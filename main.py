from APIs import KrakenAPI, KucoinAPI
from CustomExceptions import OrderVolumeDepthError
from Modules import GeneticArbitrage, TradeExecution, ExchangeData, Session
from Modules.Portfolio import Portfolio
from util.obj_funcs import load_obj, save_obj
from util.SequenceTracker import SequenceTracker
import logging
import time

KucoinAPI = KucoinAPI()
ExchangeData = ExchangeData(KucoinAPI)
ExchangeData.base_fee = .0010

tuplePairs = KucoinAPI.get_tradeable_pairs(tuple_separate=True)[50:350]
pairsToUse = KucoinAPI.get_tradeable_pairs(tuple_separate=False)[50:350]
ExchangeData.make_pairs(tuplePairs, populateSpread=False)

KucoinAPI.subscribe_all(pairs=pairsToUse)
KucoinAPI.maintain_connection()

# Setup account
funding_cur = "USDT"
starting_bal = 1000
min_volume = 100
Account = KucoinAPI.get_portfolio()
Account.deposit_fiat(starting_bal)
Session = Session(Account, KucoinAPI, Account.balance[funding_cur], funding_cur, min_volume) # The session will update the parent account 

# Setup trade execution Modules
Trader = TradeExecution(KucoinAPI, ExchangeData)

# Setup arbitrage 
sequence_length = 3
set_size = 700
GA1 = GeneticArbitrage(sequence_length, set_size, ExchangeData)

# Setup sequence tracker (remember sequences)
Tracker = SequenceTracker(5)
seq_name = ""
last_traded = []
GAprofits = []
sequence_lengths = []
RealProfits = [-100]
winners = load_obj("profitable_alts")
t1 = time.time()
i = 0
trades = 0
while True:
    GAprofit, sequence = GA1.do_evolution()
    if GAprofit:
        GAprofits.append(GAprofit)
        #profit = Trader.execute_sequence(sequence, Session)
        if GAprofit > 0:
            if sequence not in Tracker.recents:
                print(f"Potential trade found -- Profit: {round(GAprofit*100, 6)} % || Sequence: {sequence}")
                Tracker.remember(sequence)
            
                try:
                    profit = Trader.execute_sequence(sequence, Session)
                except OrderVolumeDepthError:
                    continue

                RealProfits.append(profit)
                print(f"Real profit: {round(profit, 5)}")
                
                if not profit > 0:
                    print("Trade not verified")
                else:
                    sequence_lengths.append(len(sequence))

                for tuple in sequence:
                    if tuple[1][0] not in winners:
                        print(f"appending:{tuple[1][0]}")
                        winners.append(tuple[1][0])

        Tracker.update_recents()
        i += 1

        if i % 1000 == 0:
            print("")
            print(f"Session balance: {round(Session.balance['USDT'],3)}")
            print(f"Account balance: {round(Account.balance['USDT'],3)}")
            print(f"Percentage Gain: {round(100*Session.PL, 3)} %")
            print(f"Number of trades: {Session.trades}")
            print(f"Best GA profit: {round(100*max(GAprofits),5)} %")
            print(f"Best Real profit: {round(100*max(RealProfits),5)} %")
            if sequence_lengths:
                print(f"Average profitable sequence length: {sum(sequence_lengths) / len(sequence_lengths)}")
            print(f"Elasped: {round((time.time() - t1)/60, 3)} minutes")
            print("")

    time.sleep(.05)

