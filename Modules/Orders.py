from email.mime import base
from Modules.DataManagement import ExchangeData
from enums import orderStatus, tradeType, tradeSide, timeInForce
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

