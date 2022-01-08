from dataclasses import dataclass
from typing import Dict
import time


from APIs.abstract import ExchangeAPI
from Modules import DataManagement, ExchangeData, Pair
from Modules.Portfolio import Portfolio
from util.obj_funcs import save_obj, load_obj
from CustomExceptions import OrderVolumeDepthError, TooManyRequests
from util import events

class SessionLive:
    def __init__(self, parent_account:Portfolio, API:ExchangeAPI, funding_balance:float, funding_cur:str, min_volume:int):
        self.Account = parent_account
        self.API = API
        
        if funding_balance <= 0:
            raise Exception("Funding balance cannot be negative or zero")

        self.starting_balance = funding_balance
        self.starting_cur = funding_cur
        self.min_volume = min_volume # minimum amount of volume that can be traded in funding cur
        self.last_balance_change = (None, None)
        self.last_fill = None
        self.last_pair_filled = None

        self.balance = {funding_cur:funding_balance} # Amount of money given to the trading session in base currency
        self.trades = 0 # Number of trades executed during this session
        self.PL = 0 # Current profit loss for the session
        self.average_gain = None
        
        events.subscribe(API.ACCOUNT_BALANCE_UPDATE_EVENT_ID, self.account_balance_update_listener)
        events.subscribe(API.ORDER_UPDATE_EVENT_ID, self.order_update_listener)

    def buy_market(self, pair:tuple, amount):
        ''' Use fuill balance to buy pair at market
            Session has no knowledge of fees, so exp_fill must be fee adjusted
        '''
        base, qoute = pair

        if qoute not in self.balance or qoute not in self.Account.balance:
            print(self.balance)
            raise Exception(f"{qoute} needs to be held in order to buy {pair}")
    
        # Send a buy order to the API
        self.API.market_order(pair, "buy", amount)
        self.trades += 1

        self.cur_waiting_on = base
        new_amount = self.wait_to_receive(base, pair)        

        # Update Account/Session's balance of the qoute currency (cost)
        self.Account.balance[qoute] -= float(amount)
        self.balance[qoute] -= float(amount)

        if base in self.balance:
            self.balance[base] += float(new_amount)
        else:
            self.balance[base] = float(new_amount)
        
        # Update Account's balance of the base currency (buying)
        if base in self.Account.balance:
            self.Account.balance[base] += float(new_amount)
        else:
            self.Account.balance[base] = float(new_amount)

        return new_amount

    def sell_market(self, pair:tuple, amount): 
        ''' Use full balance to sell pair at market
            Session has no knowledge of fees, so exp_fill must be fee adjusted
        '''
        base, qoute = pair

        if base not in self.balance or base not in self.Account.balance:
            raise Exception(f"{base} needs to be held in order to sell {pair}")
    
        # Send a buy order to the API
        self.API.market_order(pair, "sell", amount)
        self.trades += 1
        
        self.cur_waiting_on = qoute
        new_amount = self.wait_to_receive(qoute, pair)        

        # Update Account/Session's balance of the qoute currency (cost)
        self.Account.balance[base] -= float(amount)
        self.balance[base] -= float(amount)

        if qoute in self.balance:
            self.balance[qoute] += float(new_amount)
        else:
            self.balance[qoute] = float(new_amount)
        
        # Update Account's balance of the qoute currency (buying)
        if qoute in self.Account.balance:
            self.Account.balance[qoute] += float(new_amount)
        else:
            self.Account.balance[qoute] = float(new_amount)

        return new_amount

    def update_PL(self):
        self.refresh_balance()
        self.PL = (self.balance[self.starting_cur] - self.starting_balance) / self.starting_balance
    
    def refresh_balance(self):
        print("Refreshing balance")
        self.balance = self.API.get_portfolio(return_raw_balance=True)
        self.Account.balance = self.balance

    def wait_to_receive(self, coin_to_own, pair):
        # Wait for order to fill
        while True:             
            if self.last_balance_change[0] == coin_to_own:
                new_amount = self.last_balance_change[1]
                print(f"Now owned: {self.last_balance_change}")
                self.last_balance_change = (None, None)
                break
            time.sleep(.01) 
        return new_amount
    
    def account_balance_update_listener(self, message):
        if message['currency'] == self.cur_waiting_on:
            self.last_balance_change = (message['currency'], message['available'])

    def order_update_listener(self, message):
        #print(f"received order update: {message}")
        if message['type'] == 'match':
            self.last_fill = message['matchPrice']
            pair = message['symbol'].split("-")
            self.last_pair_filled = (pair[0],pair[1])
