from ctypes import sizeof
from dataclasses import dataclass
from typing import Dict
import time

from APIs.abstract import ExchangeAPI
from Modules import ExchangeData, Pair
from Modules.Portfolio import Portfolio
from util.obj_funcs import save_obj, load_obj
from CustomExceptions import OrderVolumeDepthError, TooManyRequests, TradeFailed, OrderTimeout
from util import events
from util.round_to_increment import round_to_increment

class SessionLive:
    def __init__(self, parent_account:Portfolio, API:ExchangeAPI, DataManager:ExchangeData, funding_balance:float, funding_cur:str, min_volume:int):
        self.Account = parent_account
        self.API = API
        self.DataManager = DataManager

        if funding_balance <= 0:
            raise Exception("Funding balance cannot be negative or zero")

        self.starting_balance = funding_balance
        self.starting_cur = funding_cur
        self.min_volume = min_volume # minimum amount of volume that can be traded in funding cur
        self.order_done = False
        self.last_trade_failed = False
        self.bal_changes = {}
        self.order_max_wait_time = 7 # seconds

        self.balance = {funding_cur:funding_balance} # Amount of money given to the trading session in base currency
        self.trades = 0 # Number of trades executed during this session
        self.PL = 0 # Current profit loss for the session
        self.average_gain = None
        
        events.subscribe(API.ACCOUNT_BALANCE_UPDATE_EVENT_ID, self.account_balance_update_listener)
        events.subscribe(DataManager.ORDER_DONE_EVENT_ID, self.order_done_listener)

    def buy(self, pair:tuple, amount, type="limit", price=None):
        ''' Use fuill balance to buy pair at market
            Session has no knowledge of fees, so exp_fill must be fee adjusted
        '''
        base, qoute = pair
        if qoute not in self.balance or qoute not in self.Account.balance:
            print(self.balance)
            raise Exception(f"{qoute} needs to be held in order to buy {pair}")
    
        # Send a buy order to the API
        if type == "limit":
            precision = self.DataManager.Pairs[pair].baseIncrement
            size = round_to_increment(amount/price, precision)
            oID = self.API.limit_order(pair, "buy", size, price)
        elif type == "market":
            precision = self.DataManager.Pairs[pair].qouteIncrement
            size = round_to_increment(amount, precision)
            oID = self.API.market_order(pair, "buy", amount)
        
        self.cur_waiting_on = base
        new_amount = float(self.wait_to_receive('buy', oID, pair))  

        # Update Account/Session's balance of the qoute currency (cost)
        self.Account.balance[qoute] -= amount
        self.balance[qoute] -= amount

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

    def sell(self, pair:tuple, amount, type="limit", price=None): 
        ''' Use full balance to sell pair at market
            Session has no knowledge of fees, so exp_fill must be fee adjusted
        '''
        base, qoute = pair

        if base not in self.balance or base not in self.Account.balance:
            raise Exception(f"{base} needs to be held in order to sell {pair}")
    
        # Send a buy order to the API
        precision = self.DataManager.Pairs[pair].baseIncrement
        amount = round_to_increment(amount, precision)
        if type == "limit":
            oID = self.API.limit_order(pair, "sell", amount, price)
        elif type == "market":
            oID = self.API.market_order(pair, "sell", amount)
        
        self.cur_waiting_on = qoute
        new_amount = float(self.wait_to_receive('sell', oID, pair))      

        # Update Account/Session's balance of the qoute currency (cost)
        self.Account.balance[base] -= amount
        self.balance[base] -= amount

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
        self.refresh_balance()
        self.PL = (self.balance[self.starting_cur] - self.starting_balance) / self.starting_balance
    
    def refresh_balance(self):
        print("Refreshing balance")
        self.balance = self.API.get_portfolio(return_raw_balance=True)
        self.Account.balance = self.balance

    def wait_to_receive(self, side, oID, pair):
        base, qoute = pair
        
        # Wait for order to fill
        print("waiting for order to complete")
        t1 = time.time()
        while not self.order_done:             
            elasped = time.time() - t1
            if elasped > self.order_max_wait_time or self.last_trade_failed:
                if elasped > self.order_max_wait_time:
                    raise OrderTimeout
                    print("Order response time out")
                self.last_trade_failed = False # Setup for next order
                raise TradeFailed

            time.sleep(.01) 
        
        # Waiting for funds to settle
        error = 1
        while error > .001:
            # Good when the amount of currency taken away is self.last_order_fill_size   
            if oID in self.bal_changes:
                if base in self.bal_changes[oID]:
                    error = (self.last_order_fill_size - abs(self.bal_changes[oID][base])) / self.last_order_fill_size
            time.sleep(.01) 

        if side == 'buy':
            new_amount = self.bal_changes[oID][base]
        elif side == 'sell':
            while not qoute in self.bal_changes[oID]:
                time.sleep(.01)
            new_amount = self.bal_changes[oID][qoute]
        
        print(f"Order status done for: {pair}, now owned {new_amount} units")
        self.trades += 1
        self.order_done = False
        self.last_trade_failed = False

        return new_amount
    
    def account_balance_update_listener(self, message):
        oID = message['relationContext']['orderId']
        cur = message['currency']
        change = float(message['availableChange'])

        if not oID in self.bal_changes:
            self.bal_changes[oID] = {}

        if not cur in self.bal_changes[oID]:
            self.bal_changes[oID][cur] = change
        else:
            self.bal_changes[oID][cur] += change

    def order_done_listener(self, size):
        if float(size) == 0:
            print("Trade failed, zero size filled")
            self.last_trade_failed = True
            raise TradeFailed
        
        print("order done")
        self.last_order_fill_size = float(size)
        self.order_done = True
        

# =============================================================================
# =============================================================================


class SessionSim:
    def __init__(self, parent_account:Portfolio=None, funding_balance:float=100, funding_cur:str="USDT", min_volume:int=5):
        self.Account = parent_account
        
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
        #self.API.market_order(pair, "buy", amount)
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
        #self.API.market_order(pair, "sell", amount)
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