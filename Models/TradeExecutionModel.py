from dataclasses import dataclass
from typing import Dict
from APIs.abstract import ExchangeAPI
from Models import DataManagementModel, ExchangeData, Pair
import time

@dataclass
class Session:
    balance: float # Amount of money given to the trading session
    base_cur: str # Currency which the balance is currently in
    trades: int = 0 # Number of trades executed during this session
    p_l: float = 1 # Current profit loss for the session
    average_gain: float = None 


class TradeExecutionModel:
    # Interfaces with the API to execute trades
    # Determines how much sequence volume can be traded based on order book
    def __init__(self, API:ExchangeAPI, DataManager:ExchangeData):
        self.API =  API
        self.last_call = None # Data from the last API call]
        self.DataManager = DataManager

    def get_real_fill_price(self, trade_type, owned_amount, book_prices, book_sizes, p_guess=None):
        ''' Calculate the real fill price to purchase/sell a currency with the amount of funds available'''
        convergence_tol = .001 # The test_volume has to be within .5% of the real_volume
        book_prices = [float(p) for p in book_prices]
        book_sizes = [float(s) for s in book_sizes]
        
        if len(book_prices) != len(book_sizes):
            raise Exception("Book sizes and prices mmust be the same length")
        
        if not p_guess:
            p_guess = float(book_prices[0]) 

        # Check how many price levels are required to cover the test_volume
        if trade_type == "buy":
            test_volume = owned_amount / p_guess # How much currency to buy
        if trade_type == "sell":
            test_volume = p_guess * owned_amount  # How much currency to sell

        i = 0
        while sum(book_sizes[:i+1]) < test_volume:
            i += 1
            if i > len(book_sizes):
                raise Exception("Volume depth is not enough to cover required volume (You must be a damn whale)")

        # determine the average fill price
        remaining_volume = (test_volume - sum(book_sizes[:i]))
        fill_price = (sum([price*vol for price,vol in zip(book_prices[:i], book_sizes[:i])]) + remaining_volume*book_prices[i]) / (test_volume)
        real_volume = owned_amount / fill_price
        
        print('iter')
        # Check that the real volume can be covered by the same depth as the test volume
        if abs((real_volume - test_volume)/test_volume) < convergence_tol:
            return fill_price
        else:
            return self.get_real_fill_price(trade_type, owned_amount, book_prices, book_sizes, p_guess=fill_price)

    def get_real_sequence_profit(self, sequence, owned_amount=None, refresh_pairs=False, Pairs: Dict[tuple, Pair]=None):
        ''' Check is the sequence matches the expected profit to within a specified tolerance
            If a volume is specified, it will return the average fill price
        '''
        fee = self.DataManager.base_fee
        total = 1
        orderbook = self.API.get_multiple_orderbooks(list(zip(*sequence))[1])

        for type, pair in sequence:
            tx = 1 - fee

            if refresh_pairs:
                Pairs[pair].bid = orderbook[pair]['bids'][0][0]
                #Pairs[pair].bids = orderbook[pair]['bids'][0]
                Pairs[pair].ask = orderbook[pair]['asks'][0][0]
                #Pairs[pair].asks = orderbook[pair]['asks'][0]
                Pairs[pair].last_updated = time.time()

            if type == "buy":
                book_prices, book_sizes = list(zip(*orderbook[pair]['asks']))
                fill_price = self.get_real_fill_price(type, owned_amount, book_prices, book_sizes)

                total *= (1/float(fill_price))*tx
                owned_amount = total
                
            elif type == "sell":
                # Treat this as a buy, 
                book_prices, book_sizes = list(zip(*orderbook[pair]['bids']))
                fill_price = self.get_real_fill_price(type, owned_amount, book_prices, book_sizes)

                total *= float(fill_price)*tx
                owned_amount = total
            else:
                raise Exception("Ivalid sequence format")
        if total > 1.5:
            raise Exception("Too good, something went wrong")
        
        return total
    
    def execute_sequence(self, sequence, Session: Session, ExchangeData:ExchangeData):
        
        # Get the expected owned currency from the first sequence pair and confirm we have that currency available in our session
        type, pair = sequence[0]
        if type == "buy":
            owned = pair[1]
        elif type == "sell":
            owned = pair[0]
        
        if owned in Session.base_cur:
            max_tradeable_volume = float(Session.balance)
        else:
            raise Exception("The activate trading Session does not own anof the required currency to trade the squence")

        # Verify the trade is still profitable with the volume sized real fill price
        profit_factor = self.get_real_sequence_profit(sequence, max_tradeable_volume, refresh_pairs=True, Pairs=ExchangeData.Pairs)

        # Execute trades
        Session.balance *= profit_factor
        return profit_factor

    def log_trade(self, trade_info):
        #self.Account.Session.trades += 1
        pass
    
    def execute_trade(type, pair, amount):
        pass
 


 # Say sequence is ETH/USD, ETH/BTC, BTC,USD
 # Start with 100 usd
 # I need to buy x amount of ETH for all 100 dollars (that is price ETH/amount usd owned)
 # Need to know the price of ETH --> start with the best ask 
 # Est. Volume of ETH to trade is best ask/amount_owned
 # Now check if this volume is covered by the best ask size
 # If it is, continue
 # Else, check how many price steps up we have to go up to cover the volume at the best ask