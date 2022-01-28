import random
import time
from threading import Thread
from typing import final
from statistics import median
from util.currency_funcs import remove_single_swapable_coins
from ArbitrageEngines import SequenceTrader
from util import events  
from enums import tradeSide

class TriangularArbitrageEngine:
    ''' Lightweight abitrage model to generate trade sequences and execute profitable sequences'
        Contains a syncronous execution loop
    '''
    def __init__(self, SequenceTrader:SequenceTrader):
            self.SequenceTrader = SequenceTrader
            self.pregenerated_sequences = {}
            self.thread = None
            events.subscribe(SequenceTrader.START_CUR_CHANGE_EVENT_ID, self.start_cur_change_listener)
    
    def get_viable_pairs(self, check_pair_data=True):
        DataManager = self.SequenceTrader.DataManager
        pairList = remove_single_swapable_coins(list(DataManager.Pairs.keys()))
        if check_pair_data:
            pairList = [pairList for pairList in pairList if DataManager.Pairs[pairList].fee_spread_populated()]
        return tuple(pairList)

    def pregenerate_sequences(self, start_cur, pairList):
        ''' 
        This code is redundant and could be compacted (yes, I know its ugly) but I'm leaving this as is 
        for readability (Sequences will always have a len of 3 for this arbitrage engine) 
        '''

        sequences = []
        start_pairs = [pair for pair in pairList if start_cur in pair]
        for base, qoute in start_pairs:
            if base != start_cur:
                cur_B = base
                S1 = (tradeSide.BUY, (base,qoute))
            elif qoute != start_cur:
                cur_B = qoute
                S1 = (tradeSide.SELL, (base,qoute))

            next_pairs = [pair for pair in pairList if cur_B in pair and start_cur not in pair]
            for base, qoute in next_pairs:
                if base != cur_B:
                    cur_C = base
                    S2 = (tradeSide.BUY, (base,qoute))
                if qoute != cur_B:
                    cur_C = qoute
                    S2 = (tradeSide.SELL, (base,qoute))

                final_pairs = [pair for pair in pairList if cur_C in pair and start_cur in pair]
                if not final_pairs:
                    continue
                for base, qoute in final_pairs:
                    if base != cur_C:
                        S3 = (tradeSide.BUY, (base,qoute))
                    if qoute != cur_C:
                        S3 = (tradeSide.SELL, (base,qoute))
                    sequences.append((S1,S2,S3))
        
        return tuple(sequences)

    def begin(self, start_cur="USDT", population_size=200, loop_delay=.1):
        '''
        Algorithm:
        1. Create pool of randomly generated sequences (of len population sizes)
        2. Calculate profits for all sequences in population
        3. Take the best performing sequences store them -> survivors
        4. Repeat with the previous survivors added into the next population

        '''
        def mainloop():
            self.running = True
            pairList = self.get_viable_pairs(check_pair_data=False)
            sequences = self.pregenerate_sequences(start_cur, pairList)

            x = .9 # Percentile of best performing population members to remember
            survivors = []
            while self.running:
                population = {}
                for _ in range(population_size):
                    sequence = random.choice(sequences)
                    population = {self.SequenceTrader.get_sequence_profit(sequence, autoExecute=True): sequence}
                for seq in survivors:
                    population.update({self.SequenceTrader.get_sequence_profit(sequence, autoExecute=True):seq})
                        
                keys_sorted = sorted(population.keys())
                keys_trimmed = keys_sorted[int(len(keys_sorted)*x):]
                survivors = [population[key] for key in keys_trimmed]

                time.sleep(loop_delay)

        if not self.thread:
            self.thread = Thread(target=mainloop)
            self.thread.start()
    
    def stop(self):
        pass
    
    def start_cur_change_listener(self, new_cur):
        print(f"Changing starting currency to {new_cur}")
        self.survivors = []
        self.begin(start_cur=new_cur)
