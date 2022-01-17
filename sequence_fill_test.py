from APIs import KrakenAPI, KucoinAPI
from CustomExceptions import OrderVolumeDepthError
from Modules import GeneticArbitrage, TradeExecution, ExchangeData, SessionSim, SessionLive
from Modules.Portfolio import Portfolio
from util.obj_funcs import load_obj, save_obj
from util.currency_filters import remove_single_swapabble_coins
from util.SequenceTracker import SequenceTracker
import logging
import time

SIMULATION_MODE = False

# Init API and Data Manager
KucoinAPI = KucoinAPI()
ExchangeData = ExchangeData(KucoinAPI)

# Setup pairs for the GA to look at
pairsInfo = KucoinAPI.get_pair_info()
viablePairs = remove_single_swapabble_coins(list(pairsInfo.keys()))[:200]
pairsInfo = {pair:info for pair, info in pairsInfo.items() if pair in viablePairs}
ExchangeData.make_pairs(pairsInfo, populateSpread=False)
ExchangeData.build_orderbook()
KucoinAPI.maintain_connection()

# Setup account
funding_cur = "USDT"

min_volume = 100
Account = KucoinAPI.get_portfolio()

if SIMULATION_MODE:
    Session = SessionSim(Account, KucoinAPI, Account.balance[funding_cur], funding_cur, 5) # The session will update the parent account 
else:
    Session = SessionLive(Account, KucoinAPI, ExchangeData, Account.balance[funding_cur], funding_cur, 5) # The session will update the parent account 
   
# Setup trade execution Modules
Trader = TradeExecution(KucoinAPI, ExchangeData, Session, simulation_mode=SIMULATION_MODE)

# Setup arbitrage model
sequence_length = 3
set_size = 500
GA1 = GeneticArbitrage(sequence_length, set_size, ExchangeData, Trader, base_cur=funding_cur)

# Setup sequence tracker (remember sequences)
Tracker = SequenceTracker(5)


seq_name = ""
last_found = None
GAprofits = []
sequence_lengths = []
RealProfits = [-100]
winners = load_obj("profitable_alts")
t1 = time.time()
i = 0
trades = 0

if __name__ == "__main__":
    
    while True:
        cleaned_pairs = GA1.cleanup_pairList()
        sequence = GA1.generate_sequence(cleaned_pairs, 3, funding_cur, funding_cur)
        profit, fills = Trader.get_sequence_profit(sequence)
        Trader.execute_sequence(sequence, Session.balance[funding_cur], fills, exp_profit=profit)
        time.sleep(10)
        
       

