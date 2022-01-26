from APIs.abstract import ExchangeAPI
from Modules.Orders import Order, MarketOrder, LimitOrder, OrderSettlementHandler
from typing import Dict, Optional

from enums import tradeType

class Tradeable:
    def _submit_order(self, API:ExchangeAPI, order:Order, wait_for_settlement=True) -> Optional[float]:
        settler = OrderSettlementHandler(API, order)

        if order.simulated:
            self._submit_fake_order(order)
        
        if isinstance(order, LimitOrder):
            oID = API.limit_order(order)
        if isinstance(order, MarketOrder):
            oID = API.market_order(order)

        order.ID = oID
        if wait_for_settlement:
            return self._settle_order(API, order)
        
        return None

    def _settle_order(self, API:ExchangeAPI, order:Order) -> float:
        settler = OrderSettlementHandler(API, order)
        received_amount = settler.wait_to_receive()
        return received_amount

    def _submit_fake_order(self, order) -> None:
        pass


class Account(Tradeable):
    # Contains holdings
    # Alows funds to be deposited
    # Allows funds to be transfered between various currencies
    # Creates sessions to allow trading to occur

    def __init__(self, API:ExchangeAPI, balance={"USDT":0}):
        self.API = API
        self.balance = API.get_portfolio()
        self.equivalent_balances = {}
        self.Sessions = {}
        self.Orders = {}
        self.equivalent_values = {}

    def deposit_fiat(self, amount) -> None:
        self.balance["USDT"] += amount

    def get_equivalent_cur_value(self, amount:float, cur:str, qoute:str="USDT") -> float:
        if cur == qoute:
            return amount
        if cur in self.equivalent_balances and qoute in self.equivalent_balances[cur]:
            return self.equivalent_balances[cur][qoute]

        _, _, p_close = self.API.get_pair_spread((cur,qoute))
        if not p_close:
            _, _, p_close = self.API.get_pair_spread((qoute, cur))
            if not p_close:
                #print(f"Couldn't get value of {cur} in {qoute}") 
                return 0
            else:
                price = 1 / p_close
        else:
            price = p_close
        
        return amount * price

    def get_largest_holding(self, qoute:str="USDT", check_limit:int=5) -> tuple[str,float]:
        ''' Return currency holding with the max value in the qoute currency'''
        qoute_values = []
        i = 0
        for cur, amount in self.balance.items():
            value = self.get_equivalent_cur_value(amount, cur, qoute)
            qoute_values.append(value)   
            self.update_balance_equivalents(cur, qoute, value)

            if i >= check_limit:
                break
            i += 1

        cur = list(self.balance.keys())[qoute_values.index(max(qoute_values))]
        return cur, self.balance[cur]

    def get_total_equivalent_value(self, qoute:str="USDT", check_limit:int=5) -> float:
        value = 0
        i = 0
        for cur, amount in self.balance.items():
            value += self.get_equivalent_cur_value(amount, cur, qoute)
            if i >= check_limit:
                break
            i += 1
        return value 
            
    def update_balance_equivalents(self, cur, qoute, value):
        if qoute not in self.equivalent_balances:
            self.equivalent_balances[qoute] = {}
        self.equivalent_balances[qoute][cur] = value

    def refresh_balance(self):
        print("Refreshing balance")
        self.balance = self.API.get_portfolio(return_raw_balance=True)
        self.Account.balance = self.balance

    def submit_order(self, order:Order):
        return super().__submit_order(self.API, order)