from ctypes import sizeof
from dataclasses import dataclass
from abc import ABC, abstractmethod
from typing import Dict
import time

from requests.models import CaseInsensitiveDict

from Modules.Account import Account, Tradeable
from Modules.Orders import Order

from util.obj_funcs import save_obj, load_obj
from CustomExceptions import OrderVolumeDepthError, TooManyRequests, TradeFailed, OrderTimeout
from util import events
from util.round_to_increment import round_to_increment


class Session(Tradeable):
    def __init__(self, Account:Account,  funding_cur:str=None, funding_balance:float=None, min_volume=None, simulated=True):
        self.Account = Account
        self.simulated = simulated
        
        if not (funding_balance and funding_cur):
            funding_cur, funding_balance = self.Account.get_largest_holding()
        if  self.Account.balance[funding_cur] < funding_balance:
            raise Exception(f"Account does not have sufficient balance to fund a Session with {funding_balance} of {funding_cur}")

        self.starting_balance = funding_balance
        self.starting_cur = funding_cur
        self.min_volume = min_volume # minimum amount of volume that can be traded in funding cur
        self.balance = {funding_cur:funding_balance}
        
         # Amount of money given to the trading session in base currency
        self.trades = 0 # Number of trades executed during this session
        self.PL = 0 # Current profit loss for the session
        self.average_gain = None

    def submit_order(self, order:Order) -> float:
        order.simulated = self.simulated
        if self.balance[order.exp_owned] >= order.required_balance:
            new_amount = super()._submit_order(self.Account.API, order)
        else:
            raise Exception("Session funds do not meet order requirements")

        self.update_balance(new_amount, order)
        return new_amount
        
    def update_balance(self, received_amount:float, complete_order:Order) -> None:
        prev_owned = complete_order.exp_owned
        now_owned = complete_order.aquiring
        self.balance[prev_owned] -= complete_order.required_balance
        if now_owned not in self.balance:
            self.balance[now_owned] = 0
        
        self.balance[complete_order.aquiring] += received_amount

    def update_PL(self) -> None:
        self.PL = (self.balance[self.starting_cur] - self.starting_balance) / self.starting_balance

    

        