import random
from statistics import median
from typing import Tuple
from util.obj_funcs import load_obj
from util.currency_filters import remove_single_swapabble_coins
from Modules.DataManagement import ExchangeData
from Modules.TradeExecution import TradeExecution

class GeneticArbitrage:
    def __init__(self, set_size, DataManager:ExchangeData, Trader: TradeExecution, base_cur="USDT"):
        ''' pairs: ({<pair> (str): (bid, ask), ...}'''
        self.Trader = Trader
        self.DataManager = DataManager
        self.Pairs = DataManager.Pairs # A list of available pairs to trade
        self.pairList = tuple(self.Pairs.keys())
        self.mutation_rate = .05
        self.sequence_lengths = (3,4)
        self.set_size = set_size
        self.base_cur = base_cur
        
    def generate_sequence(self, pairList, vector_length, starting_cur, ending_cur):
        # start with a
        # loop:
        # find currencies tradeable with a
        # choose a currency from that list (b)
        # find pairs tradeable with b
        # b becomes a

        sequence = []
        prev_choice = None
        Cur_A = starting_cur
        for i in range(vector_length-1):
            tradeable_w_A = [pair for pair in pairList if Cur_A in pair]

            if not tradeable_w_A:
                print(f"Couldn't match a tradeable pair with {Cur_A}")
                return

            choice = random.choice(tradeable_w_A)

            if i < vector_length - 2:
                pairList.remove(choice)
            if prev_choice:
                pairList.append(prev_choice)

            prev_choice = choice

            if Cur_A == choice[0]: # Owned cur on top
                Cur_B = choice[1]
                # sell the owned cur for the next cur
                sequence.append(("sell", (Cur_A, Cur_B)))
            elif Cur_A == choice[1]:
                Cur_B = choice[0]
                # buy the next cur for the owned cur
                sequence.append(("buy", (Cur_B, Cur_A)))
            else:
                raise Exception("Fatal error occured during arbitrage sequence generation")
            Cur_A = Cur_B

        if ending_cur != Cur_A:
            if (Cur_A, ending_cur) in pairList:
                sequence.append(("sell", (Cur_A, ending_cur)))
            elif (ending_cur, Cur_A) in pairList:
                sequence.append(("buy", (ending_cur, Cur_A)))
            else:
                return self.generate_sequence(pairList, vector_length, starting_cur, ending_cur)
        
        return sequence

    def choose_pregenerated_sequence(self):
        pass

    def cleanup_pairList(self):
        # Return pairs from pairlist if spread is not populated
        pairList = [pair for pair in self.pairList if self.DataManager.Pairs[pair].fee_spread_populated()]
        
        #except KeyError:
        #    # Change this later
        #    last_banned = load_obj("banned_coins")[-1]
        #    self.pairList = tuple([pair for pair in self.pairList if last_banned not in pair])
        #    pairList = [pair for pair in self.pairList if self.DataManager.Pairs[pair].fee_spread_populated()]
        
        if not pairList:
            return []
        
        # Removes coins with only a single qoute currency
        out_list = remove_single_swapabble_coins(pairList)
        return out_list

    def do_evolution(self) -> Tuple[float, Tuple[str]]:
        ''' Generates sequences, evaluates their performance, then kills off the poorest performers '''
    
        cleaned_pairs = self.cleanup_pairList() # Removes pairList pairs if there is only one qoute currency
        if len(cleaned_pairs) < 100:
            return (None, None)
        
        # Get first generation of sequences
        population = [self.generate_sequence(cleaned_pairs, random.choice(self.sequence_lengths), self.base_cur, self.base_cur) for _ in range(self.set_size)]

        while len(population) > 2:
            # Evaluate sequences
            profits = [self.Trader.get_sequence_profit(sequence)[0] for sequence in population if sequence]
            
            # Take the best
            i = profits.index(max(profits))
            best = population[i]

            # Filter out bottom 50%
            filtered_population = [sequence for sequence, profit in zip(population,profits) if profit > median(profits)]
            
            # Recombine to form new sequences
            population = self.recombine_sequences(filtered_population)
            
            if not population:
                population.append(best)
                population = prev_population
                break

            # Mutate
            for i, sequence in enumerate(population):
                if random.random() < self.mutation_rate:
                    i_rand = random.randint(1,len(sequence)-2)
                    cutoff_sequence = sequence[:i_rand]
                    if "buy" in cutoff_sequence[-1][0]:
                        owned = cutoff_sequence[-1][1][0]
                    else:
                        owned = cutoff_sequence[-1][1][1]  
                    
                    mutated = cutoff_sequence + self.generate_sequence(cleaned_pairs, 
                                                                       len(sequence) - len(cutoff_sequence), 
                                                                       starting_cur=owned, 
                                                                       ending_cur=self.base_cur)
                    population[i] = mutated
            
            population.append(best)
            prev_population = population
        
        final_profits = [self.Trader.get_sequence_profit(sequence)[0] for sequence in population]
        profit_max = max(final_profits)
        i_max = final_profits.index(profit_max)
        sequence = population[final_profits.index(profit_max)]
        return (profit_max, population[i_max])

    def recombine_sequences(self, sequences):
        duplicate_attempts = 0
        attempted = []
        children = []
        while len(sequences) > 1 and duplicate_attempts < 200:
            # Choose two at random (remove chosen from list)
            parent1 = random.choice(sequences)
            sequences.remove(parent1)

            parent2 = random.choice(sequences)
            sequences.remove(parent2)

            if (parent1, parent2) in attempted:
                duplicate_attempts += 1
                #print(duplicate_attempts)
                continue

            # Check if any of the parents own the same  currency at the same index
            i_swap = None
            i = 1
            for p1, p2 in zip(parent1[:-2], parent2[:-2]):
                if "buy" in p1[0]:
                    p1_owned = p1[1][0]
                else: 
                    p1_owned = p1[1][1]
                if "buy" in p2[0]:
                    p2_owned = p2[1][0]
                else:
                    p2_owned = p2[1][1]
                
                if p2_owned == p1_owned: # Parents own same coin at this index
                    i_swap = i
                    break
                i += 1
            
            # Swap at that index
            if i_swap:
                child1 = parent1[:i_swap] + parent2[i_swap:]
                child2 = parent2[:i_swap] + parent2[i_swap:]
                if child1 not in children:
                    children.append(child1)
                if child2 not in children:
                    children.append(child2)
                if self.check_illegal_sequences(children):
                    raise Exception("Illegal sequence detected")
            else:
                attempted.append((parent1,parent2))
                sequences.append(parent1)
                sequences.append(parent2)
        
        return  children

    def check_illegal_sequences(self, sequences): # Testing funciton
        for sequence in sequences:
            for i in range(len(sequence)-1):
                first_coin_in_next = sequence[i][1][0] in sequence[i+1][1][0] or sequence[i][1][0] in sequence[i+1][1][1]
                second_coin_in_next = sequence[i][1][1] in sequence[i+1][1][0] or sequence[i][1][1] in sequence[i+1][1][1]
                if not first_coin_in_next:
                    if not second_coin_in_next:
                        return True

                if sequence[i][0] == "buy":
                    owned = sequence[i][1][0]
                    if sequence[i+1][0] == "sell":
                        valid = owned == sequence[i+1][1][0]
                    else:
                        valid = owned == sequence[i+1][1][1]
                else:
                    if sequence[i+1][0] == "sell":
                        valid = sequence[i][1][1] == sequence[i+1][1][0]
                    else:
                        valid = sequence[i][1][1] == sequence[i+1][1][1]
                if not valid:
                    return True
        return False

   
