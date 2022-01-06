from dataclasses import dataclass
from typing import Dict
import time

from APIs.abstract import ExchangeAPI
from Modules import DataManagement, ExchangeData, Pair
from Modules.Portfolio import Portfolio
from util.obj_funcs import save_obj, load_obj
from CustomExceptions import OrderVolumeDepthError, TooManyRequests


class Session:
    def __init__(self, parent_account:Portfolio, API:ExchangeAPI, funding_balance:float, funding_cur:str, min_volume:int):
        self.Account = parent_account
        self.API = API
        if funding_balance <= 0:
            raise Exception("Funding balance cannot be negative or zero")

        self.starting_balance = funding_balance
        self.starting_cur = funding_cur
        self.min_volume = min_volume # minimum amount of volume that can be traded in funding cur

        self.balance = {funding_cur:funding_balance} # Amount of money given to the trading session in base currency
        self.trades = 0 # Number of trades executed during this session
        self.PL = 0 # Current profit loss for the session
        self.average_gain = None
        
    def buy_market(self, pair:tuple, amount, exp_fill, fee):
        ''' Use fuill balance to buy pair at market
            Session has no knowledge of fees, so exp_fill must be fee adjusted
        '''
        base, qoute = pair
        tx = 1 - fee

        if qoute not in self.balance or qoute not in self.Account.balance:
            print(self.balance)
            raise Exception(f"{qoute} needs to be held in order to buy {pair}")
    
        # Send a buy order to the API
        # API.buy_market(pair, self.balance)
        self.trades += 1
        
        # Update Account/Session's balance of the qoute currency (cost)
        self.Account.balance[qoute] -= amount
        self.balance[qoute] -= amount

        # Update Session's balance of the base currency (buying)
        new_amount = amount * (1/exp_fill) * tx
        if base in self.balance:
            self.balance[base] += new_amount
        else:
            self.balance[base] = new_amount
        
        # Update Account's balance of the base currency (buying)
        if base in self.Account.balance:
            self.Account.balance[base] += new_amount
        else:
            self.Account.balance[base] = new_amount

        return new_amount

    def sell_market(self, pair:tuple, amount, exp_fill, fee): 
        ''' Use full balance to sell pair at market
            Session has no knowledge of fees, so exp_fill must be fee adjusted
        '''
        base, qoute = pair
        tx = 1 - fee

        if base not in self.balance or base not in self.Account.balance:
            raise Exception(f"{base} needs to be held in order to sell {pair}")
    
        # Send a buy order to the API
        # API.buy_market(pair, self.balance)
        self.trades += 1
        
        # Update Account/Session's balance of the base currency (selling)
        self.Account.balance[base] -= amount
        self.balance[base] -= amount

        # Update Session's balance of the qoute currency (buying)
        new_amount = amount * exp_fill * tx
        if qoute in self.balance:
            self.balance[qoute] += new_amount
        else:
            self.balance[qoute] = new_amount
        
        # Update Account's balance of the qoute currency (buying)
        if qoute in self.Account.balance:
            self.Account.balance[qoute] += new_amount
        else:
            self.Account.balance[qoute] = new_amount

        return new_amount

    def update_PL(self):
        self.PL = (self.balance[self.starting_cur] - self.starting_balance) / self.starting_balance
        

class TradeExecution:
    # Interfaces with the API to execute trades
    # Determines how much sequence volume can be traded based on order book
    def __init__(self, API:ExchangeAPI, DataManager:ExchangeData, flexible_volume=True):
        self.API =  API
        self.last_call = None # Data from the last API call]
        self.DataManager = DataManager
        self.profit_tolerance = .0005
        self.recently_traded = []
        
        # Options
        self.flexible_volume = flexible_volume
        self.simulation_mode = True

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
                raise OrderVolumeDepthError(coin_name, self.DataManager)

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
                raise OrderVolumeDepthError(coin_name, self.DataManager)

        # determine the average fill price
        remaining_volume = (test_volume - sum(book_sizes[:i]))
        fill_price = (sum([price*vol for price,vol in zip(book_prices[:i], book_sizes[:i])]) + remaining_volume*book_prices[i]) / (test_volume)
        
        real_volume = fill_price * owned_amount
        
        # Check that the real volume can be covered by the same depth as the test volume
        if abs((real_volume - test_volume)/test_volume) < convergence_tol:
            return fill_price
        else:
            return self.get_real_fill_price_sell(trade_type, owned_amount, book_prices, book_sizes, coin_name, p_guess=fill_price)    
    
    def get_real_sequence_profit(self, sequence, owned_amount=None):
        ''' Check is the sequence matches the expected profit to within a specified tolerance
            If a volume is specified, it will return the average fill price
        '''
        fee = self.DataManager.base_fee
        total = 1
        exp_fills = []

        for type, pair in sequence:
            tx = 1 - fee
            if type == "buy":
                book_prices, book_sizes = list(zip(*self.DataManager.Pairs[pair].orderbook['asks']))
                fill_price = self.get_real_fill_price_buy(type, owned_amount, book_prices, book_sizes, pair[0])

                exp_fills.append(fill_price)
                total *= (1/float(fill_price))*tx
                owned_amount = total
                
            elif type == "sell":
                # Treat this as a buy, 
                book_prices, book_sizes = list(zip(*self.DataManager.Pairs[pair].orderbook['bids']))
                fill_price = self.get_real_fill_price_sell(type, owned_amount, book_prices, book_sizes, pair[0])
                
                exp_fills.append(fill_price)
                total *= float(fill_price)*tx
                owned_amount = total
            else:
                raise Exception("Ivalid sequence format")
        if total > 1.5:
            raise Exception("Too good, something went wrong")
        
        return total - 1, exp_fills
    
    def update_sequence_orderbook(self, sequence):
        ''' Get the most recent orderbook for the sequence'''
        remove = []
        for type, pair in sequence:
            if pair in self.recently_traded:
                remove.append((type,pair))
        sequence = [trade for trade in sequence if trade not in remove]    

        if sequence:
            try:
                orderbook = self.API.get_multiple_orderbooks(list(zip(*sequence))[1])
            except TooManyRequests:
                time.sleep(.5)
                print("Orderbook requests occurring too rapidly...")
                orderbook = self.API.get_multiple_orderbooks(list(zip(*sequence))[1])
        
            for pair in orderbook:
                self.DataManager.Pairs[pair].bid = orderbook[pair]['bids'][0][0]
                self.DataManager.Pairs[pair].ask = orderbook[pair]['asks'][0][0]
                self.DataManager.Pairs[pair].orderbook = orderbook[pair]
                self.DataManager.Pairs[pair].last_updated = time.time()

    def execute_sequence(self, sequence, Session: Session):
        
        # Get the expected owned currency and confirm we have that currency available in our session
        type, pair = sequence[0]
        if type == "buy":
            exp_owned = pair[1]
        elif type == "sell":
            exp_owned = pair[0]
        
        # Get max volume from session
        if exp_owned in Session.balance:
            max_tradeable_volume = Session.starting_balance
        else:
            raise Exception("The activate trading Session does not own any of the required currency to trade the squence")

        # Get expected profit and fill price
        self.update_sequence_orderbook(sequence)
        profit, exp_fills = self.get_real_sequence_profit(sequence, max_tradeable_volume)
        
        # Check profits with lower trade volumes if profit isn't above the threshold
        trade_volume = max_tradeable_volume
        test_volume_scale_factor = .6
        
        if self.flexible_volume:
            while profit < self.profit_tolerance and trade_volume > Session.min_volume:
                print(f"Trade not profitable ({round(100*profit,6)} %) with {trade_volume} units. Trying with {round(trade_volume*test_volume_scale_factor)} units")
                trade_volume = round(trade_volume*test_volume_scale_factor)
                profit, exp_fills = self.get_real_sequence_profit(sequence, trade_volume)
            
        # Terminate execution if profit is still not large enough
        if profit < self.profit_tolerance:
            return profit

        # Execute trades
        print("========= Executing Sequence =========")
        cur_amount = trade_volume
        starting_trade_bal = cur_amount
        for i, trade in enumerate(sequence):
            type, pair = trade
            self.log_trade(pair, type, exp_fills[i], cur_amount)
            
            if type == "buy":
                cur_amount = Session.buy_market(pair, cur_amount, exp_fills[i], self.DataManager.base_fee)
                # For buying, impact orderbook with new current amount once it's in the base currency
                if self.simulation_mode:
                    self.simulate_orderbook_impact(pair, cur_amount, type)
            if type == "sell":
                # For selling, impact the orderbook with the current amount while its still in the base currency
                if self.simulation_mode:
                    self.simulate_orderbook_impact(pair, cur_amount, type)
                cur_amount = Session.sell_market(pair, cur_amount, exp_fills[i], self.DataManager.base_fee)
                
        
        Session.update_PL() 
        ending_trade_bal = cur_amount

        # Verify result
        actual_profit = (ending_trade_bal - starting_trade_bal) / starting_trade_bal
        if round(actual_profit, 10) != round(profit, 10):
            print(f"Actual profit: {actual_profit}, exp_profit: {profit}  ---- % Discrepency: {100*abs(profit - actual_profit)/actual_profit}")
            raise Exception("Profits do not match from what was calulcated in Session and get_real_sequence_profit()")
        
        print(f"Yield: {round(actual_profit, 5)}")
        return profit

    def log_trade(self, pair, type, price, amount):
        # Save to log file

        # Update recents
        self.recently_traded.append(pair)
        if len(self.recently_traded) > 15:
            self.recently_traded.pop(0)

    def simulate_orderbook_impact(self, pair, amount, trade_type):
        ''' Update the orderbook to reflect the impact of a trade'''
        if trade_type == "buy":
            order_type = 'asks'
            orderbook = self.DataManager.Pairs[pair].orderbook['asks']    
        if trade_type == "sell":
            order_type = 'bids'
            orderbook = self.DataManager.Pairs[pair].orderbook['bids']
        book_sizes = list(zip(*orderbook))[1]
        
        i = 0
        while sum(book_sizes[:i+1]) < amount:
            i += 1
            if i > len(book_sizes):
                raise OrderVolumeDepthError(pair[0])

        # Subtract volume from the last level reached with the amount trade
        orderbook[i][1] -= amount
        
        # Remove price levels where volume is fully consumed (if first level isn't enough to cover)
        orderbook = orderbook[i:]
        
        self.DataManager.Pairs[pair].orderbook[order_type] = orderbook


        



 # Say sequence is ETH/USD, ETH/BTC, BTC,USD
 # Start with 100 usd
 # I need to buy x amount of ETH for all 100 dollars (that is price ETH/amount usd owned)
 # Need to know the price of ETH --> start with the best ask 
 # Est. Volume of ETH to trade is best ask/amount_owned
 # Now check if this volume is covered by the best ask size
 # If it is, continue
 # Else, check how many price steps up we have to go up to cover the volume at the best ask
