from Models import Session

class Portfolio:
    # Contains holdings
    # Alows funds to be deposited
    # Allows funds to be transfered between various currencies
    # Creates sessions to allow trading to occur

    def __init__(self):
        self.balance = {"USDT":0, "ETH":0}
        self.active_sessions = []
    def deposit_fiat(self, amount):
        self.balance["USDT"] += amount

    def start_trading_session(self, currency, max_allocation=None) -> Session:
        if not max_allocation:
            max_allocation = self.balance[currency]
        
        session = Session(self.balance[currency]*max_allocation, currency)
        self.active_sessions.append(session)
        return session