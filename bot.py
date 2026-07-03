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

INITIAL_COINS = 1000  # starting balance for new users
DAILY_BONUS = 200   # coins granted by daily claim

# Multilingual support

LANGUAGES = {
    "uz": {
        "welcome": "Assalomu alaykum, {name}! Sizda {coins} ta token bor.",
        "balance": "Sizda {coins} token bor.",
        "daily_cooldown": "Keyingi kunlik bonus {hrs} soat {mins} da bo'ladi.",
        "daily_success": "Kunlik bonus {bonus} token! Jami: {coins} token.",
        "no_coins": "Sizda yetarli token yo'q.",
        "slot_result": "Siz {reels} ga o'ynadingiz. {msg} {win} token qo'shildi. Jami: {coins} token.",
        "jackpot": "Jackpot!",
        "win_two": "Yaxshi!",
        "lose": "Afsus, yutqazdingiz.",
        "leaderboard": "🏆 Eng boy foydalanuvchilar:"
    },
    "ru": {
        "welcome": "Привет, {name}! У вас {coins} монет.",
        "balance": "У вас {coins} монет.",
        "daily_cooldown": "Следующий ежедневный бонус через {hrs} часов {mins} минут.",
        "daily_success": "Ежедневный бонус {bonus} монет! Всего: {coins} монет.",
        "no_coins": "Недостаточно монет.",
        "slot_result": "Вы сыграли {reels}. {msg} Вы получили {win} монет. Всего: {coins} монет.",
        "jackpot": "Джекпот!",
        "win_two": "Вы выиграли!",
        "lose": "Вы проиграли.",
        "leaderboard": "🏆 Топ игроков:"
    },
    "en": {
        "welcome": "Hello, {name}! You have {coins} coins.",
        "balance": "You have {coins} coins.",
        "daily_cooldown": "Next daily bonus in {hrs}h {mins}m.",
        "daily_success": "Daily bonus {bonus} coins! Total: {coins}.",
        "no_coins": "Not enough coins.",
        "slot_result": "You rolled {reels}. {msg} You won {win} coins. Total: {coins}.",
        "jackpot": "Jackpot!",
        "win_two": "Nice win!",
        "lose": "You lost.",
        "leaderboard": "🏆 Leaderboard:"
    }
}

def save_users():
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

def get_user(user_id: str):
    if user_id not in users:
        users[user_id] = {"coins": INITIAL_COINS, "last_daily": None, "lang": "uz"}
        save_users()
    return users[user_id]

def get_text(user_id: str, key: str, **kwargs):
    lang = get_user(user_id).get("lang", "uz")
    return LANGUAGES[lang][key].format(**kwargs)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(str(update.effective_user.id))
    await update.message.reply_text(get_text(str(update.effective_user.id), "welcome", name=update.effective_user.first_name, coins=user['coins']))

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(str(update.effective_user.id))
    await update.message.reply_text(get_text(str(update.effective_user.id), "balance", coins=user['coins']))

async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    user = get_user(uid)
    now = datetime.utcnow()
    last = user.get("last_daily")
    if last:
        last_dt = datetime.fromisoformat(last)
        if now - last_dt < timedelta(hours=24):
            remaining = timedelta(hours=24) - (now - last_dt)
            await update.message.reply_text(get_text(uid, "daily_cooldown", hrs=int(remaining.total_seconds()//3600), mins=int((remaining.total_seconds()%3600)//60)))
            return
    user["coins"] += DAILY_BONUS
    user["last_daily"] = now.isoformat()
    save_users()
    await update.message.reply_text(get_text(uid, "daily_success", bonus=DAILY_BONUS, coins=user['coins']))

async def slot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    user = get_user(uid)
    bet = 10
    if user["coins"] < bet:
        await update.message.reply_text(get_text(uid, "no_coins"))
        return
    user["coins"] -= bet
    symbols = [random.randint(0, 9) for _ in range(3)]
    if symbols[0] == symbols[1] == symbols[2]:
        win, msg_key = bet * 5, "jackpot"
    elif symbols[0] == symbols[1] or symbols[0] == symbols[2] or symbols[1] == symbols[2]:
        win, msg_key = bet * 2, "win_two"
    else:
        win, msg_key = 0, "lose"
    user["coins"] += win
    save_users()
    await update.message.reply_text(get_text(uid, "slot_result", reels=" | ".join(map(str, symbols)), msg=get_text(uid, msg_key), win=win, bet=bet, coins=user['coins']))

async def lang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🇺🇿 O'zbekcha", callback_data="lang_uz"), InlineKeyboardButton("🇺🇸 English", callback_data="lang_en")]]
    await update.message.reply_text("Select language / Tilni tanlang:", reply_markup=InlineKeyboardMarkup(keyboard))

async def lang_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(query.from_user.id)
    users[uid]["lang"] = query.data.split("_")[1]
    save_users()
    await query.answer("Language set!")
    await query.edit_message_text(f"Language set to {users[uid]['lang'].upper()}")

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    top = sorted(users.items(), key=lambda item: item[1]["coins"], reverse=True)[:10]
    lines = [get_text(str(update.effective_user.id), "leaderboard")]
    for i, (uid, data) in enumerate(top, 1): lines.append(f"{i}. ID {uid[:6]}… – {data['coins']}")
    await update.message.reply_text("\n".join(lines))

def main() -> None:
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("daily", daily))
    app.add_handler(CommandHandler("slot", slot))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("lang", lang))
    app.add_handler(CallbackQueryHandler(lang_callback, pattern="^lang_"))
    app.run_polling()

if __name__ == "__main__":
    main()
