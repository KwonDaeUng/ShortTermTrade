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

    def _calculate_macd(self, df, fast=12, slow=26, signal=9):
        exp1 = df['close'].ewm(span=fast, adjust=False).mean()
        exp2 = df['close'].ewm(span=slow, adjust=False).mean()
        macd = exp1 - exp2
        signal_line = macd.ewm(span=signal, adjust=False).mean()
        return macd, signal_line

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
        if df is None or len(df) < 30:
            return False
            
        df['ma5'] = df['close'].rolling(window=5).mean()
        df['ma20'] = df['close'].rolling(window=20).mean()
        df['vol_ma20'] = df['volume'].rolling(window=20).mean()
        df['rsi'] = self._calculate_rsi(df, 14)
        df['macd'], df['macd_signal'] = self._calculate_macd(df)
        
        current = df.iloc[-1]
        prev = df.iloc[-2]
        
        # 1. 상승 추세 판별 (정배열)
        is_uptrend = current['close'] > current['ma5'] > current['ma20']
        
        # 2. 거래량 급증 (이전 20봉 평균 대비 2.0배 이상)
        is_volume_surge = current['volume'] > current['vol_ma20'] * 2.0
        
        # 3. 캔들 상태 (현재봉이 양봉인지 확인) - 하락 중인 덤핑 잡는 것 방지
        is_green_candle = current['close'] > current['open']
        
        # 4. 윗꼬리 길이 체크 (몸통 대비 1.5배 이상 길면 위험 구간)
        def is_safe_wick(candle):
            body = abs(candle['close'] - candle['open'])
            if body == 0:
                body = 1e-8 # 0으로 나누기 방지
            upper_shadow = candle['high'] - max(candle['open'], candle['close'])
            return upper_shadow < body * 1.5

        is_current_safe_wick = is_safe_wick(current)
        is_prev_safe_wick = is_safe_wick(prev)
        
        # 5. MACD 지표 상승 추세인지 (MACD > Signal)
        is_macd_bullish = current['macd'] > current['macd_signal']
        
        # 6. RSI가 55~70 사이 (상승 여력은 있으나 너무 과열(70 초과)되지 않음)
        is_rsi_valid = 55 <= current['rsi'] <= 70
        
        # 7. 너무 급격한 상승폭 (직전 종가 대비 5% 초과) 한 번에 급등 시 배제
        is_not_too_high = current['close'] <= prev['close'] * 1.05
        
        if (is_uptrend and is_volume_surge and is_green_candle and 
            is_current_safe_wick and is_prev_safe_wick and 
            is_macd_bullish and is_rsi_valid and is_not_too_high):
            self.logger.info(f"[{ticker}] Buy Signal! Prc: {current['close']:,.2f}, RSI: {current['rsi']:.1f}, MACD: {current['macd']:.2f}")
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
