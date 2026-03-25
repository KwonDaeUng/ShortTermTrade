import pandas as pd
import requests

class Strategy:
    def __init__(self, api, logger, rank_limit=30):
        self.api = api
        self.logger = logger
        self.rank_limit = rank_limit
        
    def _calculate_rsi(self, df, period=14):
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def get_top_volume_tickers(self, limit):
        try:
            tickers = self.api.get_tickers(fiat="KRW")
            url = "https://api.upbit.com/v1/ticker"
            markets = ",".join(tickers)
            res = requests.get(url, params={"markets": markets}, timeout=5)
            if res.status_code == 200:
                data = res.json()
                sorted_data = sorted(data, key=lambda x: x['acc_trade_price_24h'], reverse=True)
                return [item['market'] for item in sorted_data[:limit]]
        except Exception as e:
            self.logger.error(f"Failed to fetch volume rank: {e}")
        
        # Fallback if request fails
        return self.api.get_tickers(fiat="KRW")[:limit]

    def check_buy_signal(self, ticker):
        df = self.api.get_ohlcv(ticker, interval="minute5", count=50)
        if df is None or len(df) < 20:
            return False
            
        df['ma5'] = df['close'].rolling(window=5).mean()
        df['ma20'] = df['close'].rolling(window=20).mean()
        df['vol_ma20'] = df['volume'].rolling(window=20).mean()
        df['rsi'] = self._calculate_rsi(df, 14)
        
        current = df.iloc[-1]
        prev = df.iloc[-2]
        
        # 1. 상승 추세 판별 (정배열)
        is_uptrend = current['close'] > current['ma5'] > current['ma20']
        
        # 2. 거래량 급증 (이전 20봉 평균 대비 2.5배 이상)
        is_volume_surge = current['volume'] > current['vol_ma20'] * 2.5
        
        # 3. RSI가 55~75 사이 (상방 압력 강함, 과매수 진입 전)
        is_rsi_valid = 55 <= current['rsi'] <= 75
        
        # 4. 직전 캔들 대비 양봉 상승폭이 상식적인 수준 (최고점 물림 방지를 위해 5% 이하)
        is_not_too_high = current['close'] <= prev['close'] * 1.05
        
        if is_uptrend and is_volume_surge and is_rsi_valid and is_not_too_high:
            self.logger.info(f"[{ticker}] Buy Signal Detected! Price: {current['close']:,.2f}, RSI: {current['rsi']:.1f}")
            return True
            
        return False

    def get_target_coins(self, limit=2, exclude_tickers=None):
        if exclude_tickers is None:
            exclude_tickers = []
            
        top_tickers = self.get_top_volume_tickers(self.rank_limit)
        targets = []
        
        for t in top_tickers:
            if t in exclude_tickers:
                continue
                
            try:
                if self.check_buy_signal(t):
                    targets.append(t)
                    if len(targets) >= limit:
                        break
            except Exception as e:
                self.logger.error(f"Error checking signal for {t}: {e}")
                
        return targets
