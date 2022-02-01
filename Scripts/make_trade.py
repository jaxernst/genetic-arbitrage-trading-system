import sys
import os.path
sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir)))

from APIs import KucoinAPI
from Modules.Account import Account
from Modules.Session import Session
from Modules import MarketOrder, OrderGenerator
from enums import tradeSide, tradeType

percent_balance_to_trade = 1 # Buy or sell x% of the balance in the account
pair = ("ALGO", "BTC")
side = tradeSide.SELL

if __name__ == "__main__":
    api = KucoinAPI()
    pair_info = api.get_pair_info(pairs=[pair])[pair]
    account = Account(api)
    orderGen = OrderGenerator()
    fee = .002
    # Trade on the account
    if side == tradeSide.BUY:
        qouteIncrement = pair_info['quoteIncrement']
        order = MarketOrder(side, pair, account.balance[pair[1]]*(1-fee))
        orderGen.format_market_order(order, qouteIncrement=qouteIncrement)
    if side == tradeSide.SELL:
        baseIncrement = pair_info["baseIncrement"]
        order = MarketOrder(side, pair, account.balance[pair[0]]*(1-fee))
        orderGen.format_market_order(order, baseIncrement=baseIncrement) 
    
    account.submit_order(order)
