import pickle

from TradeExecutionModel import TradeExecutionModel
from GeneticArbitrageModel import GeneticArbitrageModel
from KrakenAPI import KrakenAPI
from DataManagement import ExchangeData
from util import *

'''
Pairs = load_obj("KrakenPairs2")
KrakenAPI = KrakenAPI()
KrakenData = ExchangeData(KrakenAPI)
#krakenPairs = KrakenAPI.get_tradeable_pairs()
#KrakenData.make_pairs(krakenPairs, populateSpread=True)

KrakenData.Pairs = Pairs
GA = GeneticArbitrageModel(KrakenData) 
print(GA.do_evolution(3,500))

'''

import requests
import json
from WebSocketClient import WebSocketClient
from KucoinAPI import KucoinAPI
from uuid import uuid4

KC = KucoinAPI()
KC.socket.connect()
