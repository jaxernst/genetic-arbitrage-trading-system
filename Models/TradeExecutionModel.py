from dataclasses import dataclass
from typing import Dict
import time

from APIs.abstract import ExchangeAPI
from Models import DataManagementModel, ExchangeData, Pair
from Models.PortfolioModel import Portfolio
from util.obj_funcs import save_obj, load_obj
from CustomExceptions import OrderVolumeDepthError, TooManyRequests


class Session:
    def __init__(self, parent_account:Portfolio, funding_balance:float, funding_cur:str, min_volume:int):
        self.Account = parent_account

        if funding_balance <= 0:
            raise Exception("Funding blance cannot be negative or zero")

        self.starting_balance = funding_balance
        self.starting_cur = funding_cur
        self.min_volume = min_volume # minimum amount of volume that can be traded in funding cur

        self.balance = funding_balance # Amount of money given to the trading session in base currency
        self.cur_owned = funding_cur # Currency which the balance is currently in
        self.trades = 0 # Number of trades executed during this session
        self.PL = 0 # Current profit loss for the session
        self.average_gain = None

    def buy_market(self, API:ExchangeAPI, pair:Pair, exp_fill, fee):
        ''' Use fuill balance to buy pair at market
            Session has no knowledge of fees, so exp_fill must be fee adjusted
        '''
        if pair.qoute != self.cur_owned or pair.qoute not in self.Account.balance:
            raise Exception(f"{pair.qoute} needs to be held in order to buy {pair.sym}")
    
        # Send a buy order to the API
        # API.buy_market(pair, self.balance)
        self.trades += 1
        
        # Using all the balance and converting it to another currency, so take away the current balance from the parent account
        self.Account.balance[pair.qoute] -= self.balance

        # Update amount of new currency owned
        self.balance *= (1 / exp_fill) * (1 - fee)
        self.cur_owned = pair.base
        
        # Add the balance of the new currency in the parent account
        if pair.base not in self.Account.balance:
            self.Account.balance[pair.base] = self.balance
        else:
            self.Account.balance[pair.base] += self.balance

    def sell_market(self, API:ExchangeAPI, pair:Pair, exp_fill, fee): 
        ''' Use full balance to sell pair at market
            Session has no knowledge of fees, so exp_fill must be fee adjusted
        '''
        if pair.base != self.cur_owned or pair.base not in self.Account.balance:
            raise Exception("{pair.base} needs to be held in order to sell {pair.sym}")

        # Send a sell order to the API
        # API.buy_sell(pair, self.balance)
        self.trades += 1
        
        # Using all the balance and converting it to another currency, so take away the current balance from the parent account
        self.Account.balance[pair.base] -= self.balance

        # Update amount of new currency owned
        self.balance *= exp_fill * (1 - fee)
        self.cur_owned = pair.qoute
        
        # Add the balance of the new currency in the parent account
        if pair.qoute not in self.Account.balance:
            self.Account.balance[pair.qoute] = self.balance
        else:
            self.Account.balance[pair.qoute] += self.balance

    def update_PL(self):
        self.PL = (self.balance - self.starting_balance) / self.starting_balance
        

class TradeExecutionModel:
    # Interfaces with the API to execute trades
    # Determines how much sequence volume can be traded based on order book
    def __init__(self, API:ExchangeAPI, DataManager:ExchangeData):
        self.API =  API
        self.last_call = None # Data from the last API call]
        self.DataManager = DataManager
        self.profit_tolerance = .0005

    def get_real_fill_price_buy(self, trade_type, owned_amount, book_prices, book_sizes, coin_name, p_guess=None):
        ''' Calculate the real fill price to purchase/sell a currency with the amount of funds available'''
        convergence_tol = .001 # The test_volume has to be within .5% of the real_volume
        book_prices = [float(p) for p in book_prices]
        book_sizes = [float(s) for s in book_sizes]
        
        if len(book_prices) != len(book_sizes):
            raise Exception("Book sizes and prices mmust be the same length")
        
        if not p_guess:
            p_guess = float(book_prices[0]) 

        # Check how many price levels are required to cover the test_volume
        test_volume = owned_amount / p_guess # How much currency to buy

        i = 0
        while sum(book_sizes[:i+1]) < test_volume:
            i += 1
            if i > len(book_sizes):
                raise OrderVolumeDepthError(coin_name)

        # determine the average fill price
        remaining_volume = (test_volume - sum(book_sizes[:i]))
        fill_price = (sum([price*vol for price,vol in zip(book_prices[:i], book_sizes[:i])]) + remaining_volume*book_prices[i]) / (test_volume)
        
        real_volume = owned_amount / fill_price
        
        # Check that the real volume can be covered by the same depth as the test volume
        if abs((real_volume - test_volume)/test_volume) < convergence_tol:
            return fill_price
        else:
            return self.get_real_fill_price_buy(trade_type, owned_amount, book_prices, book_sizes, coin_name, p_guess=fill_price)

    def get_real_fill_price_sell(self, trade_type, owned_amount, book_prices, book_sizes, coin_name, p_guess=None):
        ''' Calculate the real fill price to purchase/sell a currency with the amount of funds available'''
        convergence_tol = .001 # The test_volume has to be within .5% of the real_volume
        book_prices = [float(p) for p in book_prices]
        book_sizes = [float(s) for s in book_sizes]
        
        if len(book_prices) != len(book_sizes):
            raise Exception("Book sizes and prices mmust be the same length")
        
        if not p_guess:
            p_guess = float(book_prices[0]) 

        # Check how many price levels are required to cover the test_volume
        test_volume = p_guess * owned_amount # How much currency to buy

        i = 0
        while sum(book_sizes[:i+1]) < test_volume:
            i += 1
            if i > len(book_sizes):
                raise OrderVolumeDepthError(coin_name)

        # determine the average fill price
        remaining_volume = (test_volume - sum(book_sizes[:i]))
        fill_price = (sum([price*vol for price,vol in zip(book_prices[:i], book_sizes[:i])]) + remaining_volume*book_prices[i]) / (test_volume)
        
        real_volume = fill_price * owned_amount
        
        # Check that the real volume can be covered by the same depth as the test volume
        if abs((real_volume - test_volume)/test_volume) < convergence_tol:
            return fill_price
        else:
            return self.get_real_fill_price_sell(trade_type, owned_amount, book_prices, book_sizes, coin_name, p_guess=fill_price)    
    
    def get_real_sequence_profit(self, sequence, owned_amount=None, update_orderbook=False, Pairs: Dict[tuple, Pair]=None):
        ''' Check is the sequence matches the expected profit to within a specified tolerance
            If a volume is specified, it will return the average fill price
        '''
        fee = self.DataManager.base_fee
        total = 1
        
        if update_orderbook:
            try:
                orderbook = self.API.get_multiple_orderbooks(list(zip(*sequence))[1])
            except TooManyRequests:
                time.sleep(.5)
                print("Orderbook requests occurring too rapidly...")
                orderbook = self.API.get_multiple_orderbooks(list(zip(*sequence))[1])
            
            for pair in orderbook:
                Pairs[pair].bid = orderbook[pair]['bids'][0][0]
                Pairs[pair].ask = orderbook[pair]['asks'][0][0]
                Pairs[pair].orderbook = orderbook[pair]
                Pairs[pair].last_updated = time.time()

        exp_fills = []

        for type, pair in sequence:
            tx = 1 - fee
            if type == "buy":
                book_prices, book_sizes = list(zip(*Pairs[pair].orderbook['asks']))
                fill_price = self.get_real_fill_price_buy(type, owned_amount, book_prices, book_sizes, pair[0])

                exp_fills.append(fill_price)
                total *= (1/float(fill_price))*tx
                owned_amount = total
                
            elif type == "sell":
                # Treat this as a buy, 
                book_prices, book_sizes = list(zip(*Pairs[pair].orderbook['bids']))
                fill_price = self.get_real_fill_price_sell(type, owned_amount, book_prices, book_sizes, pair[0])
                
                exp_fills.append(fill_price)
                total *= float(fill_price)*tx
                owned_amount = total
            else:
                raise Exception("Ivalid sequence format")
        if total > 1.5:
            raise Exception("Too good, something went wrong")
        
        return total - 1, exp_fills
    
    def execute_sequence(self, sequence, Session: Session, ExchangeData:ExchangeData):
        
        # Get the expected owned currency and confirm we have that currency available in our session
        type, pair = sequence[0]
        if type == "buy":
            exp_owned = pair[1]
        elif type == "sell":
            exp_owned = pair[0]
        
        # Get max volume from session
        if exp_owned in Session.cur_owned:
            max_tradeable_volume = float(Session.balance)
        else:
            raise Exception("The activate trading Session does not own any of the required currency to trade the squence")

        # Verify the trade is still profitable with the volume sized real fill price
        profit, exp_fills = self.get_real_sequence_profit(sequence, max_tradeable_volume, update_orderbook=True, Pairs=ExchangeData.Pairs)
        
        trade_volume = max_tradeable_volume
        test_volume_scale_factor = .75
        while profit < self.profit_tolerance and trade_volume > Session.min_volume:
            print(f"Trade not profitable with {trade_volume} units. Trying with {round(trade_volume*test_volume_scale_factor)} units")
            trade_volume = round(trade_volume*test_volume_scale_factor)
            profit, exp_fills = self.get_real_sequence_profit(sequence, trade_volume, update_orderbook=False, Pairs=ExchangeData.Pairs)
            
        if profit < self.profit_tolerance:
            return profit

        # Execute trades
        print("========= Executing Sequence =========")
        starting_bal = Session.starting_balance
        Session.balance = trade_volume
        for i, trade in enumerate(sequence):
            type, pair = trade
            ''' Will be updated so sequence will already store pair objects (so they don't need to be created here'''
            if type == "buy":
                Session.buy_market(self.API, Pair(pair[0], pair[1]), exp_fills[i], self.DataManager.base_fee)
            if type == "sell":
                Session.sell_market(self.API, Pair(pair[0], pair[1]), exp_fills[i], self.DataManager.base_fee)
        
        Session.balance += max_tradeable_volume - trade_volume
        Session.update_PL() 
        ending_bal = Session.balance

        actual_profit = (ending_bal - starting_bal) / starting_bal
        if round(actual_profit, 10) != round(profit, 10):
            print(f"Actual profit: {actual_profit}, exp_profit: {profit}")
            raise Exception("Profits do not match from what was calulcated in Session and get_real_sequence_profit()")
        
        print(f"Yield:  {round(actual_profit, 5)}")
        return profit

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