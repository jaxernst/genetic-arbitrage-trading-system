from concurrent.futures import ThreadPoolExecutor
from typing import List, Tuple
import requests
import json
import Config

from util import events
from util.currency_filters import remove_single_swapabble_coins
from APIs.WebSocketClient import WebSocketClient
from APIs.abstract import ExchangeAPI

####################################################

class KrakenAPI(ExchangeAPI):
    SERVER = "https://api.kraken.com"
    SOCKET_URL = "wss://ws.kraken.com"
    PAIR_UPDATE_EVENT_ID = "KrakenPairUpdate"
    TICKER_ENDPOINT = "/0/public/Ticker"
    SYMBOLS_ENDPOINT = "/0/public/AssetPairs"

    def __init__(self):
        self.socket = WebSocketClient(self, url=self.SOCKET_URL)
        self.streaming = self.socket.connected
        self.showDataStream = False

    def get_tradeable_pairs(self, tuple_separate=True, remove_singles=True) -> list:
        r = requests.get(f"{self.SERVER}{self.SYMBOLS_ENDPOINT}")
        pairs = []
        pairs2 = []
        results = r.json()['result']
        for key in results:
            base, qoute = results[key]["wsname"].split("/")
            if base not in Config.skipCurrencies and qoute not in Config.skipCurrencies:
                pairs2.append((base,qoute))
                if tuple_separate:
                    pairs.append((base,qoute))
                else:
                    pairs.append(f"{base}/{qoute}")
        
        if remove_singles:
            pairs = remove_single_swapabble_coins(pairs2)
            if not tuple_separate:
                pairs = [f"{pair[0]}/{pair[1]}" for pair in pairs]
        
        return pairs

    def get_pair_spread(self, pair: Tuple[str]) -> Tuple[float]: 
        resp = requests.get(f"{self.SERVER}{self.TICKER_ENDPOINT}?pair={pair[0]}{pair[1]}").json()
        if not resp['error']:
            ticker = next(iter(resp['result']))
            bid = resp['result'][ticker]['b'][0]
            ask = resp['result'][ticker]['a'][0]
            last = resp['result'][ticker]['c'][0]
            return (float(bid), float(ask), float(last))
        else:
            print(resp)  
            raise Exception("No data from ticker data request")   
            
    def get_multiple_pairs_spread(self, pairs: List[tuple]) -> List[Tuple[float]]:
        urls = [f"{self.SERVER}{self.TICKER_ENDPOINT}?pair={pair[0]}{pair[1]}" for pair in pairs] 

        with ThreadPoolExecutor(max_workers=10) as pool:
            response_list = list(pool.map(requests.get, urls))
        
        out = []
        for resp in response_list:
            resp = resp.json()
            if not resp['error']:
                ticker = next(iter(resp['result']))
                bid = resp['result'][ticker]['b'][0]
                ask = resp['result'][ticker]['a'][0]
                last = resp['result'][ticker]['c'][0]
                out.append((float(bid), float(ask), float(last)))
            else:
                print(resp)  
                raise Exception("No data from ticker data request")  
        return out

    def add_price_stream(self, pair:Tuple[str]) -> None:
        # Facillitate easy selection of payload type, build payload, then send the dictionary to the socket
        payload = { "event": "subscribe",
            "pair": [f"{pair[0]}/{pair[1]}"],
            "subscription": {"name": "ticker"}}
        self.socket.send(json.dumps(payload))
    
    def remove_price_stream(self, pair:Tuple[str]):
        pass
    
    def subscribe_all(self, limit:int=None, pairs: List[str]=None) -> None:
        if not pairs:
            pairs = self.get_tradeable_pairs(tuple_separate=False)

        if limit:
            pairs = pairs[:limit]

        #for base, qoute in pairs:
        payload = { "event": "subscribe",
                    "pair": pairs,
                    "subscription": {"name": "ticker"}}
        self.socket.send(json.dumps(payload))    
    
    def stream_listen(self, message):
        ''' Receive incoming message and send on a tuple with the following format:
            (pair: str (i.e. ETHUSD), {payload: dict})
            
            - The payload will follow the kraken format, so for this class, the payload can be sent on as is
        '''
        # Ignoring hearbeat messages for now
        if self.showDataStream:
            print(message)

        message = json.loads(message)
        if "errorMessage" in message:
            print(message)
            return

        if type(message) is list:
            message = message[1:]
            if "ticker" in message:
                base, qoute = message[message.index("ticker") + 1].split("/")
                data = {}
                data['bid']  = message[0]['b'][0] 
                data['ask']  = message[0]['a'][0]
                data['close']  = message[0]['c'][0]

                events.post_event(self.PAIR_UPDATE_EVENT_ID, ((base,qoute),data))



    




        
        

        

    
    

        

