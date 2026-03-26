import time
import os
import traceback
from utils import load_config, load_state, save_state, setup_logger
from upbit_api import UpbitDataAPI, UpbitTradeAPI
from simulator import SimulatorAPI
from strategy import Strategy
from trader import Trader
from telegram_manager import TelegramManager

def main():
    import os
    pid = os.getpid()
    logger = setup_logger("ShortTermBot", "bot.log")
    logger.info(f"--- Bot Starting (PID: {pid}) ---")

    config = load_config()
    state = load_state()

    is_simulation = config.get("simulation_mode", True)
    logger.info(f"Simulation Mode: {is_simulation}")

    data_api = UpbitDataAPI()
    
    if is_simulation:
        # 가상 투자금 1,000,000원으로 시작 (테스트용)
        trade_api = SimulatorAPI(data_api, initial_krw=1000000)
    else:
        # 실제 투자
        trade_api = UpbitTradeAPI()

    # --- Telegram Callbacks ---
    def config_callback(action="get", key=None, value=None):
        nonlocal config
        if action == "get":
            return config
        elif action == "set":
            if key in config:
                config[key] = value
                with open("config.json", "w", encoding="utf-8") as f:
                    import json
                    json.dump(config, f, indent=4, ensure_ascii=False)
                return True
        return False

    def report_callback():
        if not is_simulation:
            return "실전 매매 모드입니다. (상세 보고서 미지원)"
        
        hist = trade_api.trade_history
        
        realized_pn_l = sum([t.get('net_return', 0) for t in hist if t['type'] == 'sell'])
        # realized cost is the total_cost of the sell transactions' buy counterparts. 
        # But for simplicity, we use net_return - cost. 
        # Actually, let's just use the current balance and initial balance if we had it.
        # For now, keeping the current realized P/L logic.
        
        total_buy = sum([t.get('total_cost', 0) for t in hist if t['type'] == 'buy'])
        
        holdings_summary = state_callback()
        
        return (f"💰 *매매 보고서 요약*\n"
                f"- 현재 잔고: {trade_api.get_balance('KRW'):,.0f} KRW\n"
                f"- 누적 실현 손익: {realized_pn_l:,.0f} KRW\n"
                f"- 총 매수 누적: {total_buy:,.0f} KRW\n\n"
                f"📦 *현재 계좌 상태*\n{holdings_summary}")

    def state_callback():
        holdings = state.get("holdings", {})
        if not holdings:
            return "현재 보유 코인이 없습니다."
        
        res = []
        for t, info in holdings.items():
            curr = data_api.get_current_price(t)
            if not curr: continue
            profit = (curr / info['avg_price'] - 1) * 100
            buy_price = info['avg_price']
            amount = info['total_cost']
            res.append(f"• *{t}*\n  수익률: {profit:+.2f}%\n  매수금액: {amount:,.0f}원 (평단: {buy_price:,.2f})")
        return "\n".join(res)

    telegram = TelegramManager(config_callback, report_callback, state_callback)
    telegram.start_thread()
    # --------------------------

    strategy = Strategy(data_api, logger, rank_limit=config.get("rank_volume_limit", 30))
    trader = Trader(trade_api, state, config, logger, telegram=telegram)

    interval = config.get("monitoring_interval_sec", 1)
    last_report_time = time.time()

    try:
        while True:
            try:
                # 1. 기존 보유 종목 관리 (마틴게일 추매, 익절, 손절)
                trader.manage_holdings()

                # 2. 신규 급등 코인 탐색 및 매수
                holdings = state.get("holdings", {})
                max_coins = config.get("max_concurrent_coins", 2)
                
                if len(holdings) < max_coins:
                    exclude_tickers = list(holdings.keys())
                    # 아직 빈 자리가 있으면 타겟 발굴
                    targets = strategy.get_target_coins(limit=(max_coins - len(holdings)), exclude_tickers=exclude_tickers)
                    if targets:
                        trader.try_buy_new_targets(targets)

                # 10회 주기마다 상태 요약 출력 (루프 interval 고려)
                if int(time.time()) % 10 == 0:
                    balance_krw = trade_api.get_balance("KRW")
                    holdings_count = len(state.get("holdings", {}))
                    logger.info(f"[Summary] KRW: {balance_krw:,.0f} | Count: {holdings_count}")

                # 1시간마다 텔레그램 자동 보고서 전송
                if time.time() - last_report_time >= 3600:
                    logger.info("Sending hourly automated report to Telegram...")
                    telegram.send_message_sync(f"🕒 *정기 매매 보고 (1시간 단위)*\n{report_callback()}")
                    last_report_time = time.time()

                # 상태 저장
                save_state(state)
                
                # 시뮬레이션인 경우 리포트 업데이트
                if is_simulation:
                    trade_api.save_report()

            except Exception as e:
                logger.error(f"Error in main loop: {e}\n{traceback.format_exc()}")
            
            time.sleep(interval)

    except KeyboardInterrupt:
        logger.info("Bot stopped by user (KeyboardInterrupt).")
    finally:
        save_state(state)
        if is_simulation:
            trade_api.save_report()
            logger.info("Simulation report saved to simulation_report.json")
        logger.info("Bot shut down gracefully.")

if __name__ == "__main__":
    main()
