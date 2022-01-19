from Modules import DataManagement, GeneticArbitrage, TradeExecution, ExchangeData, SessionSim, SessionLive, TriangularArbitrageEngine
from APIs import KrakenAPI, KucoinAPI
from CustomExceptions import OrderVolumeDepthError
from Modules.Portfolio import Portfolio
from util.obj_funcs import load_obj, save_obj
from util.currency_funcs import remove_single_swapable_coins, get_usd_value
from util.SequenceTracker import SequenceTracker

import logging
from threading import Thread
import time




SIMULATION_MODE = False

# Init API and Data Manager
KucoinAPI = KucoinAPI()
ExchangeData = ExchangeData(KucoinAPI)

# Setup pairs for the GA to look at
pairsInfo = KucoinAPI.get_pair_info()
viablePairs = remove_single_swapable_coins(list(pairsInfo.keys()))[:299]
pairsInfo = {pair:info for pair, info in pairsInfo.items() if pair in viablePairs}
ExchangeData.make_pairs(pairsInfo, populateSpread=False)
ExchangeData.build_orderbook()
KucoinAPI.maintain_connection()
time.sleep(10)
   
# Setup account
funding_cur = "ETH"
min_volume = 100
Account = KucoinAPI.get_portfolio()
starting_bal = get_usd_value(funding_cur, Account.balance[funding_cur])

if SIMULATION_MODE:
    Session = SessionSim(Account, KucoinAPI, Account.balance[funding_cur], funding_cur, 5) # The session will update the parent account 
else:
    Session = SessionLive(Account, KucoinAPI, ExchangeData, Account.balance[funding_cur], funding_cur, 5) # The session will update the parent account 

# Setup trade execution Modules
Trader = TradeExecution(KucoinAPI, ExchangeData, Session, starting_cur=funding_cur, simulation_mode=SIMULATION_MODE)


# Setup arbitrage model
set_size = 500
TA = TriangularArbitrageEngine(Trader)



def display_stats(t1):
    amount = Session.balance[Trader.owned]
    usd_amount = get_usd_value(Trader.owned, amount)
    print("")
    print(f"Starting balance: {round(starting_bal,3)}")
    print(f"Percentage Gain: {round(100*(usd_amount - starting_bal)/starting_bal, 3)} %")
    print(f"Session owned: {Trader.owned}")
    print(f"Session balance: {round(amount,3)}")
    print(f"Number of trades: {Session.trades}")
    print(f"Best TA profit: {round(100*Trader.best_exp_profit,5)} %")
    print(ExchangeData.orderbook_updates)
    print(f"Elasped: {round((time.time() - t1)/60, 3)} minutes")
    print("")

if __name__ == "__main__":
    TA.begin(start_cur=funding_cur)
    start_time = time.time()
    while True:
        display_stats(start_time)
        time.sleep(10)
