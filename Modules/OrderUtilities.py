from CustomExceptions import OrderVolumeDepthError, TradeFailed, OrderTimeout
from APIs.ExchangeAPI import ExchangeAPI
from enums import orderStatus, tradeSide
from Modules.Orders import Order
from typing import Dict
from util import events
import time

class OrderVolumeSizer:
    BOOK_TYPE = {tradeSide.BUY:"asks", 
                 tradeSide.SELL:"bids"}

    BASE_VOLUME_CALC = {tradeSide.BUY: lambda owned,price: owned*price,
                        tradeSide.SELL: lambda owned,_: owned}
 
    def __init__(self, Pairs: Dict[tuple[str], object]) -> None:
        self.Pairs = Pairs
        self.convergence_tol = .001
        
    def get_fill_price(self, side:tradeSide, pair:tuple[str], ownedAmount:float):
        ''' 
        tradeType: "buy" or "sell"
        pair: ExchangeData pair to trade
        ownedAmount: amount in qoute currency for buy types, amount in base currency for sell types
        '''
        self.pair = pair
        book_prices, book_sizes = self.__get_separated_book(pair, side)
        p_guess = book_prices[0]
      
        def converge_price(p_guess, c=0):
            if c > 5:
                a = 1
            
            # Get amount to be filled based on the guess fill price
            test_volume = self.BASE_VOLUME_CALC[side](ownedAmount, p_guess)

            # Determine number of price levels needed to satisfy volume
            i = 0 
            while sum(book_sizes[:i+1]) < test_volume:
                i += 1
                if i > len(book_sizes):
                    raise OrderVolumeDepthError

            # Calculate the average fill price
            remaining_volume = (test_volume - sum(book_sizes[:i]))
            fill_price = (sum([price*vol for price,vol in zip(book_prices[:i], book_sizes[:i])]) + remaining_volume*book_prices[i]) / (test_volume)
            real_volume = self.BASE_VOLUME_CALC[side](ownedAmount, fill_price)

            # Recursively converge price
            if abs(real_volume - test_volume) < self.convergence_tol:
                return fill_price, i
            else:
                return converge_price(fill_price, c=c+1)

        return converge_price(p_guess)

    def __get_separated_book(self, pair, side) -> tuple[tuple[float]]: 
        ''' Return book prices and coorresponding volumes in a zipped tuple'''
        return tuple(zip(*self.Pairs[pair].orderbook.get_book(self.BOOK_TYPE[side])))

class OrderSettlementHandler:
    ''' Takes in an Order object and collects websocket order
        updates and account balance updates. 
        Returns an order object with fields populated ronce order finishes
    '''
    status_keys = {"open":orderStatus.OPEN,
                   "match":orderStatus.PARTIAL_FILL,
                   "filled":orderStatus.FILLED}

    funds_settled = False
    last_trade_failed = False
    bal_changes = {}
    order_max_wait_time = 10 # seconds
 
    def __init__(self, API:ExchangeAPI, order:Order):
        self.Order = order

        events.subscribe(API.ACCOUNT_BALANCE_UPDATE_EVENT_ID, self.account_balance_update_listener)
        events.subscribe(API.ORDER_UPDATE_EVENT_ID, self.order_update_listener)
        self.activate_order_update_stream(API)
        self.activate_account_balance_update_stream(API)
        
    def wait_to_receive(self) -> float:
        print("waiting for order to complete")
        t1 = time.time()
        while not self.funds_settled:             
            elasped = time.time() - t1
            if elasped > self.order_max_wait_time:
                print("Order response time out")
                raise OrderTimeout
            if self.Order.status == orderStatus.FAILED:
                print("Trade failed")
                raise TradeFailed
            time.sleep(.01) 

        print(f"Order status done for: {self.Order.pair}, now owned {self.received_amount} units")
        return self.received_amount
    
    def account_balance_update_listener(self, message:dict) -> None:
        oID = message['relationContext']['orderId']
        event = message['relationEvent']
        if oID == self.Order.ID and event == "trade.setted":
            self.funds_settled = True
            self.received_amount = float(message['available'])

    def order_update_listener(self, message:dict) -> None:
        oID = message['orderId']
        if oID != self.Order.ID:
            return

        self.Order.update(message)
        status = message['type']
        if status == "update":
            raise Exception("Pending order change updates not handled yet")

        if status == "canceled":
            if float(message['filledSize']) == 0:
                self.Order.status = orderStatus.FAILED
            else:
                self.Order.status = orderStatus.FILLED
        else:
            self.Order.status = self.status_keys[status]

    def activate_account_balance_update_stream(self, API) -> None:
        if API.ACCOUNT_BALANCE_UPDATE_EVENT_ID not in API.active_streams:
            API.subscribe_account_balance_notice()

    def activate_order_update_stream(self, API) -> bool:
        if API.ACCOUNT_BALANCE_UPDATE_EVENT_ID not in API.active_streams:
            API.subscribe_order_status()