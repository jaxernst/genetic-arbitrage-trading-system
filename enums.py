from enum import Enum, auto

class sessionType(Enum):
    LIVE = auto()
    SIM = auto()

class tradeSide(Enum):
    ''' Prevent unexpected TradeTypes from being created'''
    BUY = auto()
    SELL = auto()

class tradeType(Enum):
    MARKET = auto()
    LIMIT = auto()

class orderStatus(Enum):
    CREATED = auto()
    OPEN = auto()
    FILLED = auto()
    PARTIAL_FILL = auto()
    FAILED = auto()

class amountType(Enum):
    ''' Distinguish whether the qoute currency (funds) or base currency (size)'''
    FUNDS = auto()
    SIZE = auto()

class timeInForce(Enum):
    FILL_OR_KILL = "fok"
    GOOD_TILL_CANCELED = "gtc"
