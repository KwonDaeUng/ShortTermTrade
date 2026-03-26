import os
import asyncio
import logging
import threading
from telegram import Bot, Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from dotenv import load_dotenv

load_dotenv()

class TelegramManager:
    def __init__(self, config_callback, report_callback, state_callback):
        self.token = os.getenv("TELEGRAM_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.config_callback = config_callback  # Function to get/set config
        self.report_callback = report_callback  # Function to get simulation report
        self.state_callback = state_callback    # Function to get current state
        self.logger = logging.getLogger("TelegramManager")
        self.loop = None
        self.bot = None
        self.app = None

        if not self.token or not self.chat_id:
            self.logger.warning("Telegram Token or Chat ID not found in .env")

    async def send_message(self, text):
        if not self.token or not self.chat_id:
            return
        try:
            if not self.bot:
                self.bot = Bot(token=self.token)
            await self.bot.send_message(chat_id=self.chat_id, text=text, parse_mode='Markdown')
        except Exception as e:
            self.logger.error(f"Failed to send telegram message: {e}")

    def send_message_sync(self, text):
        """Bridge for synchronous parts of the bot"""
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self.send_message(text), self.loop)

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("안녕하세요! 업비트 단타 봇입니다. /help 를 입력하여 명령어를 확인하세요.")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = (
            "*지원 명령어*\n"
            "/report - 현재 시뮬레이션/매매 보고서 요약 확인\n"
            "/set <key> <value> - 환경 설정 변경\n"
            "   예: /set profit_target_rate 1.02\n"
            "   예: /set max_concurrent_coins 3\n"
            "/config - 현재 설정값 확인\n"
            "/status - 현재 보유 코인 및 수익 현황"
        )
        await update.message.reply_text(help_text, parse_mode='Markdown')

    async def report_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        report_data = self.report_callback()
        await update.message.reply_text(f"*실시간 보고서 요약*\n{report_data}", parse_mode='Markdown')

    async def config_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        cfg = self.config_callback(action="get")
        cfg_str = "\n".join([f"{k}: {v}" for k, v in cfg.items()])
        await update.message.reply_text(f"*현재 환경 설정*\n```\n{cfg_str}\n```", parse_mode='Markdown')

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        status_text = self.state_callback()
        await update.message.reply_text(f"*현재 계좌 상태*\n{status_text}", parse_mode='Markdown')

    async def set_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if len(context.args) < 2:
            await update.message.reply_text("사용법: /set <key> <value>")
            return
        
        key = context.args[0]
        val = context.args[1]
        
        # Try to convert to float/int if possible
        try:
            if '.' in val:
                val = float(val)
            else:
                val = int(val)
        except:
            pass
            
        success = self.config_callback(action="set", key=key, value=val)
        if success:
            await update.message.reply_text(f"설정 변경 완료: {key} = {val}")
        else:
            await update.message.reply_text(f"설정 변경 실패: {key} 항목을 찾을 수 없거나 형식이 잘못되었습니다.")

    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Log the error."""
        from telegram.error import Conflict
        if isinstance(context.error, Conflict):
            self.logger.error("!!! 텔레그램 중복 실행 감지 !!! 이 봇 토큰으로 다른 인스턴스가 이미 실행 중입니다.")
        else:
            self.logger.error(f"Telegram Exception: {context.error}")

    def run_bot(self):
        if not self.token:
            return
            
        self.app = ApplicationBuilder().token(self.token).build()
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("report", self.report_command))
        self.app.add_handler(CommandHandler("config", self.config_command))
        self.app.add_handler(CommandHandler("status", self.status_command))
        self.app.add_handler(CommandHandler("set", self.set_command))
        
        # 에러 핸들러 추가
        self.app.add_error_handler(self.error_handler)
        
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.logger.info("Telegram Bot Thread Started")
        self.app.run_polling()

    def start_thread(self):
        t = threading.Thread(target=self.run_bot, daemon=True)
        t.start()
        return t
