from typing import Tuple, Dict
from dataclasses import dataclass
from APIs.abstract import ExchangeAPI
from util import events
import time

@dataclass
class Coin:
    ticker: str
    orders: dict = None 
    price: float = None # Price in USD
    fullName: str = None # Will have to create  a key:pair dict with all tickers and their names
    balance: float = None 

@dataclass
class Pair:
    base: Coin
    qoute: Coin
    bid: float = None
    ask: float = None
    close: float = None
    bids: list = None
    asks: list = None
    #basePrice: base.price
    lastUpdated: float = time.time()
    exchange = None

    def __post_init__(self):
        self.ticker = f"{self.base.ticker}/{self.qoute.ticker}"
    def spread_populated(self):
        return bool(self.bid and self.ask)

class ExchangeData:
    PAIR_UPDATE_EVENT_ID = "ExchangeDataPairUpdate"
    
    def __init__(self, API: ExchangeAPI):
        self.API = API
        self.Pairs = {} # List of 
        self.skipCurrencies = [] # Currencies to not collect data on
        self.showPairUpdates = False
        self.base_fee = .0026
        events.subscribe(API.PAIR_UPDATE_EVENT_ID, self.pair_update_listener)
        
    def pair_update_listener(self, message: Tuple[tuple,Dict[str,str]]) -> None:
        '''
        This function is called whenpair data is received through the websocket.
        Mesaage: tuple = (("base","qoute"), {'close':..., 'ask':..., 'bid':...})
        '''
        pair = message[0]
        data = message[1]
        #print(message)
        if type(data) != dict:
           raise Exception("Unexpected data type")

        base = pair[0]
        qoute = pair[1]
        if pair not in self.Pairs:
            self.Pairs[pair] = Pair(Coin(base), Coin(qoute))
        
        self.Pairs[pair].close =  float(data['close'])
        self.Pairs[pair].ask = float(data['ask'])
        self.Pairs[pair].bid = float(data['bid'])
        self.Pairs[pair].last_updated = time.time()
        
        if self.showPairUpdates:
            self.show_coins()

    def show_coins(self):
        for pair in self.Pairs:
            if self.Pairs[pair].close != None:
                print(self.Pairs[pair])

    def make_pairs(self, pairList, populateSpread=False):
        if type(pairList) != list:
            list(pairList)
        
        for base, qoute in pairList:
            '''
            if base not in self.Coins:
                self.Coins[base] = Coin(base)
            if qoute not in self.Coins:
                self.Coins[qoute] = Coin(qoute)
            '''
            if (base, qoute) not in self.Pairs:
                if populateSpread:
                    bid, ask, close  = self.update_spread((base,qoute))
                    self.Pairs[(base, qoute)] = Pair(Coin(base), Coin(qoute), bid, ask, close)
                else:
                    self.Pairs[(base, qoute)] = Pair(Coin(base), Coin(qoute))

    def update_spread(self, pair):
        return self.API.get_pair_spread(pair)

    def refresh_pairs(self, threshold=60):
        for pair in self.Pairs:
            if (time.time() - self.Pairs[pair].last_updated) > threshold:
                bid, ask, close = self.update_spread(pair)
                self.Pairs[pair].bid = bid
                self.Pairs[pair].bid = ask
                self.Pairs[pair].close = close
                self.Pairs[pair].last_updated = time.time()
    
    def getPriceHistory():
        pass