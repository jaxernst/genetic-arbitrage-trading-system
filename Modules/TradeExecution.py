from dataclasses import dataclass
from typing import Dict
import time
from decimal import Decimal, ROUND_DOWN

from APIs.abstract import ExchangeAPI
from Modules import DataManagement, ExchangeData, Pair
from Modules.Portfolio import Portfolio
from Modules.Sessions import SessionLive, SessionSim
from util.obj_funcs import save_obj, load_obj
from CustomExceptions import OrderVolumeDepthError, TooManyRequests
from util import events        

class TradeExecution:
    # Interfaces with the API to execute trades
    # Determines how much sequence volume can be traded based on order book
    def __init__(self, API:ExchangeAPI, DataManager:ExchangeData, flexible_volume=False, simulation_mode=True):
        self.API =  API
        self.API.subscribe_order_status()
        self.API.subscribe_account_balance_notice()
        self.last_call = None # Data from the last API call]
        self.DataManager = DataManager
        self.profit_tolerance = .0015
        self.recently_traded = []
        self.last_balance_change = (None,None)

        # Options
        self.flexible_volume = flexible_volume
        self.simulation_mode = simulation_mode

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
        print(f"Estimated fill in orderbook level {i+1}")
        # determine the average fill price
        remaining_volume = (test_volume - sum(book_sizes[:i]))
        fill_price = (sum([price*vol for price,vol in zip(book_prices[:i], book_sizes[:i])]) + remaining_volume*book_prices[i]) / (test_volume)
        
        real_volume = owned_amount / fill_price
        # Check that the real volume can be covered by the same depth as the test volume
        if abs((real_volume - test_volume)/test_volume) < convergence_tol:
            return fill_price
        else:
            return self.get_real_fill_price_buy(trade_type, owned_amount, book_prices, book_sizes, coin_name, p_guess=fill_price)

    def get_real_fill_price_sell(self, trade_type, owned_amount, book_prices, book_sizes, coin_name, p_guess=None, iter_num=0):
        ''' Calculate the real fill price to purchase/sell a currency with the amount of funds available'''
        convergence_tol = .001 # The test_volume has to be within .5% of the real_volume
        book_prices = [float(p) for p in book_prices]
        book_sizes = [float(s) for s in book_sizes]
        
        if iter_num > 5:
            # First degub: occured when a volume on the first level was negative
            a = 1

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
        print(f"Estimated fill in orderbook level {i+1}")
        # determine the average fill price
        remaining_volume = (test_volume - sum(book_sizes[:i]))
        fill_price = (sum([price*vol for price,vol in zip(book_prices[:i], book_sizes[:i])]) + remaining_volume*book_prices[i]) / (test_volume)
        
        real_volume = fill_price * owned_amount
        
        # Check that the real volume can be covered by the same depth as the test volume
        if abs((real_volume - test_volume)/test_volume) < convergence_tol:
            return fill_price
        else:
            return self.get_real_fill_price_sell(trade_type, owned_amount, book_prices, book_sizes, coin_name, p_guess=fill_price, iter_num=iter_num+1)    
    
    def get_real_sequence_profit(self, sequence, owned_amount=None):
        ''' Check is the sequence matches the expected profit to within a specified tolerance
            If a volume is specified, it will return the average fill price
        '''
        
        total = 1
        exp_fills = []

        for type, pair in sequence:
            fee = self.DataManager.Pairs[pair].fee
            tx = 1 - fee
            if type == "buy":
                book_prices, book_sizes = list(zip(*self.DataManager.Pairs[pair].orderbook.get_book('asks')))
                fill_price = self.get_real_fill_price_buy(type, owned_amount, book_prices, book_sizes, pair[0])

                exp_fills.append(fill_price)
                total *= (1/float(fill_price))*tx
                owned_amount = total
                
            elif type == "sell":
                # Treat this as a buy, 
                book_prices, book_sizes = list(zip(*self.DataManager.Pairs[pair].orderbook.get_book('bids')))
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
        
        if self.simulation_mode:
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

    def execute_sequence(self, sequence, Session):
        self.cur_waiting_on = None
        
        if isinstance(Session, SessionLive) and self.simulation_mode:
            raise Exception("Cannot trade with a live session in simulation mode")
        if isinstance(Session, SessionSim) and not self.simulation_mode:
            raise Exception("Cannot trade a simulated session in live mode")


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
        #self.update_sequence_orderbook(sequence)
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
        print(f"Expecting {profit} yield. Starting with: {trade_volume}")
        starting_trade_bal = trade_volume
        cur_amount = trade_volume
    
        for i, trade in enumerate(sequence):
            type, pair = trade
            price_precision = self.DataManager.Pairs[pair].priceIncrement
            limit_price =  float(Decimal(exp_fills[i]).quantize(Decimal(price_precision), rounding=ROUND_DOWN))

            if type == "buy":
                size_precision = self.DataManager.Pairs[pair].qouteIncrement
                print(f"{trade} with {cur_amount} units. Expected fill: {exp_fills[i]}, (qouteIncrement={size_precision})")
                cur_amount = float(Decimal(cur_amount).quantize(Decimal(size_precision), rounding=ROUND_DOWN))
                
                if self.simulation_mode:
                    # For buying, impact orderbook with new current amount once it's in the base currency
                    cur_amount = Session.buy_market(pair, cur_amount, limit_price, self.DataManager.Pairs[pair].fee)
                    self.simulate_orderbook_impact(pair, cur_amount, type)
                else:
                    amount_to_buy = cur_amount*(1 - self.DataManager.Pairs[pair].fee)# / limit_price
                    amount_to_buy = float(Decimal(str(amount_to_buy)).quantize(Decimal(size_precision), rounding=ROUND_DOWN))
                    cur_amount = Session.buy_market(pair, amount_to_buy, limit_price)
                
            if type == "sell":
                size_precision = self.DataManager.Pairs[pair].baseIncrement
                cur_amount = float(Decimal(str(cur_amount)).quantize(Decimal(size_precision), rounding=ROUND_DOWN))
                print(f"{trade} with {cur_amount} units. Expected fill: {exp_fills[i]}, (baseIncrement={size_precision})")

                if self.simulation_mode:
                    #  For selling, impact the orderbook with the current amount while its still in the base currency
                    self.simulate_orderbook_impact(pair, cur_amount, type)
                    cur_amount = Session.sell_market(pair, cur_amount, limit_price, self.DataManager.Pairs[pair].fee)
                else:
                    cur_amount = Session.sell_market(pair, cur_amount, limit_price)
                
        Session.update_PL()
        ending_trade_bal = cur_amount
        
        if not self.simulation_mode:    
            self.DataManager.save_orders()

        actual_profit = (ending_trade_bal - starting_trade_bal) / starting_trade_bal        
        print(f"Yield: {round(actual_profit, 5)}")
        #raise Exception("Worked")
        return actual_profit

    def log_trade(self, pair, type, price, amount):
        # Save to log file

        # Update recents
        self.recently_traded.append(pair)
        if len(self.recently_traded) > 15:
            self.recently_traded.pop(0)

    def simulate_orderbook_impact(self, pair, amount, trade_type):
        ''' Update the orderbook to reflect the impact of a trade'''
        if trade_type == "buy":
            orderbook = self.DataManager.Pairs[pair].orderbook.get_book('asks')    
        if trade_type == "sell":
            orderbook = self.DataManager.Pairs[pair].orderbook.get_book('bids')
        book_prices, book_sizes = list(zip(*orderbook))
        
        i = 0
        while book_sizes[i] <= amount:
            amount -= book_sizes[i]
            orderbook[i][1] = 0
            i += 1
            if i > len(book_sizes):
                raise OrderVolumeDepthError(pair[0])

        print(f"Simulating orderbook impact at {i+1} level/s")
        
        # Subtract volume from the last level reached with the amount trade
        remaining = book_sizes[i] - amount
        if trade_type == "buy":
            if book_prices[i] in self.DataManager.Pairs[pair].orderbook.asks:
                self.DataManager.Pairs[pair].orderbook.asks[book_prices[i]] = str(remaining)
        elif trade_type == "sell":
            if book_prices[i] in self.DataManager.Pairs[pair].orderbook.bids:
                self.DataManager.Pairs[pair].orderbook.bids[book_prices[i]] = str(remaining)
    

        # Remove price levels where volume is fully consumed (if first level isn't enough to cover)
        for price in book_prices[:i]:
            if trade_type == "buy":
                if price in self.DataManager.Pairs[pair].orderbook.asks:
                    del self.DataManager.Pairs[pair].orderbook.asks[price]
                else:
                    print("Expected orderbook price no longer present")
            elif trade_type == "sell":
                if price in self.DataManager.Pairs[pair].orderbook.bids:
                    del self.DataManager.Pairs[pair].orderbook.bids[price]
                else:
                    print("Expected orderbook price no longer present")
