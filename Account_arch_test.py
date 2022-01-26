from APIs import KucoinAPI
from Modules.Account import Account
from Modules.Sessions import Session
from enums import tradeType

api = KucoinAPI()
account = Account(api)
sesh = Session(account)
sesh.buy(("ETH","BTC"),0.00001, tradeType.MARKET_BUY)