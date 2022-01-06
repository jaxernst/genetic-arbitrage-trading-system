from Abstract_ExchangeAPI import ExchangeAPI
from DataManagement import ExchangeData, Coin, Pair
import events
import Config

# https://file.scirp.org/Html/9-9900153_22082.htm

class Execution:
    pass

class TriangularArbitrageExecution(Execution):
    pass


class TriangularArbitrageIdentification:
    '''
    Purpose: Go through crypto currency pairs and identify 
    Everytime a pair's bid or ask gets updated, it should check arbitrage opprtunities with that pair
    '''
    def __init__(self, Data: ExchangeData):
        self.Pairs = Data.Pairs # A list of available pairs to trade
        self.pairList = list(self.Pairs.keys())
        self.init_roundtrip_pairs()
        events.subscribe(Data.pairUpdateEvent, self.pair_update_listener)

    def init_roundtrip_pairs(self):
        # Find all tradeable roundtrip pairs
        self.roundtripPairs = {}
        for pair in self.Pairs:
            if pair not in self.roundtripPairs:
                rountrip_matches = self.get_roundtrip_pairs(pair)
                if rountrip_matches:
                    self.roundtripPairs[pair] = self.get_roundtrip_pairs(pair)
        print(self.roundtripPairs)

    def get_roundtrip_pairs(self, pair: tuple):
        """
        given market A_B, returns an array of all tradeable currencies C if
        the exchange supports markets (A_C or C_A) and (B_C or C_B).
        """
        currencies_found = []
        base = pair[0]
        qoute = pair[1]
        tradeable_currencies = set(sum(self.pairList, ()))
        for cur in tradeable_currencies:
            if (base, cur) in self.Pairs and (qoute, cur) in self.Pairs:
                currencies_found.append(cur)
        return currencies_found

    def pair_update_listener(self, pair):
        ''' When a pair price is updated, '''
        #print(f"Looks like {pair} was updated. Store pair price: {self.Pairs[pair].close}")
        self.find_arbitrage_profits(pair)
        
    def find_arbitrage_profits(self, pair):
        '''Loop over all combinaitons of triangular trades and store the theoretical profit if that trade would be profitable
            Pair: A_B, Assuming I already own A and B 

            Say A is Eth and B is USD

            type1: sell A_C, sell C_B, buy A_B
                   sell Eth/Doge, sell doge/usd, buy eth/usd
                   ==
                   buy doge/eth, buy usd/doge, sell eth/usd

            type2: buy C_B, buy A_C, sell A_B
        '''      
        for cur in self.roundtripPairs[pair]:
            print(f"Checking roundtrip: {pair} with {cur}")
            Pair1 = self.Pairs[pair]
            if (pair[1],cur) in self.pairs:
                Pair2 = self.Pairs[(pair[1],cur)]
            else:
                Pair2 = self.Pairs[(cur, pair[1])]
            if (cur, pair[0]) in self.Pairs:
                Pair2 = self.Pairs[(cur, pair[0])]
            else:
                Pair3 = self.Pairs[(pair[0], cur)]
            
            if all(pair.spread_populated() for pair in [Pair1, Pair2, Pair3]):
                print("Looking for arbitrage trade: {Pair1.base.ticker}_{Pair1.qoute.ticker} to {Pair2.base.ticker}_{Pair2.qoute.ticker} to {Pair3.base.ticker}_{Pair3.qoute.ticker}")
                Profit = TriangularArbitrageProfit(Pair1, Pair2, Pair3, self.Exchange.fees)
                Profit.check_type1_profits()
    
class TriangularArbitrageProfit:
    '''
    Calculates the profits of a triangular arbitrage trade assuming the 
    input Pairs have the most up to date price 
    '''
    def __init__(self, Pair1: Pair, Pair2: Pair, Pair3: Pair, fees = .01):
        '''

        '''  
        self.A_B = Pair1
        
        

    def check_type1_profits(self):
        """
        yes, there is a lot of rendundancy code between check_type1_profits
        and check_type2_profits, but this code is much more readable
        """
        base, alt = self.pair
        tx = 1 - self.fees['taker']
        lo_ask = self.A_B.ask
        count = 0

        # calculate implied hi bid rate
        sell_A_C = self.A_C.bid
        sell_C_B = self.C_B.bid

        # this is how much base we would get if we sold exactly 1 unit of alt
        implied_hi_bid = (sell_A_C * tx) * (sell_C_B * tx)
        # see type2 calculation for explanation
        spread = implied_hi_bid * tx - lo_ask
        if spread > Config.PROFIT_THRESH[alt]:
            count += 1
            print(f"Potential profit: {spread}%")
    
        #if count > 0:
        #    print('detected %d profitable spreads!' % count)
        return (count > 0)

    def check_type2_profits(self):
        base, alt = self.pair
        tx = 1 - self.broker.xchg.trading_fee
        hi_bid = self.broker.get_highest_bid(self.pair)
        count = 0
        for C in self.roundtrip_currencies:
            # calculate implied lo ask rate
            buy_C_B = self.broker.get_lowest_ask((C,alt))
            buy_A_C = self.broker.get_lowest_ask((base,C))
            # how many alts it would REALLY cost me to buy 1 unit of base (i.e. end up with exactly 1 unit of base)
            implied_lo_ask = (buy_C_B * 1.0/tx) * (buy_A_C * 1.0/tx)
            # hi_bid is multiplied by tx one more time because thats how much alts we recv for selling 1 unit of base
            # and subtract from that the amount of alts we pay exactly for 1 unit of base
            spread = hi_bid * tx - implied_lo_ask
            self.type2_spreads[C] = spread
            if spread > config.PROFIT_THRESH[alt]:
                count += 1
        #if count > 0:
        #    print('detected %d profitable spreads!' % count)
        return (count > 0)