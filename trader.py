import time

class Trader:
    def __init__(self, api, state, config, logger):
        self.api = api
        self.state = state
        self.config = config
        self.logger = logger
        
        # 기본 설정값 로드
        self.investment_steps = self.config.get("investment_steps", [5500, 11000, 22000, 44000, 88000])
        self.profit_target = self.config.get("profit_target_rate", 1.015)
        self.stop_loss = self.config.get("stop_loss_rate", 0.985)
        self.max_concurrent = self.config.get("max_concurrent_coins", 2)

    def execute_buy(self, ticker, step=1):
        if step > len(self.investment_steps):
            return False
            
        amount = self.investment_steps[step - 1]
        
        krw = self.api.get_balance("KRW")
        if krw < amount * 1.0005:
            self.logger.warning(f"[{ticker}] Not enough KRW to buy step {step}.")
            return False
            
        current_price = self.api.get_current_price(ticker)
        res = self.api.buy_market_order(ticker, amount)
        
        if res:
            self.logger.info(f"[{ticker}] Order Placed for Step {step} with {amount} KRW.")
            fee = amount * 0.0005
            net_amount = amount - fee
            bought_vol = net_amount / current_price
            
            holdings = self.state.get("holdings", {})
            if ticker in holdings:
                old_vol = holdings[ticker]["volume"]
                old_cost = holdings[ticker]["total_cost"]
                
                new_cost = old_cost + amount
                new_vol = old_vol + bought_vol
                avg_price = new_cost / new_vol
                
                holdings[ticker]["volume"] = new_vol
                holdings[ticker]["total_cost"] = new_cost
                holdings[ticker]["avg_price"] = avg_price
                holdings[ticker]["step"] = step
                holdings[ticker]["highest_price"] = current_price
            else:
                holdings[ticker] = {
                    "step": step,
                    "volume": bought_vol,
                    "total_cost": amount,
                    "avg_price": current_price,
                    "highest_price": current_price
                }
            self.state["holdings"] = holdings
            return True
        return False

    def execute_sell(self, ticker, reason=""):
        holdings = self.state.get("holdings", {})
        if ticker not in holdings:
            return False
            
        vol = holdings[ticker]["volume"]
        res = self.api.sell_market_order(ticker, vol)
        if res:
            current_price = self.api.get_current_price(ticker)
            self.logger.info(f"[{ticker}] Sold all ({vol:,.4f}). Reason: {reason}, Price: {current_price:,.2f}")
            del holdings[ticker]
            self.state["holdings"] = holdings
            return True
        return False

    def manage_holdings(self):
        holdings = self.state.get("holdings", {}).copy()
        
        for t, info in holdings.items():
            current_price = self.api.get_current_price(t)
            if not current_price:
                continue
                
            avg_price = info["avg_price"]
            step = info["step"]
            highest_price = info.get("highest_price", current_price)
            
            if current_price > highest_price:
                highest_price = current_price
                self.state.get("holdings", {})[t]["highest_price"] = highest_price
            
            profit_rate = current_price / avg_price
            
            if profit_rate >= self.profit_target:
                if current_price <= highest_price * 0.995:
                    self.execute_sell(t, reason=f"Take Profit (Trailing) at {profit_rate:.3f}")
            elif profit_rate >= 1.03:
                self.execute_sell(t, reason=f"Take Profit (Max 3%) at {profit_rate:.3f}")
                
            elif profit_rate <= self.stop_loss:
                if step < len(self.investment_steps):
                    next_step = step + 1
                    self.logger.info(f"[{t}] Price dropped to {profit_rate:.3f}. Triggering Martingale Step {next_step}.")
                    if not self.execute_buy(t, next_step):
                        self.execute_sell(t, reason="Stop Loss (Martingale Failed due to insufficient funds)")
                else:
                    self.execute_sell(t, reason="Stop Loss (Max Martingale Step Reached)")

    def try_buy_new_targets(self, targets):
        holdings = self.state.get("holdings", {})
        
        for t in targets:
            if len(holdings) >= self.max_concurrent:
                break
                
            if t not in holdings:
                self.execute_buy(t, step=1)
                holdings = self.state.get("holdings", {})
