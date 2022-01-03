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
kucoinPairs = KucoinAPI.get_tradeable_pairs()
ExchangeData.make_pairs(kucoinPairs, populateSpread=False)

pairsToUse = KucoinAPI.get_tradeable_pairs(tuple_separate=False)[100:400]
KucoinAPI.subscribe_all(pairs=pairsToUse)
KucoinAPI.maintain_connection()

Trader = TradeExecutionModel(KucoinAPI, ExchangeData)
GA1 = GeneticArbitrageModel(6, 400, ExchangeData)


#save_obj(KrakenData.Pairs, "KrakenPairs")
logging.basicConfig(filename='abitrage_datalog.log', level=logging.INFO)

i = 0
GAProfit = 0
seq3prof = []
seq4prof = []
seq5prof = []
winners = load_obj("winning_alts")
t1 = time.time()
t_last_ping = t1
sequence_prev = []
data = {"API":[], "GA":[], "time":[], 'time2':[]}
while True:
    i += 1
    '''
    cmd = input()
    if cmd:
        if cmd.lower() == "show stream":
            KrakenAPI.showDataStream = True  
        if cmd.lower() == "hide stream":
            KrakenAPI.showDataStream = False
        if "add" in cmd.lower():
            KrakenAPI.add_price_stream(cmd.upper())

        cmd = None
    '''
    profits, sequences = GA1.do_evolution()
    
    if profits:
        GAProfit = (max(profits) - 1)*100
        i_max = profits.index(max(profits))
        sequence = sequences[i_max]
        for tuple in sequence:
            if tuple[1][0] not in winners:
                winners.append(tuple[1][0])


        (tradeVerified, (TraderProfit, bids, asks)) = Trader.verify_sequence_profit(sequence, GAProfit, refresh_pairs=True) # Refreshing pairs in here doesn't make snese, do it in the mainloop
        TraderProfit = (TraderProfit - 1)*100
        
        seq_name = list(zip(*sequence))[1]
        logged = ''
        if seq_name != sequence_prev:
            logged = "logged"
            data["API"].append(TraderProfit)
            data['time2'].append((time.time() - t1)/60)
            data["GA"].append(GAProfit)
            data["time"].append((time.time() - t1)/60)
        
        sequence_prev = seq_name

        if len(sequence) >= 3 and False:
            pair1 = GA1.DataManager.Pairs[sequence[0][1]]
            pair2 = GA1.DataManager.Pairs[sequence[1][1]]
            pair3 = GA1.DataManager.Pairs[sequence[2][1]]
            
        
            print(f"Socket data {round(GAProfit,3)} || API data {round(TraderProfit,3)} --  T1:{sequence[0][1]}, u:{round(time.time() - pair1.last_updated,2)}, p:{round(pair1.ask,4)} || p:{round(asks[0],4)}    T2:{sequence[1][1]}, u:{round(time.time() - pair2.last_updated,2)}, p:{round(pair2.ask,4)} || p:{round(asks[1],4)}    T3:{sequence[2][1]}, u:{round(time.time() - pair3.last_updated,2)}, p:{round(pair3.ask,4)} || p:{round(asks[2],4)}")

        updated = [(pair[1], round(time.time() - ExchangeData.Pairs[pair[1]].last_updated, 3)) for pair in sequence]
        print(f"Trader: {round(TraderProfit,3)}, GA: {round(GAProfit,3)}, || {updated}  || {logged}")
        #Trader.verify_sequence_profit(sequence, refresh_pairs=True)


    if i % 500 == 0:
        save_obj(data, f"ProfitComparison")
        save_obj(winners, "winning_alts")

    if GAProfit > 0:
        logging.info(f"Found a profit of {GAProfit}% with a 3 sequence trade after {round((time.time() - t1)/60, 2)} minutes")  
        #save_obj(data, f"ProfitComparison{round(time.time(),2)}")
    
    '''
    now = time.time()
    if now - t_last_ping > KucoinAPI.pingInterval-3:
        KucoinAPI.send_ping()
        t_last_ping = now
    '''

    '''
    print("")
    print(f"Max 3-sequence profit found: {round(profit,3)}%")
    print(f"Avergage 3-sequence profit : {round(sum(seq3prof)/len(seq3prof),3)}%")
    print("")
    
    if max(profits) > 1.01:
        logging.info(f"Found a profit of {profit}% with a 3 sequence trade after {round((time.time() - t1)/60, 2)} minutes")

    GA2 = GeneticArbitrageModel(KrakenData)
    profits = GA2.do_evolution(4, 900)
    profit = (max(profits) - 1)*100
    seq4prof.append(profit)
    print("")
    print(f"Max 4-sequence profit found: {round(profit,3)}%")
    print(f"Avergage 4-sequence profit : {round(sum(seq4prof)/len(seq4prof),3)}%")
    print("")

    if max(profits) > 1.01:
        logging.info(f"Found a profit of {profit}% with a 4 sequence trade after {round((time.time() - t1)/60, 2)} minutes")

    GA3 = GeneticArbitrageModel(KrakenData)
    profits =GA3.do_evolution(5, 900)
    profit = (max(profits) - 1)*100
    seq5prof.append(profit)
    print("")
    print(f"Max 5-sequence profit found: {round(profit,3)}%")
    print(f"Avergage 5-sequence profit : {round(sum(seq5prof)/len(seq5prof),3)}%")
    print("")

    if max(profits) > 1.01:
        logging.info(f"Found a profit of {profit}% with a 5 sequence trade after {round((time.time() - t1)/60, 2)} minutes")

    '''
