import json

class SimulatorAPI:
    def __init__(self, data_api, initial_krw=1000000):
        self.data_api = data_api
        self.krw_balance = initial_krw
        self.balances = {}
        self.trade_history = []
        self.report_file = "simulation_report.json"
        
    def get_current_price(self, ticker):
        return self.data_api.get_current_price(ticker)

    def get_ohlcv(self, ticker, interval="minute1", count=200):
        return self.data_api.get_ohlcv(ticker, interval=interval, count=count)

    def get_orderbook(self, ticker):
        return self.data_api.get_orderbook(ticker)

    def get_tickers(self, fiat="KRW"):
        return self.data_api.get_tickers(fiat=fiat)

    def get_balance(self, ticker="KRW"):
        if ticker == "KRW":
            return self.krw_balance
        return self.balances.get(ticker, 0)

    def buy_market_order(self, ticker, price):
        current_price = self.get_current_price(ticker)
        if not current_price:
            return None
            
        fee_rate = 0.0005 # Upbit fee
        volume = price / current_price
        total_cost = price * (1 + fee_rate)
        
        if self.krw_balance < total_cost:
            return None
            
        self.krw_balance -= total_cost
        self.balances[ticker] = self.balances.get(ticker, 0) + volume
        
        trade = {
            "type": "buy",
            "ticker": ticker,
            "price": current_price,
            "volume": volume,
            "total_cost": total_cost,
            "uuid": f"sim_buy_{len(self.trade_history)}"
        }
        self.trade_history.append(trade)
        return trade

    def sell_market_order(self, ticker, volume):
        current_price = self.get_current_price(ticker)
        if not current_price or self.balances.get(ticker, 0) < volume:
            return None
            
        fee_rate = 0.0005
        gross_return = current_price * volume
        net_return = gross_return * (1 - fee_rate)
        
        self.balances[ticker] -= volume
        if self.balances[ticker] <= 1e-8:
            self.balances.pop(ticker, None)
            
        self.krw_balance += net_return
        
        trade = {
            "type": "sell",
            "ticker": ticker,
            "price": current_price,
            "volume": volume,
            "net_return": net_return,
            "uuid": f"sim_sell_{len(self.trade_history)}"
        }
        self.trade_history.append(trade)
        return trade
        
    def save_report(self):
        report = {
            "current_krw": self.krw_balance,
            "current_balances": self.balances,
            "total_trades": len(self.trade_history),
            "history": self.trade_history
        }
        with open(self.report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=4, ensure_ascii=False)
