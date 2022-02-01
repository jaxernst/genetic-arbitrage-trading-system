from email.mime import base
from Modules.DataManagement import ExchangeData
from enums import orderStatus, tradeType, tradeSide, timeInForce
from CustomExceptions import OrderVolumeDepthError
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_DOWN
from typing import Dict

@dataclass   
class Order:
    side: tradeSide
    pair: tuple[str,str]
    
    def __post_init__(self):
        aquired_owned = {tradeSide.BUY: (self.pair[0], self.pair[1]), 
                        tradeSide.SELL: (self.pair[1], self.pair[0])} 

        self.aquiring, self.exp_owned = aquired_owned[self.side]
        self.status: orderStatus=orderStatus.CREATED
        self.ID: str = None # Order IDs are created when submitted to the exchange
        self.update_msgs: list = None
        self.received_amount: float = None
    
    def __eq__(self, check) -> bool:
        return self.ID == check.ID
    
    def average_fill(self) -> float:
        pass
    
    def update(self, message:dict) -> None:
        if self.update_msgs is None:
            self.update_msgs = []
        self.update_msgs.append(message)

@dataclass
class MarketOrder(Order):
    amount: float # Amount owned (sell: amount is the base, buy: amount is the qoute)
    simulated: bool = False

    def __post_init__(self):
        self.required_balance = self.amount
        return super().__post_init__()

@dataclass
class LimitOrder(Order):
    amount: float # Amount in base currency (always base currency for limit orders)
    price: float=None
    tif: timeInForce=timeInForce.GOOD_TILL_CANCELED
    simulated: bool = False

    def __post_init__(self):
        if self.side == tradeSide.BUY:
            self.required_balance =  self.price*self.amount
        if self.side == tradeSide.SELL:
            self.required_balance = self.amount
        return super().__post_init__()
        
class OrderGenerator:
    ''' 
    Create and format orders based on exchange defined price increments, size increments, and 
    the balance of the Tradeable (Account or Session)
    '''
    def __init__(self, DataManager:ExchangeData=None):
        self.DataManager = DataManager # Need for order parameter increments

    def create_order_from_funds(self, side:tradeSide, pair:tuple[str,str], funds:float, price:float=None) -> Order:
        ''' Create and format an order with with amount of funds (owned currency) given'''
        order_amount = funds
        if price is None:

            order = MarketOrder(side, pair, funds)
            return self.format_market_order(order)
        else:
            if side == tradeSide.BUY:
                order_amount = funds / price 

            order = LimitOrder(side, pair, order_amount, price)
            return self.format_limit_order(order)

    def format_limit_order(self, order:Order, priceIncrement:str=None, baseIncrement:str=None) -> Order:
        ''' Amount is always in base curreny for limit orders'''
        if self.DataManager is None:
            if priceIncrement is None or baseIncrement is None:
                raise Exception("priceIncrement and baseIncrement arguments required.")
        else:
            priceIncrement = self.DataManager.Pairs[order.pair].priceIncrement
            baseIncrement = self.DataManager.Pairs[order.pair].baseIncrement

        order.price = self.round_to_increment(order.price, priceIncrement)
        order.amount = self.round_to_increment(order.amount, baseIncrement)
        return order
    
    def format_market_order(self, order:Order, qouteIncrement:str=None, baseIncrement:str=None) -> Order:
        if order.side == tradeSide.BUY:
            if self.DataManager is None:
                if qouteIncrement is None:
                    raise Exception("qouteIncrement is required to format a market buy order")
            else:
                qouteIncrement = self.DataManager.Pairs[order.pair].qouteIncrement     
            
            order.amount = self.round_to_increment(order.amount, qouteIncrement)

        elif order.side == tradeSide.SELL:
            if self.DataManager is None:
                if baseIncrement is None:
                    raise Exception("baseIncrement is required to format a market sell order")
            else:
                baseIncrement = self.DataManager.Pairs[order.pair].baseIncrement

            order.amount = self.round_to_increment(order.amount, baseIncrement)
        
        return order
    
    def round_to_increment(self, amount, precision):
        ''' Round down to the exchange defined precision'''
        return float(Decimal(str(amount)).quantize(Decimal(precision), rounding=ROUND_DOWN))

class OrderVolumeSizer:
    BOOK_TYPE = {tradeSide.BUY:"asks", 
                 tradeSide.SELL:"bids"}

    BASE_VOLUME_CALC = {tradeSide.BUY: lambda owned,price: owned/price,
                        tradeSide.SELL: lambda owned,_: owned}
 
    def __init__(self, Pairs: Dict[tuple[str], object]) -> None:
        self.Pairs = Pairs
        self.convergence_tol = .001
        
    def get_average_fill_price(self, side:tradeSide, pair:tuple[str], ownedAmount:float):
        ''' 
        Return the average price that a market order would be expected to fill at based on the current ordebook state
        '''
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
                return fill_price
            else:
                return converge_price(fill_price, c=c+1)

        return converge_price(p_guess)

    def get_best_fill_price(self, side:tradeSide, pair:tuple[str], ownedAmount:float):
        ''' 
        Return the best existing orderbook price level that can cover the full trade volume.
        Note: 
        This is returns a price level that exists in the orderbook in its current state, so 
        this function is better suited for limit order, while get_average_fill is better suited 
        for a market order.
        '''

        book_prices, book_sizes = self.__get_separated_book(pair, side)
        
        i = 0
        summed_volume = book_sizes[0]
        test_volume = self.BASE_VOLUME_CALC[side](ownedAmount, book_prices[0])
        while summed_volume < test_volume:
            i += 1
            summed_volume += book_sizes[i]

        return book_prices[i]

    def __get_separated_book(self, pair, side) -> tuple[tuple[float]]: 
        ''' Return book prices and coorresponding volumes in a zipped tuple'''
        return tuple(zip(*self.Pairs[pair].orderbook.get_book(self.BOOK_TYPE[side])))
