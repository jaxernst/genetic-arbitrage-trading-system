from typing import Dict, List
import copy
from util import events

from CustomExceptions import OrderVolumeDepthError, TradeFailed, ConvergenceError, RestartEngine
from Modules import ExchangeData
from Modules.Session import Session
from Modules.Orders import Order, LimitOrder, MarketOrder, OrderGenerator
from Modules.OrderUtilities import OrderVolumeSizer
from enums import tradeType, tradeSide
from util.obj_funcs import save_obj, load_obj
from util.SequenceTracker import SequenceTracker
from util.round_to_increment import  round_to_increment



class SequenceTrader:
    
    START_CUR_CHANGE_EVENT_ID = 1
    TRADEABLE_MARKETS = ("USDT", "ETH", "BTC", "KCS", "USDC", "TUSD")

    def __init__(self, DataManager:ExchangeData, Session: Session=None, starting_cur:str="USDT"):
        self.DataManager = DataManager
        self.OrderVolumeSizer = OrderVolumeSizer(self.DataManager.Pairs)
        self.order_gen = OrderGenerator(self.DataManager)
        self.session = Session
    
        # Options
        self.default_trade_type = tradeType.LIMIT
        self.profit_tolerance = .00025
        self.Tracker = SequenceTracker(20)

        self.DataManager.subscribe_order_status()
        self.DataManager.subscribe_account_balance_notice()

        self.owned = Session.starting_cur
               
    def get_sequence_profit(self, sequence:tuple[tuple], autoExecute:bool=True, forceExecute:bool=False, owned_amount:float=None):
        ''' Check if the sequence matches the expected profit to within a specified tolerance
            If a volume is specified, it will return the average fill price
        '''
    
        type, pair = sequence[0]
        exp_owned = self.expected_to_own(sequence[0])
         
        starting_amount = self.session.balance[exp_owned]
        total = copy.copy(starting_amount)
        exp_fills = []
        for type, pair in sequence:
            fee = self.DataManager.Pairs[pair].fee
            tx = 1 - fee
            if "BUY" in type.name:
                try:
                    fill_price = self.OrderVolumeSizer.get_best_fill_price(type, pair, total)
                except (OrderVolumeDepthError, ConvergenceError):
                    return -1

                exp_fills.append(fill_price)
                total *= (1/fill_price)*tx
                
            elif "SELL" in type.name:
                try:
                    fill_price = self.OrderVolumeSizer.get_best_fill_price(type, pair, total)
                except (OrderVolumeDepthError, ConvergenceError):
                    return -1

                exp_fills.append(fill_price)
                total *= fill_price*tx
            else:
                raise Exception("Invalid sequence format")
           
        exp_profit = (total / starting_amount) - 1
        if exp_profit > 1.5:
            raise Exception("Too good, something went wrong")
        
        if forceExecute:
            return self.execute_sequence(sequence, starting_amount, exp_fills, exp_profit=exp_profit)
        if self.trading_conditions_statisfied(exp_profit, sequence):
            return self.execute_sequence(sequence, starting_amount, exp_fills, exp_profit=exp_profit)  

        return exp_profit
        
    def trading_conditions_statisfied(self, exp_profit, sequence):
        if not exp_profit > self.profit_tolerance:
            return False

        self.Tracker.update_recents()
        return all(trade not in self.Tracker.recents for trade in sequence)
        
    def expected_to_own(self, trade:tuple[str, tuple[str]]):
        ''' arg format example: ('buy', ('ETH','USD')) '''
        if "BUY" in trade[0].name:
            return trade[1][1]
        elif "SELL" in trade[0].name:
            return trade[1][0]
        else:
            raise Exception("Unexpected trade type")

    def execute_sequence(self, sequence,  trade_volume, exp_fills, exp_profit=None):
        ''' Execute trading sequence with the full session balance '''
        print("========= Executing Sequence =========")
        
        if exp_profit:
            print(f"Expecting {exp_profit} yield. Starting with: {trade_volume}")
        
        starting_trade_bal = trade_volume
        cur_amount = copy.copy(trade_volume)
        for i, trade in enumerate(sequence):
            print(f"{trade} with {cur_amount} units. Expected fill: {exp_fills[i]}")
            side, pair = trade
            limit_price = exp_fills[i]
            
            if side == tradeSide.BUY:
                available_funds = cur_amount*(1 - self.DataManager.Pairs[pair].fee)
                order = self.order_gen.create_order_from_funds(side, pair, available_funds, limit_price)
            else:
                order = self.order_gen.create_order_from_funds(side, pair, cur_amount, limit_price)

            order_succeeded = self.session.submit_order(order)
            if order_succeeded:
                self.owned = pair
                cur_amount = order.received_amount
            else:
                self.handle_trade_failure(order, i)

        self.session.update_PL()
        actual_profit = (cur_amount - starting_trade_bal) / starting_trade_bal   
        if actual_profit < 0:
            # Don't trade this again for a while if the trade wasn't profitable
            for trade in sequence:
                self.Tracker.remember(trade)    
         
        print(f"Yield: {round(actual_profit, 5)}")
        return actual_profit

    def handle_trade_failure(self, order, i_seq_fail):
        self.Tracker.remember((order.side, order.pair)) 
        self.remove_suspect_orders(order)

        if i_seq_fail == 0:
            return
        
        if self.owned in self.TRADEABLE_MARKETS:
            ''' If a sequence failed and we have already made a trade out of the starting currency,
                restart the arbitrage engine with a new starting currency
            '''
            raise RestartEngine
        else:
            self.return_home(from_cur=order.exp_owned)

    
    def remove_suspect_orders(self, order: Order):
        try:
            price = order.price
        except:
            print("Couldn't remove price")
            return
        
        try:
            if order.side == tradeSide.SELL:
                self.DataManager.Pairs[order.pair].orderbook.bids.pop(order.price)
            elif order.side == tradeSide.BUY:
                self.DataManager.Pairs[order.pair].orderbook.asks.pop(price)
        except KeyError:
            print("Price level no longer exists")
        
    def return_home(self, from_cur):
        
        amount_owned = self.session.balance[from_cur]
        start_cur = self.session.starting_cur
        print(f"Returning session balance to {self.session.starting_cur}")

        if (from_cur, start_cur) in self.DataManager.Pairs:
            print(f"Selling {(from_cur, start_cur)}")
            order = self.order_gen.create_order_from_funds(tradeSide.SELL, (from_cur, start_cur), amount_owned)
        elif (start_cur, from_cur) in self.DataManager.Pairs:
            print(f"Buying {(start_cur, from_cur)}")
            order = self.order_gen.create_order_from_funds(tradeSide.BUY, (start_cur, from_cur), amount_owned)
        else:
            print(f"Cannot return home with pair {(start_cur, start_cur)}: not in self.Datamanger.Pairs")
        
        self.session.submit_order(order)
        self.session.update_PL()

    




'''
    def verify_sequence(self, sequence, Session):
        Not currently being used, needs more separation
        
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
'''








'''
    def __get_real_fill_price_buy(self, trade_type, owned_amount, book_prices, book_sizes, coin_name, p_guess=None, iter_num=0):
         Calculate the real fill price to purchase/sell a currency with the amount of funds available
        
        if iter_num > 5:
            #print(f"Fill price convergence error with {coin_name}")
            raise ConvergenceError
        
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
    
    def __get_real_fill_price_sell(self, trade_type, owned_amount, book_prices, book_sizes, coin_name, p_guess=None, iter_num=0):
     Calculate the real fill price to purchase/sell a currency with the amount of funds ava
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
'''