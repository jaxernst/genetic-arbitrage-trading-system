
class Portfolio:
    # Contains holdings
    # Alows funds to be deposited
    # Allows funds to be transfered between various currencies
    # Creates sessions to allow trading to occur

    def __init__(self, balance={"USDT":0}):
        self.balance = balance
    
    def deposit_fiat(self, amount):
        self.balance["USDT"] += amount

