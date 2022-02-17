from Modules.OrderCreation import LimitOrder, MarketOrder
from Modules import Order
from Modules.OrderSettlement import OrderSettlementHandler
from APIs.ExchangeAPI import ExchangeAPI
from typing import Dict, Optional

class Tradeable:
    def _submit_order(self, API:ExchangeAPI, order:Order, wait_for_settlement=True) -> Optional[float]:
        settler = OrderSettlementHandler(API, order)

        if order.simulated:
            self._submit_fake_order(order)
        
        if isinstance(order, LimitOrder):
            oID = API.limit_order(order)
        if isinstance(order, MarketOrder):
            oID = API.market_order(order)
        
        print("Order submitted to the API")
        order.ID = oID
        if wait_for_settlement:
            return settler.wait_to_receive()

    def _submit_fake_order(self, order) -> None:
        pass

    