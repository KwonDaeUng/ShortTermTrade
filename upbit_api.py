import os
import pyupbit
from dotenv import load_dotenv

load_dotenv()

class UpbitDataAPI:
    """Read-only API for fetching market data"""
    def __init__(self):
        self.access = os.getenv("UPBIT_ACCESS_KEY", "")
        self.secret = os.getenv("UPBIT_SECRET_KEY", "")
        if self.access and self.secret:
            self.upbit = pyupbit.Upbit(self.access, self.secret)
        else:
            self.upbit = None

    def get_current_price(self, ticker):
        return pyupbit.get_current_price(ticker)

    def get_ohlcv(self, ticker, interval="minute1", count=200):
        return pyupbit.get_ohlcv(ticker, interval=interval, count=count)

    def get_orderbook(self, ticker):
        return pyupbit.get_orderbook(ticker)
        
    def get_tickers(self, fiat="KRW"):
        return pyupbit.get_tickers(fiat=fiat)

class UpbitTradeAPI(UpbitDataAPI):
    """Trading API for executing actual transactions"""
    def get_balance(self, ticker="KRW"):
        if self.upbit:
            return self.upbit.get_balance(ticker)
        return 0

    def buy_market_order(self, ticker, price):
        if self.upbit:
            return self.upbit.buy_market_order(ticker, price)
        return None

    def sell_market_order(self, ticker, volume):
        if self.upbit:
            return self.upbit.sell_market_order(ticker, volume)
        return None
