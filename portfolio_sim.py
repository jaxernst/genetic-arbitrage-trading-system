
from APIs import KrakenAPI, KucoinAPI
from Models import GeneticArbitrageModel, TradeExecutionModel, ExchangeData
from util.obj_funcs import load_obj, save_obj
import logging
import time

'''
KrakenAPI = KrakenAPI()
ExchangeData = ExchangeData(KrakenAPI)
ExchangeData.base_fee = .0026
krakenPairs = KrakenAPI.get_tradeable_pairs()
ExchangeData.make_pairs(krakenPairs, populateSpread=False)
KrakenAPI.subscribe_all()
Trader = TradeExecutionModel(KrakenAPI, ExchangeData)
GA1 = GeneticArbitrageModel(4, 400, ExchangeData)
'''

KucoinAPI = KucoinAPI()
ExchangeData = ExchangeData(KucoinAPI)
ExchangeData.base_fee = .0010

tuplePairs = KucoinAPI.get_tradeable_pairs(tuple_separate=True)[50:350]
pairsToUse = KucoinAPI.get_tradeable_pairs(tuple_separate=False)[50:350]
ExchangeData.make_pairs(tuplePairs, populateSpread=False)

KucoinAPI.subscribe_all(pairs=pairsToUse)
KucoinAPI.maintain_connection()

# Setup account
Account = KucoinAPI.get_portfolio()
Account.deposit_fiat(1000) # Put in $100
Session = Account.start_trading_session("USDT", max_allocation=.5)
starting_bal = 1000

# Setup trade execution models
Trader = TradeExecutionModel(KucoinAPI, ExchangeData)

# Setup arbitrage model
sequence_length = 4
set_size = 400
GA1 = GeneticArbitrageModel(sequence_length, set_size, ExchangeData)

sequence_prev =[]
seq_name = ""
last_traded = []
winners = load_obj("winning_alts")
i = 0
trades = 0
while True:
    GAprofit, sequence = GA1.do_evolution()
    if sequence:
        seq_name = list(zip(*sequence))[1]
    if GAprofit:
        if GAprofit > -.001:
            print(round(GAprofit, 5))

    if GAprofit and seq_name != sequence_prev: # If new sequence has been found:
        profit = Trader.execute_sequence(sequence, Session, ExchangeData)
        if GAprofit > 0:
            print(f"Potential trade found -- Profit: {round(GAprofit*100, 3)} % || Sequence: {seq_name}")
        
            profit = Trader.execute_sequence(sequence, Session, ExchangeData)
            print(f"Real profit: {round(profit-1, 5)}")
            Account.balance["USDT"] *= 1 + profit
            if profit-1 > 0 and sequence != last_traded:
                print("=========================")
                print("Executing Trade")
                print("=========================")
                bal_0 = Account.balance
                trades += 1
                Trader.execute_sequence(sequence, profit* 1 - .0001, Session)
                bal_1 = Account.balance
                print( "")
                print(f"Account balance increased by {round(bal_1 - bal_0,3)} %")
                print("")
                print("=================")
                last_traded = sequence
            else:
                print("Trade not verified")
        
        for tuple in sequence:
            if tuple[1][0] not in winners:
                print(f"appending:{tuple[1][0]}")
                winners.append(tuple[1][0])

    sequence_prev = seq_name
    i += 1
    time.sleep(.05)

    if i % 500 == 0:
        save_obj(winners, "winning_alts")

    if i % 150 == 0:
        print("")
        print(f"Current balance: {round(Account.balance['USDT'],3)}")
        print(f"Percentage Gain: {round(100*(Account.balance['USDT'] - starting_bal)/starting_bal, 3)} %")
        print(f"Number of trades: {trades}")
        print("")



