from enum import Enum, auto

class sessionType(Enum):
    LIVE = auto()
    SIM = auto()

class tradeType(Enum):
    ''' Prevent unexpected TradeTypes from being created'''
    MARKET_BUY = auto() 
    MARKET_SELL = auto()
    LIMIT_BUY = auto()
    LIMIT_SELL = auto()

class orderStatus(Enum):
    CREATED = auto()
    OPEN = auto()
    FILLED = auto()
    PARTIAL_FILL = auto()
    FAILED = auto()

class amountType(Enum):
    ''' Distinguish whether the qoute currency (funds) or base currency (size)'''
    FUNDS: auto()
    SIZE: auto()