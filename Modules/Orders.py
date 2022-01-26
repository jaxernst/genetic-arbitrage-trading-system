from enums import orderStatus, tradeType, tradeSide, timeInForce
from dataclasses import dataclass, field
from typing import Dict

@dataclass   
class Order:
    side: tradeType
    pair: tuple[str,str]
    
    def __post_init__(self):
        aquired_owned = {tradeSide.BUY: (self.pair[0], self.pair[1]), 
                        tradeSide.SELL: (self.pair[1], self.pair[0])} 

        self.aquiring, self.exp_owned = aquired_owned[self.side]
        self.status: orderStatus=orderStatus.CREATED
        self.ID: str = None # Order IDs are created when submitted to the exchange
        self.update_msgs: list = None
    
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
        




