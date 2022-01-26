from Modules import DataManagement, ExchangeData
from ArbitrageEngines import TriangularArbitrageEngine, SequenceTrader
from Modules.Session import Session
from APIs import KrakenAPI, KucoinAPI
from CustomExceptions import OrderVolumeDepthError
from Modules.Account import Account
from util.obj_funcs import load_obj, save_obj
from util.currency_funcs import remove_single_swapable_coins
from util.SequenceTracker import SequenceTracker

import logging
from threading import Thread
import time

SIMULATION_MODE = False

# Init API and Data Manager
KucoinAPI = KucoinAPI()
ExchangeData = ExchangeData(KucoinAPI)

# Setup account and trading session
Account = Account(KucoinAPI)
starting_usd_bal = Account.get_total_equivalent_value("USDT")
starting_cur, amount = Account.get_largest_holding()
Session = Session(Account)

# Setup pair data stream
pairsInfo = KucoinAPI.get_pair_info()
viablePairs = remove_single_swapable_coins(list(pairsInfo.keys()))[:299] # SOcket can only maintain 300 orderbook subscriptions
pairsInfo = {pair:info for pair, info in pairsInfo.items() if pair in viablePairs}
ExchangeData.make_pairs(pairsInfo, populateSpread=False)
ExchangeData.build_orderbook()
KucoinAPI.maintain_connection()
time.sleep(5)
   
# Setup trade execution and arbitrage engine
SequenceTrader = SequenceTrader(ExchangeData, Session, starting_cur=Session.starting_cur)

# Setup arbitrage model
set_size = 500
TA = TriangularArbitrageEngine(SequenceTrader)

def display_stats(t1):
    usd_amount = Account.get_total_equivalent_value("USDT")
    print("")
    print(f"Starting balance: {round(starting_usd_bal,3)}")
    print(f"Current balance: {round(usd_amount,3)}")
    print(f"Percentage Gain: {round(100*(usd_amount - starting_usd_bal)/starting_usd_bal, 3)} %")
    print(f"Session owned: {SequenceTrader.owned}")

    print(f"Number of trades: {Session.trades}")
    print(f"Best TA profit: {round(100*SequenceTrader.best_exp_profit,5)} %")
    print(ExchangeData.orderbook_updates)
    print(f"Elasped: {round((time.time() - t1)/60, 3)} minutes")
    print("")


if __name__ == "__main__":
    TA.begin(start_cur=starting_cur)
    start_time = time.time()
    while True:
        display_stats(start_time)
        time.sleep(10)
