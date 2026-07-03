import os
import json
import random
import logging
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler

# Load environment variables
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN not set in .env")

# Paths
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
USERS_FILE = DATA_DIR / "users.json"

# Initialize logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Load or initialize user data
if USERS_FILE.exists():
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        users = json.load(f)
else:
    users = {}

INITIAL_COINS = 500  # starting balance for new users
DAILY_BONUS = 100   # coins granted by daily claim

def save_users():
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

def get_user(user_id: str):
    if user_id not in users:
        users[user_id] = {"coins": INITIAL_COINS, "last_daily": None}
        save_users()
    return users[user_id]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(str(update.effective_user.id))
    await update.message.reply_text(
        f"👋 Salom, {update.effective_user.first_name}!\n"
        f"Sizda hozir {user['coins']} ta token mavjud.\n"
        "O'yinlarga quyidagi komandalar bilan kirishingiz mumkin:\n"
        "/balance – balansni ko'rish\n"
        "/slot – slot‑mashinani o'ynash\n"
        "/daily – kunlik bonusni olish\n"
        "/leaderboard – eng boy foydalanuvchilar ro'yxati"
    )

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(str(update.effective_user.id))
    await update.message.reply_text(f"💰 Sizning balansingiz: {user['coins']} token")

async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(str(update.effective_user.id))
    now = datetime.utcnow().isoformat()
    last = user.get("last_daily")
    if last:
        last_dt = datetime.fromisoformat(last)
        if datetime.utcnow() - last_dt < timedelta(hours=24):
            remaining = timedelta(hours=24) - (datetime.utcnow() - last_dt)
            hrs = int(remaining.total_seconds() // 3600)
            mins = int((remaining.total_seconds() % 3600) // 60)
            await update.message.reply_text(
                f"⏳ Siz bugun allaqachon bonus oldingiz. Qolgan vaqt: {hrs}h {mins}m"
            )
            return
    user["coins"] += DAILY_BONUS
    user["last_daily"] = now
    save_users()
    await update.message.reply_text(
        f"🎉 Kunlik bonus! +{DAILY_BONUS} token. Yangi balans: {user['coins']}"
    )

async def slot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(str(update.effective_user.id))
    bet = 10
    if user["coins"] < bet:
        await update.message.reply_text("❌ Yetarli tokeningiz yo‘q. Balansingizni ko‘rish uchun /balance")
        return
    # Deduct bet
    user["coins"] -= bet
    # Spin three reels (symbols 0‑9)
    symbols = [random.randint(0, 9) for _ in range(3)]
    # Simple payout logic: three of a kind -> 5x bet, two of a kind -> 2x bet
    if symbols[0] == symbols[1] == symbols[2]:
        win = bet * 5
        result_msg = "👏 JACKPOT! Uchta bir xil!"
    elif symbols[0] == symbols[1] or symbols[0] == symbols[2] or symbols[1] == symbols[2]:
        win = bet * 2
        result_msg = "👍 Ikki bir xil!"
    else:
        win = 0
        result_msg = "😢 Hech narsa kelmadi."
    user["coins"] += win
    save_users()
    reels = " | ".join(str(s) for s in symbols)
    await update.message.reply_text(
        f"🎰 {reels}\n{result_msg}\n"
        f"+{win} token (bet {bet})\nYangi balans: {user['coins']}"
    )

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Sort users by coins descending, take top 10
    top = sorted(users.items(), key=lambda item: item[1]["coins"], reverse=True)[:10]
    if not top:
        await update.message.reply_text("📊 Hali foydalanuvchilar yo‘q.")
        return
    lines = ["🏆 Leaderboard (Top 10):"]
    for rank, (uid, data) in enumerate(top, start=1):
        lines.append(f"{rank}. ID {uid[:6]}… – {data['coins']} token")
    await update.message.reply_text("\n".join(lines))

async def main() -> None:
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("daily", daily))
    app.add_handler(CommandHandler("slot", slot))
    app.add_handler(CommandHandler("leaderboard", leaderboard))

    logger.info("Bot starting…")
    await app.run_polling()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
