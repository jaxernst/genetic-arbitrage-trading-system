from CustomExceptions import OrderVolumeDepthError, TradeFailed, OrderTimeout
from APIs.ExchangeAPI import ExchangeAPI
from enums import orderStatus, tradeSide
from Modules.OrderCreation import Order
from typing import Dict
from util import events
import time


class OrderSettlementHandler:
    ''' Takes in an Order object and collects websocket order
        updates and account balance updates. 
        Returns an order object with fields populated ronce order finishes
    '''
    status_keys = {"open":orderStatus.OPEN,
                   "match":orderStatus.PARTIAL_FILL,
                   "filled":orderStatus.FILLED}

    
        
    def __init__(self, API:ExchangeAPI, order:Order):
        self.Order = order

        self.funds_settled = False
        self.last_trade_failed = False
        self.bal_changes = {}
        self.order_max_wait_time = 10 # seconds

        events.subscribe(API.ACCOUNT_BALANCE_UPDATE_EVENT_ID, self.account_balance_update_listener)
        events.subscribe(API.ORDER_UPDATE_EVENT_ID, self.order_update_listener)
        self.activate_order_update_stream(API)
        self.activate_account_balance_update_stream(API)
        
    def wait_to_receive(self) -> bool:
        print("waiting for order to complete")
        t1 = time.time()
        while not self.funds_settled:             
            elasped = time.time() - t1
            if elasped > self.order_max_wait_time:
                print("Order response time out")
                return False
            if self.Order.status == orderStatus.FAILED:
                print("Trade failed")
                return False
            time.sleep(.01) 
        
        print(f"Order status done for: {self.Order.pair}, now owned {self.Order.received_amount} units")
        return True
    
    def account_balance_update_listener(self, message:dict) -> None:
        oID = message['relationContext']['orderId']
        event = message['relationEvent']
        cur = message['currency']
        trade_settled = (oID == self.Order.ID and
                      event == "trade.setted" and
                      cur == self.Order.aquiring)

        if trade_settled:
            self.Order.received_amount = float(message['available'])
            self.funds_settled = True

    def order_update_listener(self, message:dict) -> None:
        oID = message['orderId']
        if oID != self.Order.ID:
            return

        self.Order.update(message)
        status = message['type']
        if status == "update":
            raise Exception("Pending order change updates not handled yet")

        if status == "canceled":
            if float(message['filledSize']) == 0:
                self.Order.status = orderStatus.FAILED
            else:
                self.Order.status = orderStatus.FILLED
        else:
            self.Order.status = self.status_keys[status]


    def activate_account_balance_update_stream(self, API) -> None:
        if API.ACCOUNT_BALANCE_UPDATE_EVENT_ID not in API.active_streams:
            API.subscribe_account_balance_notice()

    def activate_order_update_stream(self, API) -> bool:

        if API.ACCOUNT_BALANCE_UPDATE_EVENT_ID not in API.active_streams:
            API.subscribe_order_status()

