from dataclasses import dataclass
from typing import Dict
import time
from decimal import Decimal, ROUND_DOWN

from APIs.abstract import ExchangeAPI
from Modules import DataManagement, ExchangeData, Pair
from Modules.Portfolio import Portfolio
from util.obj_funcs import save_obj, load_obj
from CustomExceptions import OrderVolumeDepthError, TooManyRequests
from util import events

class SessionSim:
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
        self.API.market_order(pair, "buy", amount)
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
        self.API.market_order(pair, "sell", amount)
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