import time
import os
import traceback
from utils import load_config, load_state, save_state, setup_logger
from upbit_api import UpbitDataAPI, UpbitTradeAPI
from simulator import SimulatorAPI
from strategy import Strategy
from trader import Trader

def main():
    logger = setup_logger("ShortTermBot", "bot.log")
    logger.info("Starting ShortTermTrade Bot...")

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

    strategy = Strategy(data_api, logger, rank_limit=config.get("rank_volume_limit", 30))
    trader = Trader(trade_api, state, config, logger)

    interval = config.get("monitoring_interval_sec", 1)

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
