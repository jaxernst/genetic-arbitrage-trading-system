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
viablePairs = remove_single_swapabble_coins(list(pairsInfo.keys()))[:299]
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
# Tracker = SequenceTracker(5)


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
        GAprofit, sequence = GA1.do_evolution()
        #print(GAprofit)
        if GAprofit:
            GAprofits.append(GAprofit)
            #profit = Trader.execute_sequence(sequence, Session)
            if GAprofit > 0:
                #print("GAprofit found")

                print(f"Potential trade found -- Profit: {round(GAprofit*100, 6)} % || Sequence: {sequence}")

                try:
                    pass
                    #profit = Trader.execute_sequence(sequence, Session)
                except OrderVolumeDepthError:
                    continue


            i += 1
            if i % 50 == 0:
                print("")
                print(f"Session balance: {round(Session.balance['USDT'],3)}")
                print(f"Percentage Gain: {round(100*Session.PL, 3)} %")
                print(f"Account balance: {round(Account.balance['USDT'],3)}")
                print(f"Number of trades: {Session.trades}")
                print(f"Best GA profit: {round(100*max(GAprofits),5)} %")
                print(f"Best Real profit: {round(100*max(RealProfits),5)} %")
                print(ExchangeData.orderbook_updates)
                if sequence_lengths:
                    print(f"Average profitable sequence length: {sum(sequence_lengths) / len(sequence_lengths)}")
                print(f"Elasped: {round((time.time() - t1)/60, 3)} minutes")
                print("")

        time.sleep(.05)

