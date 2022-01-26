import sys
import os.path
sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir)))

from Modules import DataManagement, GeneticArbitrage, SequenceTrader, ExchangeData, TriangularArbitrageEngine
from Modules.Session import Session
from APIs import KrakenAPI, KucoinAPI
from CustomExceptions import OrderVolumeDepthError
from Modules.Account import Account
from util.obj_funcs import load_obj, save_obj
from util.currency_funcs import remove_single_swapable_coins
from util.SequenceTracker import SequenceTracker
import random
import logging
from threading import Thread
import time

SIMULATION_MODE = False

# Init API and Data Manager
KucoinAPI = KucoinAPI()
ExchangeData = ExchangeData(KucoinAPI)

# Setup account and trading session
Account = Account(KucoinAPI)
starting_cur, amount = Account.get_largest_holding(check_limit=3)
Session = Session(Account, simulated=False)

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
sequences = TA.pregenerate_sequences(starting_cur, list(ExchangeData.Pairs.keys()))
sequence = random.choice(sequences)
a = SequenceTrader.get_sequence_profit(sequence, forceExecute=True)
       
print(a)
