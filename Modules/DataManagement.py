import dataclasses
from typing import Tuple, Dict
from dataclasses import dataclass
from APIs.abstract import ExchangeAPI
from util.currency_filters import remove_single_swapabble_coins
from util import events
from util.obj_funcs import save_json
import logging
import bisect
import time

@dataclass
class Orderbook:
    last_sequence: int = None
    bids: dict = None
    asks: dict = None
    missing_sequences:list=None

    def update(self, type, price, size, sequence:int):
        if int(sequence) != self.last_sequence + 1:
            if not self.missing_sequences:
                self.missing_sequences = []
            self.missing_sequences.append(sequence)     
        self.last_sequence = sequence
        
        if not self.bids:
            self.bids = {}
        if not self.asks:
            self.asks - {}

        if price == "0":
            return
        if type == "bids":
            self.bids[price] = size
            if size == "0": 
                self.bids.pop(price)
        elif type == "asks":
            self.asks[price] = size
            if size == "0": 
                self.asks.pop(price)
                 
    def get_book(self, type):
        out = []
        if type == 'bids':
            book_sorted = sorted(self.bids.items(), reverse=True)
        elif type == 'asks':
            book_sorted = sorted(self.asks.items())
        else:
            raise Exception("Invalid type")

        for price, size in book_sorted:
            out.append([float(price), float(size)])
        return out

@dataclass
class Pair:
    base: str
    qoute: str
    best_bid: float = None
    best_ask: float = None
    close: float = None
    orderbook: Orderbook = None
    lastUpdated: float = time.time()
    baseIncrement: float = None
    qouteIncrement: float = None
    priceIncrement: float = None
    fee: float = None
    exchange = None

    def __post_init__(self):
        self.ticker = f"{self.base}/{self.qoute}"
        self.sym = self.base + "/" + self.qoute

    def fee_spread_populated(self):
        return isinstance(self.orderbook.bids,dict) and isinstance(self.orderbook.asks,dict) and self.fee

   
class ExchangeData:

    PAIR_UPDATE_EVENT_ID = "ExchangeDataPairUpdate"
    ORDER_DONE_EVENT_ID = "OrderDoneEvent"

    def __init__(self, API: ExchangeAPI):
        self.API = API
        self.Pairs = {} # List of 
        self.Orders = {}
        self.balanceUpdates = []
        self.skipCurrencies = [] # Currencies to not collect data on
        self.showPairUpdates = False
        self.num_missing_fees = None
        self.missing_fees  = []
        self.level2_calibrated = False
        self.orderbook_updates = 0
        self.orders = []

        logging.basicConfig(filename='util/orders.log', encoding='utf-8', level=logging.DEBUG)
        events.subscribe(API.PAIR_UPDATE_EVENT_ID, self.pair_update_listener)
        events.subscribe(API.ORDER_UPDATE_EVENT_ID, self.order_update_listener)
        events.subscribe(API.ACCOUNT_BALANCE_UPDATE_EVENT_ID, self.account_balance_update_listener)
        events.subscribe(API.LEVEL2_UPDATE_EVENT_ID, self.level_2_update_listener)
        events.subscribe(API.DISCONNECT_EVENT_ID, self.build_orderbook)

    def build_orderbook(self):
        '''Creates orderbook for each pair, start oderbook update stream, and calibrates the ordebook with the sequencial updates'''
        self.level2_calibrated = False
        self.orderbook_cache = {}
        print("Subscribing to ordebook stream...")
        self.API.subscribe_level2(list(self.Pairs.keys()))
        time.sleep(.4) # Delay to allow orders to get cached
        print("Getting orderbook snapshot...")
        snapshot = self.API.get_multiple_orderbooks(list(self.Pairs.keys()))
        
        # Create ordebook objects for each pair
        for pair in snapshot:
            asks = {price:size for price, size in snapshot[pair]["asks"]}
            bids = {price:size for price, size in snapshot[pair]["bids"]}
            self.Pairs[pair].orderbook.asks = asks
            self.Pairs[pair].orderbook.bids = bids
            self.Pairs[pair].orderbook.last_sequence = int(snapshot[pair]['sequence'])
        
        # Playback cache
        print(f"Initial orderbook built, calibrating with {len(self.orderbook_cache)} cached orderbook increments...")
        for pair in list(self.orderbook_cache):
            for cache_sequence in list(self.orderbook_cache[pair]):
                # Discard cache_sequenced orderbook change data from sequences that came before the ordebook was built
                if int(cache_sequence) > self.Pairs[pair].orderbook.last_sequence:
                    type, price, size = self.orderbook_cache[pair][cache_sequence]
                    self.Pairs[pair].orderbook.update(type, price, size, int(cache_sequence))
            try:
                print(f"{pair} calibration status set to True with {len(self.Pairs[pair].orderbook.missing_sequences)} missing sequences")
            except:
                print(f"{pair} calibration status set to True with 0 missing sequences")

        self.level2_calibrated = True

    def level_2_update_listener(self, message):
        base, qoute = message["symbol"].split('-')
        
        if not self.level2_calibrated:
            for type, changes in message['changes'].items():
                for change in changes:
                    price, size, sequence_num  = change
                    if (base,qoute) not in self.orderbook_cache:
                        self.orderbook_cache[(base,qoute)] = {}
                    self.orderbook_cache[(base,qoute)][sequence_num] = (type, price, size)
                    return
        else:
            for type, change in message['changes'].items():
                if change:
                    price, size, sequence = change[0]
                    self.Pairs[(base,qoute)].orderbook.update(type, price, size, int(sequence))
                    self.orderbook_updates += 1
            a = 1
    
    def pair_update_listener(self, message: Tuple[tuple,Dict[str,str]]) -> None:
        '''
        This function is called when pair data is received through the websocket.
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
            #print(f"Pair {pair} not in pairs.")
            self.Pairs[pair] = Pair(base, qoute)
        
        self.Pairs[pair].close =  float(data['close'])
        self.Pairs[pair].ask = float(data['ask'])
        self.Pairs[pair].bid = float(data['bid'])
        self.Pairs[pair].last_updated = time.time()
        
        if self.showPairUpdates:
            self.show_coins()

    def order_update_listener(self, message):
        oID = message['orderId']
        self.Orders[oID] = []
        self.Orders[oID].append(message)
        side = message['side']
        status = message['status']

        if status == "done":
            fill_size = message['filledSize']
            events.post_event(self.ORDER_DONE_EVENT_ID, fill_size)

            #self.Orders.pop((side,(base,qoute)))
    
        #self.Orders[(base,qoute)]['type'] = message['type']
        #self.Orders[(base,qoute)]['status'] = message['status']
        #self.Orders[(base,qoute)]['filledSize'] = message['filledSize']

    def account_balance_update_listener(self, message):
        self.balanceUpdates.append(message)

    def save_orders(self):
        now = str(time.time()) 
        save_json(self.Orders, f"orders_{now}")
        save_json(self.balanceUpdates, f"balances_{now}")
    
    def show_coins(self):
        for pair in self.Pairs:
            if self.Pairs[pair].close != None:
                print(self.Pairs[pair])

    def make_pairs(self, pairInfo, populateSpread=False):
        for pair, pair_data in pairInfo.items():
            base, qoute = pair
            if (base, qoute) not in self.Pairs:
                if populateSpread:
                    bid, ask, close = self.update_spread((base,qoute))
                    self.Pairs[(base, qoute)] = Pair(base, qoute, best_bid=bid, best_ask=ask, close=close, 
                                                    orderbook=Orderbook(),
                                                    baseIncrement=pair_data['baseIncrement'],
                                                    qouteIncrement=pair_data['qouteIncrement'],
                                                    priceIncrement=pair_data['priceIncrement'],
                                                    fee=float(pair_data['fee']))
                else:
                    self.Pairs[(base, qoute)] = Pair(base=base, qoute=qoute, 
                                                    orderbook=Orderbook(),
                                                    baseIncrement=pair_data['baseIncrement'], 
                                                    qouteIncrement=pair_data['quoteIncrement'],
                                                    priceIncrement=pair_data['priceIncrement'],
                                                    fee=float(pair_data['fee']))
    
    def update_missing_fee_pairs(self):
        self.missing_fees  = []
        for pair_name, pair  in self.Pairs.items():
            if not pair.fee:
                self.missing_fees.append(pair_name)

        print(f"Out of {len(self.Pairs)}, {len(self.missing_fees)} are currently missing, updating those fees")

        for pair, fee in self.API.get_pair_fees(self.missing_fees).items():
            self.Pairs[pair].fee = float(fee)

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
    