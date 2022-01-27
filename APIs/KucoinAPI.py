from concurrent.futures import ThreadPoolExecutor
from threading import Thread
from typing import List, Tuple
from uuid import uuid4
import time
import asyncio
import requests
import json
import Config
import re

from CustomExceptions import TooManyRequests
from util import events
from util.currency_funcs import remove_single_swapable_coins
from APIs.authentication import KucoinAuthenticator
from APIs.WebSocketClient import WebSocketClient
from APIs.ExchangeAPI import ExchangeAPI
from Modules.Orders import LimitOrder, MarketOrder

####################################################
# This class is long overdue for a cleanup

class KucoinAPI(ExchangeAPI):
    ''' 
    Creates websocket connection, requests/posts APi endpoints, subscribes/unsubscribes from websokcet streams, distributes websocket messages
    '''
    PAIR_UPDATE_EVENT_ID = "KucoinPairUpdate"
    ORDER_UPDATE_EVENT_ID = "OrderStatusUpdate"
    ACCOUNT_BALANCE_UPDATE_EVENT_ID = "AccountBalanceUpdate"
    LEVEL2_UPDATE_EVENT_ID = "Level2Update"
    DISCONNECT_EVENT_ID = "SocketDisconnected"

    SERVER = "https://api.kucoin.com"
    TICKER_ENDPOINT = "/api/v1/market/orderbook/level1"
    ORDERBOOK_ENDPOINT = "/api/v1/market/orderbook/level2_100"
    SYMBOLS_ENDPOINT = "/api/v1/symbols"
    ACCOUNT_ENDPOINT = "/api/v1/accounts"
    ORDER_ENDPOINT = "/api/v1/orders"
    TRADE_FEE_ENDPOINT = "/api/v1/trade-fee"

    def __init__(self, private=True, sandbox=False):

        if private:
            if not sandbox:
                self.Auth = KucoinAuthenticator(self.SERVER)
            else:
                self.Auth = KucoinAuthenticator("https://openapi-sandbox.kucoin.com")

        self.socket = WebSocketClient(self, url=self.generate_connection_url(private))
        self.streaming = self.socket.connected
        self.showDataStream = False
        self.active_streams = []
        self.request_freq = 5
        self.ping_interval_scale = 1
        self.last_pong_time = 0
        self.payloads = [] # Stores subscription functions with arguements so they can be recalled when reconnect occurs
        self.subscription_limit = 300

    def generate_connection_url(self, private=True):
        # Request token
        if private:
            req = "/api/v1/bullet-private"
            r = self.Auth.request(req, "POST").json()
        else:
            req = "/api/v1/bullet-public"
            r = requests.post(f"{self.SERVER}{req}").json()
        token = r['data']['token']
        
        # get endpoint and ping info
        endpoint = r['data']['instanceServers'][0]['endpoint']
        self.pingInterval =  float(r['data']['instanceServers'][0]['pingInterval'])*10**-3

        # Generate connect ID
        self.connectID = str(uuid4()).replace('-', '')
        return f"{endpoint}?token={token}&connectId={self.connectID}"

    def maintain_connection(self):
        def send_ping():
            while True:
                payload = {"id":f"{self.connectID}",
                            "type":"ping"}
                self.socket.send(json.dumps(payload))
                print("sending ping")
                send_time = time.time()
                time.sleep(self.pingInterval*self.ping_interval_scale)

                if self.last_pong_time < send_time:
                    # No pong received since last sent
                    print("Pong not received...")
                    #if self.socket.attempt_reconnect():
                    #    # If reconnect succesful, resubscribe
                    #    events.post_event(self.DISCONNECT_EVENT_ID)
                    #    self.reset_subscriptions()

        self.ping_thread = Thread(target=send_ping)
        self.ping_thread.daemon=True
        self.ping_thread.start()
    
    def get_tradeable_pairs(self, tuple_separate=True, remove_singles=True) -> list:
        r = requests.get(f"{self.SERVER}{self.SYMBOLS_ENDPOINT}").json()
        pairs = []
        pairs2 =[]
        results = r['data']
        for pair_data in results:
            base, qoute = pair_data["symbol"].split("-") 
            skip = Config.skipCurrencies
            if base not in skip and qoute not in skip:
                pairs2.append((base,qoute))
                if tuple_separate:
                    pairs.append((base,qoute))
                else:
                    pairs.append(f"{base}-{qoute}")
            else:
                print(f"Skipping {(base,qoute)}")
        
        if remove_singles:
            pairs = remove_single_swapable_coins(pairs2)
            if not tuple_separate:
                pairs = [f"{pair[0]}-{pair[1]}" for pair in pairs]
        
        return pairs
    
    def get_pair_info(self, pairs:list=None, limit:int=None) -> dict:
        r1 = requests.get(f"{self.SERVER}{self.SYMBOLS_ENDPOINT}").json()
        r2 = self.Auth.request(f"{self.TRADE_FEE_ENDPOINT}", "GET").json()
        pair_info = {}
        results = r1['data']
        fees = r2['data']

        for pair_data in results:
            base, qoute = pair_data["symbol"].split("-") 
            skip = Config.skipCurrencies
            
            for fee_dict in fees:
                if fee_dict['symbol'] == pair_data['symbol']:
                    pair_data['fee'] = fee_dict['taker']
            
            
            if base not in skip and qoute not in skip:
                if pairs:
                    if (base,qoute) in pairs:
                        pair_info[(base, qoute)] = pair_data
                        continue
                pair_info[(base, qoute)] = pair_data
            else:
                print(f"Skipping {(base,qoute)}")

            if limit and len(list(pair_info.keys())) >= limit:
                break

        return pair_info
    
    def get_pair_fees(self, pairs):
        def divide_chunks(l, n):
            # looping till length l
            for i in range(0, len(l), n): 
                yield l[i:i + n]

        urls = []
        for pairs in divide_chunks(pairs, 10):
            joined = ','.join([f"{base}-{qoute}" for base, qoute in pairs])
            urls.append(f"{self.TRADE_FEE_ENDPOINT}s?symbols={joined}")
    

        with ThreadPoolExecutor(max_workers=10) as pool:
            response_list = list(pool.map(self.Auth.request, urls))

        out = {}
        for i, response in enumerate(response_list):
            data = response.json()
            if 'data' in data:
                for fee_data in data['data']:
                    base, qoute = fee_data['symbol'].split("-")
                    out[(base, qoute)] = fee_data['takerFeeRate']
                
            elif data['code'] == '429000':
                raise TooManyRequests
            else:
                raise Exception(f"Unexpected response from API: {data}")
        return out

    def get_pair_spread(self, pair: Tuple[str]) -> Tuple[float]:        
        
        r = requests.get(f"{self.SERVER}{self.TICKER_ENDPOINT}?symbol={pair[0]}-{pair[1]}").json()
        if r['data']:
            bid = r['data']['bestBid']
            ask = r['data']['bestAsk']
            last = r['data']['price']
            return (float(bid), float(ask), float(last))
        else:
            return None, None, None
 
    def get_multiple_spreads(self, pairs: List[tuple]) -> List[Tuple[float]]:
        urls = [f"{self.SERVER}{self.TICKER_ENDPOINT}?symbol={pair[0]}-{pair[1]}" for pair in pairs] 
        with ThreadPoolExecutor(max_workers=10) as pool:
            response_list = list(pool.map(requests.get, urls))
        
        out = {}
        for response in response_list:
            data = response.json()
            if 'data' in data:     
                out['bid'] = float(data['data']['bestBid'])
                out['ask'] = float(data['data']['bestAsk'])
                out['last'] = float(data['data']['price'])
            else:
                raise Exception(f"Unexpected response from API: {data}")

        return out
    
    def get_multiple_orderbooks(self, pairs: List[tuple]):
        ''' pairs : ('ETH', 'BTC') '''
        
        def divide_chunks(l, n):
                # looping till length l
                for i in range(0, len(l), n): 
                    yield l[i:i + n]

        out = {}
        num_reqs = 0 
        t_last_request = None
        for chunk in divide_chunks(pairs, 20):
            if t_last_request:
                
                while (time.time() - t_last_request) < 1/self.request_freq:
                    time.sleep(.05)
            
            urls = [f"{self.SERVER}{self.ORDERBOOK_ENDPOINT}?symbol={pair[0]}-{pair[1]}" for pair in chunk] 
            with ThreadPoolExecutor(max_workers=40) as pool:
                response_list = list(pool.map(requests.get, urls))
            t_last_request = time.time()

            for i, response in enumerate(response_list):
                data = response.json()
                if 'data' in data:
                    out[chunk[i]] = data['data']
                elif data['code'] == '429000':
                        print(data)
                        raise TooManyRequests
                else:
                    raise Exception (f"Unexpected response from API: {data}")
            
                num_reqs += 1
                print(num_reqs)

        return out
    
    def add_price_stream(self, pair:Tuple[str]) -> None:
        # Facillitate easy selection of payload type, build payload, then send the dictionary to the socket
        self.topics_in_use.append("/market/ticker:{pair[0]}-{pair[1]}")
        payload = { 'id': self.connectID,
                    "type": "subscribe",
                    "topic": f"/market/ticker:{pair[0]}-{pair[1]}",
                    "privateChannel": False}
        self.payloads.append(payload)
        self.socket.send(json.dumps(payload))
    
    def reset_subscriptions(self):
        for payload in self.payloads:
            payload['type'] = "unsubscribe"
            self.socket.send(json.dumps(payload)) 
            time.sleep(.1)     
        for payload in self.payloads:
            payload['type'] = "subscribe"
            self.socket.send(json.dumps(payload)) 
            time.sleep(.1)  

    def subscribe_all(self, pairs: List[tuple]=None, limit:int=300) -> None:
        ''' Subscribe too pair price and orderbook stream'''
        if pairs:
            if limit:
                pairs = pairs[:limit]
            
            def divide_chunks(l, n):
                # looping till length l
                for i in range(0, len(l), n): 
                    yield l[i:i + n]

            for pairs in divide_chunks(pairs, 100):
                tickers = ','.join([f"{base}-{qoute}" for base,qoute in pairs])
                payload = { 'id': self.connectID,
                            "type": "subscribe",
                            "topic": f"/market/ticker:{tickers}",
                            "subscription": {"name": "ticker"}}
                self.payloads.append(payload)
                self.socket.send(json.dumps(payload)) 
            return     
        
        payload = { 'id': self.connectID,
                    "type": "subscribe",
                    "topic": f"/market/ticker:all",
                    "response":"true"}
        self.payloads.append(payload)
        self.socket.send(json.dumps(payload))

    def subscribe_level2(self, pairs: List[tuple], limit:int=300):
        def divide_chunks(l, n):
                # looping till length l
                for i in range(0, len(l), n): 
                    yield l[i:i + n]

        if limit:
            pairs = pairs[:limit]

        for chunk in divide_chunks(pairs, 100):
            symbols = ','.join([f"{base}-{qoute}" for base, qoute in chunk])
            payload = { 'id': self.connectID,
                        "type": "subscribe",
                        "topic": f"/market/level2:{symbols}"}
            self.socket.send(json.dumps(payload))
        
        self.active_streams.append(self.LEVEL2_UPDATE_EVENT_ID)    
   
    def subscribe_order_status(self):
        payload = { 'id': self.connectID,
                    "type": "subscribe",
                    "topic": "/spotMarket/tradeOrders",
                    "privateChannel": "true"}
        self.payloads.append(payload)
        self.socket.send(json.dumps(payload))
        self.active_streams.append(self.ORDER_UPDATE_EVENT_ID)      
    
    def subscribe_account_balance_notice(self):
        payload = { 'id': self.connectID,
                    "type": "subscribe",
                    "topic": "/account/balance",
                    "privateChannel": "true"}
        self.payloads.append(payload)
        self.socket.send(json.dumps(payload)) 
        self.active_streams.append(self.ACCOUNT_BALANCE_UPDATE_EVENT_ID)

    def stream_listen(self, message) -> None:
        ''' Receive incoming message and send on a tuple with the following format:
            (pair: str (i.e. ETHUSD), {payload: dict})
            
            - The payload will follow the kraken format, so for this class, the payload can be sent on as is
        '''
        # Ignoring hearbeat messages for now
        if self.showDataStream:
            print(message)
        
        message = json.loads(message)

        if message['type'] == "pong":
            print(message)
            self.last_pong_time = time.time()
            return
        if message['type'] != "message":
            print(message)
            return
        
        if "/market/ticker" in message['topic']:
            if message['subject'] == "trade.ticker":
                ticker = re.search(r"ticker:(\w+-\w+)", message['topic']).group(1)
            else:
                ticker = message['subject']

            base, qoute = ticker.split("-")

            data = {}
            data['close'] = message['data']['price']
            data['bid'] = message['data']['bestBid']
            data['ask'] = message['data']['bestAsk']
            events.post_event(self.PAIR_UPDATE_EVENT_ID, ((base,qoute),data))
            return
        
        if "/market/level2" in message['topic']:
            events.post_event(self.LEVEL2_UPDATE_EVENT_ID, message['data'])
        if "/spotMarket/tradeOrders" in message['topic']:
            events.post_event(self.ORDER_UPDATE_EVENT_ID, message['data'])
        if "/account/balance" in message['topic']:
            events.post_event(self.ACCOUNT_BALANCE_UPDATE_EVENT_ID, message['data'])

    def market_order(self, order:MarketOrder):
        oID = str(uuid4()).replace('-', '')
        pair = f"{order.pair[0]}-{order.pair[1]}"
        volume_type = {"buy":"funds", "sell":"size"}
        data = json.dumps({"clientOid":oID,
                            "side":order.side.name.lower(),
                            "symbol":pair,
                            volume_type[order.side.name.lower()]:order.amount,
                            "type":"market"})

        r = self.Auth.request(self.ORDER_ENDPOINT, "POST", data=data).json()
        print(r)

        if 'data' in r:
            return r['data']['orderId']

    def limit_order(self, order:LimitOrder):
        oID = str(uuid4()).replace('-', '')
        pair = f"{order.pair[0]}-{order.pair[1]}"
        
        data = {"clientOid":oID,
                "side":order.side.name.lower(),
                "symbol":pair,
                "size":order.amount,
                "price":order.price,
                "timeInForce":order.tif.value,
                "type":"limit"}

        r = self.Auth.request(self.ORDER_ENDPOINT, "POST", data=json.dumps(data)).json()
        print(r)

        if 'data' in r:
            return r['data']['orderId']

    def get_portfolio(self, return_raw_balance=False) -> dict:
        '''Request portfolio information for an authenticated account and return a portfolio object'''
        r = self.Auth.request(self.ACCOUNT_ENDPOINT, "GET").json()


        balance = {}
        for data in r['data']:
            if data['type'] == "trade":
                balance[data['currency']] = float(data['balance'])
        
        return balance


