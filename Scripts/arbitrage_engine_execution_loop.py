import sys
import os.path
sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir)))

from APIs.KucoinAPI import KucoinAPI
from CustomExceptions import OrderVolumeDepthError
from Modules import GeneticArbitrage, TradeExecution, ExchangeData, TriangularArbitrageEngine
from Modules.Account import Account
from util.obj_funcs import load_obj, save_obj
from util.currency_funcs import remove_single_swapable_coins
from util.SequenceTracker import SequenceTracker
import logging
import time

# Init API and Data Manager
KucoinAPI = KucoinAPI()
ExchangeData = ExchangeData(KucoinAPI)

# Setup pairs for the GA to look at
pairsInfo = KucoinAPI.get_pair_info()
viablePairs = remove_single_swapable_coins(list(pairsInfo.keys()))
pairsInfo = {pair:info for pair, info in pairsInfo.items() if pair in viablePairs}
ExchangeData.make_pairs(pairsInfo, populateSpread=False)
#ExchangeData.build_orderbook()
   
# Setup trade execution Modules
Trader = TradeExecution.SequenceTrader(ExchangeData)

TA = TriangularArbitrageEngine(Trader)

TA.begin("USDT")