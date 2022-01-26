from APIs import KucoinAPI
from Modules.Account import Account
from Modules.Session import Session
from enums import tradeType

if __name__ == "__main__":
    # Setup a session and make a single trade
    api = KucoinAPI()
    account = Account(api)
    sesh = Session(account)
    sesh.buy(("ETH","BTC"),0.00001, tradeType.MARKET_BUY)