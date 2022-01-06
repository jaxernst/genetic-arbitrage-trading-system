from concurrent.futures import ThreadPoolExecutor
from threading import Thread
from typing import List, Tuple
from uuid import uuid4
from time import sleep
import requests
import json
import Config
import re

from CustomExceptions import TooManyRequests
from util import events
from util.obj_funcs import load_obj
from util.currency_filters import remove_single_swapabble_coins
from APIs.WebSocketClient import WebSocketClient
from APIs.abstract import ExchangeAPI
from Modules.Portfolio import Portfolio

####################################################

class KucoinAPI(ExchangeAPI):
    PAIR_UPDATE_EVENT_ID = "KucoinPairUpdate"
    SERVER = "https://api.kucoin.com"
    TICKER_ENDPOINT = "/api/v1/market/orderbook/level1"
    ORDERBOOK_ENDPOINT = "/api/v1/market/orderbook/level2_100"
    SYMBOLS_ENDPOINT = "/api/v1/symbols"

    def __init__(self):
        self.socket = WebSocketClient(self, url=self.generate_connection_url())
        self.streaming = self.socket.connected
        self.showDataStream = False
        
        self.subscriptions = 0
        self.subscription_limit = 300

    def generate_connection_url(self, private=False):
        # Request token
        if private:
            req = "/api/v1/bullet-private" 
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
                sleep(self.pingInterval)

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
            skip = Config.skipCurrencies + load_obj("banned_coins")
            if base not in skip and qoute not in skip:
                pairs2.append((base,qoute))
                if tuple_separate:
                    pairs.append((base,qoute))
                else:
                    pairs.append(f"{base}-{qoute}")
        
        if remove_singles:
            pairs = remove_single_swapabble_coins(pairs2)
            if not tuple_separate:
                pairs = [f"{pair[0]}-{pair[1]}" for pair in pairs]
        return pairs
    
    def get_pair_spread(self, pair: Tuple[str]) -> Tuple[float]:        
        r = requests.get(f"{self.SERVER}{self.TICKER_ENDPOINT}?symbol={pair[0]}-{pair[1]}").json()
        if r['data']:
            bid = r['data']['bestBid']
            ask = r['data']['bestAsk']
            last = r['data']['price']
            return (float(bid), float(ask), float(last))
        else:
            print(r)
            raise Exception("No data from ticker data request")
 
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
        urls = [f"{self.SERVER}{self.ORDERBOOK_ENDPOINT}?symbol={pair[0]}-{pair[1]}" for pair in pairs] 
        with ThreadPoolExecutor(max_workers=10) as pool:
            response_list = list(pool.map(requests.get, urls))
        
        out = {}
        for i, response in enumerate(response_list):
            data = response.json()
            if 'data' in data:
                out[pairs[i]] = {}
                out[pairs[i]]['bids'] = [[float(x) for x in sublist] for sublist in data['data']['bids']]
                out[pairs[i]]['asks'] = [[float(x) for x in sublist] for sublist in data['data']['asks']]
            elif data['code'] == '429000':
                raise TooManyRequests
            else:
                raise Exception (f"Unexpected response from API: {data}")
        return out
    
    def add_price_stream(self, pair:Tuple[str]) -> None:
        # Facillitate easy selection of payload type, build payload, then send the dictionary to the socket
        payload = { 'id': self.connectID,
                    "type": "subscribe",
                    "topic": f"/market/ticker:{pair[0]}-{pair[1]}",
                    "privateChannel": False}
        self.socket.send(json.dumps(payload))
    
    def remove_price_stream(self, pair:Tuple[str]):
        pass

    def subscribe_all(self, limit:int=None, pairs: List[str]=None) -> None:
        if not pairs:
            pairs = self.get_tradeable_pairs(tuple_separate=False)
        
        if limit:
            pairs = pairs[:limit]
        
        def divide_chunks(l, n):
            # looping till length l
            for i in range(0, len(l), n): 
                yield l[i:i + n]
        
        pair_iter = list(divide_chunks(pairs, 100))

        for pairs in pair_iter:
            tickers = ','.join([f"{pair}" for pair in pairs])
            payload = { 'id': self.connectID,
                        "type": "subscribe",
                        "topic": f"/market/ticker:{tickers}",
                        "subscription": {"name": "ticker"}}
            self.socket.send(json.dumps(payload))      
    
    def stream_listen(self, message) -> None:
        ''' Receive incoming message and send on a tuple with the following format:
            (pair: str (i.e. ETHUSD), {payload: dict})
            
            - The payload will follow the kraken format, so for this class, the payload can be sent on as is
        '''
        # Ignoring hearbeat messages for now
        if self.showDataStream:
            print(message)

        message = json.loads(message)
        if message['type'] != "message":
            print(message)
            return
        #print(message)
        if message['data']:
            ticker = re.search(r"ticker:(\w+-\w+)", message['topic']).group(1)
            base, qoute = ticker.split("-")

            data = {}
            data['close'] = message['data']['price']
            data['bid'] = message['data']['bestBid']
            data['ask'] = message['data']['bestAsk']
            events.post_event(self.PAIR_UPDATE_EVENT_ID, ((base,qoute),data))
        else:
            print(message)
            raise Exception("No data in this message")

    def authenticate(self):
        ''' Have the user input credentials and authenticate rest api'''

    def get_portfolio(self) -> Portfolio:
        '''Request portfolio information for an authenticated account and returns a portfolio object'''
        balances = {}
        return Portfolio()
        

        

    
    

        

