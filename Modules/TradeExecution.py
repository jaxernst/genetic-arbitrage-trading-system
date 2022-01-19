from dataclasses import dataclass
from typing import Dict
import time
from util import events

from APIs.abstract import ExchangeAPI
from Modules import DataManagement, ExchangeData
from Modules.Portfolio import Portfolio
from Modules.Sessions import SessionLive, SessionSim

from util.obj_funcs import save_obj, load_obj
from CustomExceptions import OrderVolumeDepthError, TooManyRequests, TradeFailed, ConvergenceError, OrderTimeout
from util.SequenceTracker import SequenceTracker
from util.round_to_increment import  round_to_increment


import decimal

# create a new context for this task
ctx = decimal.Context()

# 20 digits should be enough for everyone :D
ctx.prec = 20

def float_to_str(f):
    """
    Convert the given float to a string,

    without resorting to scientific notation
    """
    d1 = ctx.create_decimal(repr(f))
    return format(d1, 'f')


class TradeExecution:
    # Interfaces with the API to execute trades
    # Determines how much sequence volume can be traded based on order book

    START_CUR_CHANGE_EVENT_ID = 1
    TRADEABLE_MARKETS = ("USDT", "ETH", "BTC", "KCS", "USDC", "TUSD")

    def __init__(self, API:ExchangeAPI, DataManager:ExchangeData, Session: SessionLive=None, starting_cur="USDT", flexible_volume=False, simulation_mode=True):
        self.API = API
        self.DataManager = DataManager
        
        # Options
        self.flexible_volume = flexible_volume
        self.simulation_mode = simulation_mode
        self.profit_tolerance = .0005
        self.Tracker = SequenceTracker(20)

        if Session:
            self.Session = Session
            if isinstance(Session, SessionLive):
                self.API.subscribe_order_status()
                self.API.subscribe_account_balance_notice()
        else:
            self.Session = SessionSim()
            self.simulation_mode = True

        self.best_exp_profit = -1
        self.owned = starting_cur
        
        
    def get_real_fill_price_buy(self, trade_type, owned_amount, book_prices, book_sizes, coin_name, p_guess=None, iter_num=0):
        ''' Calculate the real fill price to purchase/sell a currency with the amount of funds available'''
        convergence_tol = .001 # The test_volume has to be within .5% of the real_volume
        book_prices = [float(p) for p in book_prices]
        book_sizes = [float(s) for s in book_sizes]
        
        if iter_num > 5:
            #print(f"Fill price convergence error with {coin_name}")
            raise ConvergenceError

        if len(book_prices) != len(book_sizes):
            raise Exception("Book sizes and prices must be the same length")
        
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
            return fill_price, i
        else:
            return self.get_real_fill_price_buy(trade_type, owned_amount, book_prices, book_sizes, coin_name, p_guess=fill_price, iter_num=iter_num+1)

    def get_real_fill_price_sell(self, trade_type, owned_amount, book_prices, book_sizes, coin_name, p_guess=None, iter_num=0):
        ''' Calculate the real fill price to purchase/sell a currency with the amount of funds available'''
        convergence_tol = .001 # The test_volume has to be within .5% of the real_volume
        book_prices = [float(p) for p in book_prices]
        book_sizes = [float(s) for s in book_sizes]
        
        if iter_num > 5:
            #print(f"Fill price convergence error with {coin_name}")
            raise ConvergenceError

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
            return fill_price, i
        else:
            return self.get_real_fill_price_sell(trade_type, owned_amount, book_prices, book_sizes, coin_name, p_guess=fill_price, iter_num=iter_num+1)    
    
    def get_sequence_profit(self, sequence, owned_amount=None):
        ''' Check if the sequence matches the expected profit to within a specified tolerance
            If a volume is specified, it will return the average fill price
        '''
        type, pair = sequence[0]
        if type == "buy":
            exp_owned = pair[1]
        elif type == "sell":
            exp_owned = pair[0]
         
        total = self.Session.balance[exp_owned]
        starting_amount = self.Session.balance[exp_owned]

        pair_p_level_indices = []
        exp_fills = []
        for type, pair in sequence:
            fee = self.DataManager.Pairs[pair].fee
            tx = 1 - fee
            if type == "buy":
                book_prices, book_sizes = list(zip(*self.DataManager.Pairs[pair].orderbook.get_book('asks')))
                try:
                    fill_price, p_level_index = self.get_real_fill_price_buy(type, total, book_prices, book_sizes, pair[0])
                except (OrderVolumeDepthError, ConvergenceError):
                    return -1, None

                exp_fills.append(fill_price)
                pair_p_level_indices.append(p_level_index)
                total *= (1/fill_price)*tx
                
            elif type == "sell":
                # Treat this as a buy, 
                book_prices, book_sizes = list(zip(*self.DataManager.Pairs[pair].orderbook.get_book('bids')))
                try:
                    fill_price, p_level_index = self.get_real_fill_price_sell(type, total, book_prices, book_sizes, pair[0])
                except (OrderVolumeDepthError, ConvergenceError):
                    return -1, None, None

                pair_p_level_indices.append(p_level_index)
                exp_fills.append(fill_price)
                total *= fill_price*tx
            else:
                raise Exception("Invalid sequence format")
        
        
        exp_profit = (total / starting_amount) - 1
        if exp_profit > 1.5:
            raise Exception("Too good, something went wrong")
        

        if  exp_profit > self.profit_tolerance:
            self.Tracker.update_recents()
            if all(trade not in self.Tracker.recents for trade in sequence):
                print("Profitable sequence found for immediate execution")
                realProfit = self.execute_sequence(sequence, starting_amount, exp_fills, pair_p_level_indices, exp_profit=exp_profit)  
                if realProfit:
                    if realProfit < 0:
                        # Don't trade this again for a while if the trade wasn't profitable
                        for trade in sequence:
                            self.Tracker.remember(trade)
            else:
                return -1, None, None
        
        if exp_profit > self.best_exp_profit:
            self.best_exp_profit = exp_profit

        return exp_profit, exp_fills, pair_p_level_indices
    
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

    def verify_sequence(self, sequence, Session):
        ''' Not currently being used, needs more separation'''
        
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

    def execute_sequence(self, sequence, trade_volume, exp_fills, pair_p_level_indices, exp_profit=None):
        # Execute trades
        print("========= Executing Sequence =========")
        if exp_profit:
            print(f"Expecting {exp_profit} yield. Starting with: {trade_volume}")
        
        starting_trade_bal = trade_volume
        cur_amount = trade_volume
        last_cur = None   
        for i, trade in enumerate(sequence):
            type, pair = trade
            price_precision = self.DataManager.Pairs[pair].priceIncrement
            limit_price = round_to_increment(exp_fills[i], price_precision)

            if type == "buy":
                print(f"{trade} with {cur_amount} units. Expected fill: {exp_fills[i]}")
                if self.simulation_mode:
                    # For buying, impact orderbook with new current amount once it's in the base currency
                    cur_amount = self.Session.buy_market(pair, cur_amount, limit_price, self.DataManager.Pairs[pair].fee)
                    self.simulate_orderbook_impact(pair, cur_amount, type)
                else:
                    amount_to_buy = cur_amount*(1 - self.DataManager.Pairs[pair].fee)
                    try:
                        cur_amount = self.Session.buy(pair, amount_to_buy, type="limit", price=limit_price)
                    except (TradeFailed, OrderTimeout):
                        self.Tracker.remember(trade)
                        self.remove_suspect_orders("asks", sequence, trade, pair_p_level_indices)

                        if last_cur:
                            if last_cur in self.TRADEABLE_MARKETS:
                                self.owned = last_cur
                                events.post_event(self.START_CUR_CHANGE_EVENT_ID, data=last_cur)
                            else:
                                self.return_home(from_cur=last_cur)
                        return False
                last_cur = pair[0]

            if type == "sell":
                print(f"{trade} with {cur_amount} units. Expected fill: {exp_fills[i]}")
                if self.simulation_mode:
                    #  For selling, impact the orderbook with the current amount while its still in the base currency
                    self.simulate_orderbook_impact(pair, cur_amount, type)
                    cur_amount = self.Session.sell_market(pair, cur_amount, limit_price, self.DataManager.Pairs[pair].fee)
                else:
                    try:
                        cur_amount = self.Session.sell(pair, cur_amount, type="limit", price=limit_price)
                    except (TradeFailed, OrderTimeout):
                        self.Tracker.remember(trade)
                        self.remove_suspect_orders("bids", sequence, trade, pair_p_level_indices)
                        if last_cur:
                            if last_cur in self.TRADEABLE_MARKETS:
                                self.owned = last_cur
                                events.post_event(self.START_CUR_CHANGE_EVENT_ID, data=last_cur)
                            else:
                                self.return_home(from_cur=last_cur)
                        return False
                last_cur = pair[1]

        self.Session.update_PL()
        ending_trade_bal = cur_amount

        actual_profit = (ending_trade_bal - starting_trade_bal) / starting_trade_bal        
        print(f"Yield: {round(actual_profit, 5)}")
        #raise Exception("Worked")
        return actual_profit

    def remove_suspect_orders(self, book_type, sequence, trade, pair_p_level_indices):
        pair = trade[1]
        book_prices, _ = list(zip(*self.DataManager.Pairs[pair].orderbook.get_book(book_type)))
        i_trade_failure = sequence.index(trade)
        p_level_index = pair_p_level_indices[i_trade_failure]
        
        print(f"Suspected spoofing in {pair} orderbook. Removing {p_level_index + 1 } price levels.")

        for i in range(p_level_index + 1):
            price = str(book_prices[i])
            try:
                if book_type == "bids":
                    self.DataManager.Pairs[pair].orderbook.bids.pop(price)
                elif book_type == "asks":
                    self.DataManager.Pairs[pair].orderbook.asks.pop(price)
            except KeyError:
                print(f"Key error in level {i+1}")

    def return_home(self, from_cur=None):
        self.Session.refresh_balance()
        balance = self.Session.balance
        start_cur = self.Session.starting_cur
        print(f"Returning session balance to {start_cur}")
        if from_cur:
            balance = {from_cur:self.Session.balance[from_cur]}
        for cur in balance:
            if cur != start_cur:
                try:
                    if (cur, start_cur) in self.DataManager.Pairs:
                        print(f"Selling {(cur, start_cur)}")
                        self.Session.sell((cur, start_cur), balance[cur], type="market")
                    elif (start_cur, cur) in self.DataManager.Pairs:
                        print(f"Buying {(start_cur, cur)}")
                        self.Session.buy((start_cur, cur), balance[cur], type="market")
                    else:
                        print(f"Cannot return home with pair {(start_cur, cur)}: not in self.Datamanger.Pairs")
                except TradeFailed:
                    print(f"Could not return {cur} to starting currency")
                    raise Exception("Fatal Error")
        
        self.Session.update_PL()

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
