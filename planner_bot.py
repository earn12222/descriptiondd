"""
📅 Kunlik Rejalar Boshqaruv Boti
=================================
Vazifalar:
 - Reja qo'shish (sana, vaqt, sarlavha, tavsif)
 - Barcha rejalarni ko'rish
 - Bugungi rejalar
 - Rejani tahrirlash / o'chirish
 - Bajarildi deb belgilash
 - Vaqt eslatmalari (scheduler)
"""

import os
import sqlite3
import logging
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
)

# ──────────────────────── CONFIG ────────────────────────────
load_dotenv()
TOKEN = "8668546166:AAGftWBJPNDariHUMc_wTSybX-tccQhjLHE"
TIMEZONE = ZoneInfo("Asia/Tashkent")   # O'zbekiston vaqti (UTC+5)
DB_FILE = "plans.db"

# Conversation states
(
    ADD_TITLE,
    ADD_DATE,
    ADD_TIME,
    ADD_DESC,
    EDIT_CHOOSE,
    EDIT_FIELD,
    EDIT_VALUE,
    DELETE_CONFIRM,
) = range(8)

# ──────────────────────── LOGGING ───────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ──────────────────────── DATABASE ──────────────────────────
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS plans (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            title       TEXT    NOT NULL,
            plan_date   TEXT    NOT NULL,   -- YYYY-MM-DD
            plan_time   TEXT    NOT NULL,   -- HH:MM
            description TEXT,
            done        INTEGER DEFAULT 0,
            created_at  TEXT    NOT NULL,
            notified    INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

def db():
    return sqlite3.connect(DB_FILE)

def add_plan(user_id, title, plan_date, plan_time, description=""):
    with db() as conn:
        conn.execute(
            "INSERT INTO plans (user_id, title, plan_date, plan_time, description, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, title, plan_date, plan_time, description,
             datetime.now(TIMEZONE).isoformat()),
        )

def get_plans(user_id, filter_date=None, only_pending=False, only_done=False):
    query = "SELECT id, title, plan_date, plan_time, description, done FROM plans WHERE user_id=?"
    params = [user_id]
    if filter_date:
        query += " AND plan_date=?"
        params.append(filter_date)
    if only_pending:
        query += " AND done=0"
    if only_done:
        query += " AND done=1"
    query += " ORDER BY plan_date, plan_time"
    with db() as conn:
        return conn.execute(query, params).fetchall()

def get_plan_by_id(plan_id, user_id):
    with db() as conn:
        return conn.execute(
            "SELECT id, title, plan_date, plan_time, description, done FROM plans WHERE id=? AND user_id=?",
            (plan_id, user_id),
        ).fetchone()

def update_plan_field(plan_id, field, value):
    with db() as conn:
        conn.execute(f"UPDATE plans SET {field}=? WHERE id=?", (value, plan_id))

def delete_plan(plan_id, user_id):
    with db() as conn:
        conn.execute("DELETE FROM plans WHERE id=? AND user_id=?", (plan_id, user_id))

def mark_done(plan_id, user_id, done=1):
    with db() as conn:
        conn.execute("UPDATE plans SET done=? WHERE id=? AND user_id=?", (done, plan_id, user_id))

def get_upcoming_unnotified(minutes=15):
    """Keyingi 15 daqiqa ichida boshlanadigan, hali xabar yuborilmagan rejalar."""
    now = datetime.now(TIMEZONE)
    soon = now + timedelta(minutes=minutes)
    date_now = now.strftime("%Y-%m-%d")
    date_soon = soon.strftime("%Y-%m-%d")
    time_now = now.strftime("%H:%M")
    time_soon = soon.strftime("%H:%M")
    with db() as conn:
        # Bir kunga sig'adigan holat
        return conn.execute(
            """SELECT id, user_id, title, plan_date, plan_time FROM plans
               WHERE done=0 AND notified=0
               AND ((plan_date=? AND plan_time BETWEEN ? AND ?)
                 OR (plan_date=? AND plan_date!=? AND plan_time<=?))
            """,
            (date_now, time_now, time_soon, date_soon, date_now, time_soon),
        ).fetchall()

def mark_notified(plan_id):
    with db() as conn:
        conn.execute("UPDATE plans SET notified=1 WHERE id=?", (plan_id,))

# ──────────────────────── HELPERS ───────────────────────────
def now_uz():
    return datetime.now(TIMEZONE)

def fmt_plan(plan):
    pid, title, pdate, ptime, desc, done = plan
    status = "✅ Bajarildi" if done else "🕐 Kutilmoqda"
    d = datetime.strptime(pdate, "%Y-%m-%d").strftime("%d.%m.%Y")
    no_desc = "Tavsif yo'q"
    text = (
        f"📌 <b>{title}</b>\n"
        f"📅 {d}  🕐 {ptime}\n"
        f"📝 {desc or no_desc}\n"
        f"Holat: {status}"
    )
    return text

def main_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("➕ Reja qo'shish"), KeyboardButton("📋 Barcha rejalar")],
            [KeyboardButton("📅 Bugungi rejalar"), KeyboardButton("✅ Bajarilganlar")],
            [KeyboardButton("⏳ Kutilayotganlar"), KeyboardButton("ℹ️ Yordam")],
        ],
        resize_keyboard=True,
    )

def parse_date(text):
    """Sana formatlarini qabul qilish: 25.06.2025, 25/06/2025, 2025-06-25"""
    text = text.strip()
    for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None

def parse_time(text):
    """Vaqt formatlarini qabul qilish: 14:30, 1430, 2:30 PM"""
    text = text.strip()
    for fmt in ("%H:%M", "%H%M", "%I:%M %p", "%I %p"):
        try:
            return datetime.strptime(text, fmt).strftime("%H:%M")
        except ValueError:
            pass
    return None

# ──────────────────────── HANDLERS ──────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name
    text = (
        f"👋 Salom, <b>{name}</b>!\n\n"
        "🗓 <b>Kunlik Rejalar Boti</b>ga xush kelibsiz!\n\n"
        "Bu bot orqali siz:\n"
        "• Kunlik rejalaringizni <b>qo'shishingiz</b>\n"
        "• Ularni <b>ko'rib chiqishingiz</b>\n"
        "• <b>Tahrirlashingiz</b> va <b>o'chirishingiz</b>\n"
        "• Vaqti kelganda <b>eslatma olishingiz</b> mumkin\n\n"
        "Quyidagi tugmalardan birini bosing:"
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=main_keyboard())

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "ℹ️ <b>Yordam</b>\n\n"
        "/start – Bosh menyu\n"
        "/add – Yangi reja qo'shish\n"
        "/today – Bugungi rejalar\n"
        "/all – Barcha rejalar\n"
        "/pending – Kutilayotgan rejalar\n"
        "/done – Bajarilgan rejalar\n\n"
        "📌 <b>Sana formatlari:</b> 25.06.2025 yoki 25/06/2025\n"
        "🕐 <b>Vaqt formatlari:</b> 14:30 yoki 09:00\n\n"
        "Har bir reja kartasida <b>Tahrirlash</b>, <b>O'chirish</b>, "
        "<b>Bajarildi</b> tugmalari mavjud."
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=main_keyboard())

# ── ADD PLAN conversation ─────────────────────────────────
async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "➕ <b>Yangi reja qo'shish</b>\n\n"
        "1️⃣ Reja <b>sarlavhasini</b> kiriting:\n"
        "(Bekor qilish uchun /cancel)",
        parse_mode="HTML",
    )
    return ADD_TITLE

async def add_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["title"] = update.message.text.strip()
    await update.message.reply_text(
        f"✅ Sarlavha: <b>{context.user_data['title']}</b>\n\n"
        "2️⃣ <b>Sanani</b> kiriting:\n"
        "Masalan: <code>25.06.2025</code> yoki <code>2025-06-25</code>",
        parse_mode="HTML",
    )
    return ADD_DATE

async def add_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parsed = parse_date(update.message.text)
    if not parsed:
        await update.message.reply_text(
            "❌ Sana formati noto'g'ri!\n"
            "Iltimos qayta kiriting: <code>25.06.2025</code>",
            parse_mode="HTML",
        )
        return ADD_DATE
    context.user_data["date"] = parsed
    await update.message.reply_text(
        f"✅ Sana: <b>{datetime.strptime(parsed,'%Y-%m-%d').strftime('%d.%m.%Y')}</b>\n\n"
        "3️⃣ <b>Vaqtni</b> kiriting:\n"
        "Masalan: <code>14:30</code> yoki <code>09:00</code>",
        parse_mode="HTML",
    )
    return ADD_TIME

async def add_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parsed = parse_time(update.message.text)
    if not parsed:
        await update.message.reply_text(
            "❌ Vaqt formati noto'g'ri!\n"
            "Iltimos qayta kiriting: <code>14:30</code>",
            parse_mode="HTML",
        )
        return ADD_TIME
    context.user_data["time"] = parsed
    await update.message.reply_text(
        f"✅ Vaqt: <b>{parsed}</b>\n\n"
        "4️⃣ <b>Tavsif</b> kiriting (ixtiyoriy):\n"
        "Yoki o'tkazib yuborish uchun <code>-</code> yozing.",
        parse_mode="HTML",
    )
    return ADD_DESC

async def add_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    desc = "" if text == "-" else text
    uid = update.effective_user.id
    ud = context.user_data

    add_plan(uid, ud["title"], ud["date"], ud["time"], desc)

    d = datetime.strptime(ud["date"], "%Y-%m-%d").strftime("%d.%m.%Y")
    await update.message.reply_text(
        f"🎉 <b>Reja muvaffaqiyatli qo'shildi!</b>\n\n"
        f"📌 <b>{ud['title']}</b>\n"
        f"📅 {d}  🕐 {ud['time']}\n"
        f"📝 {desc or 'Tavsif yo\'q'}",
        parse_mode="HTML",
        reply_markup=main_keyboard(),
    )
    context.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "❌ Bekor qilindi.", reply_markup=main_keyboard()
    )
    return ConversationHandler.END

# ── VIEW PLANS ────────────────────────────────────────────
def plans_keyboard(plan_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Bajarildi", callback_data=f"done_{plan_id}"),
            InlineKeyboardButton("✏️ Tahrirlash", callback_data=f"edit_{plan_id}"),
        ],
        [
            InlineKeyboardButton("🗑 O'chirish", callback_data=f"del_{plan_id}"),
            InlineKeyboardButton("↩️ Bekor qilish", callback_data=f"undone_{plan_id}"),
        ],
    ])

async def show_plans(update: Update, uid: int, plans: list, header: str):
    if not plans:
        msg = update.message or update.callback_query.message
        await msg.reply_text(f"📭 {header}\n\nHech qanday reja topilmadi.")
        return

    msg = update.message or update.callback_query.message
    await msg.reply_text(f"<b>{header}</b> — jami: {len(plans)} ta", parse_mode="HTML")
    for plan in plans:
        await msg.reply_text(
            fmt_plan(plan),
            parse_mode="HTML",
            reply_markup=plans_keyboard(plan[0]),
        )

async def cmd_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    plans = get_plans(uid)
    await show_plans(update, uid, plans, "📋 Barcha rejalar")

async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    today = now_uz().strftime("%Y-%m-%d")
    plans = get_plans(uid, filter_date=today)
    d = now_uz().strftime("%d.%m.%Y")
    await show_plans(update, uid, plans, f"📅 Bugungi rejalar ({d})")

async def cmd_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    plans = get_plans(uid, only_pending=True)
    await show_plans(update, uid, plans, "⏳ Kutilayotgan rejalar")

async def cmd_done_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    plans = get_plans(uid, only_done=True)
    await show_plans(update, uid, plans, "✅ Bajarilgan rejalar")

# ── CALLBACK BUTTONS ────────────────────────────────────────
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    data = query.data

    if data.startswith("done_"):
        plan_id = int(data.split("_")[1])
        plan = get_plan_by_id(plan_id, uid)
        if not plan:
            await query.edit_message_text("❌ Reja topilmadi.")
            return
        mark_done(plan_id, uid, 1)
        await query.edit_message_text(
            fmt_plan((*plan[:5], 1)),
            parse_mode="HTML",
            reply_markup=plans_keyboard(plan_id),
        )
        await query.message.reply_text(f"✅ <b>{plan[1]}</b> bajarildi deb belgilandi!", parse_mode="HTML")

    elif data.startswith("undone_"):
        plan_id = int(data.split("_")[1])
        plan = get_plan_by_id(plan_id, uid)
        if not plan:
            await query.edit_message_text("❌ Reja topilmadi.")
            return
        mark_done(plan_id, uid, 0)
        await query.edit_message_text(
            fmt_plan((*plan[:5], 0)),
            parse_mode="HTML",
            reply_markup=plans_keyboard(plan_id),
        )
        await query.message.reply_text(f"↩️ <b>{plan[1]}</b> bajarilmagan deb belgilandi!", parse_mode="HTML")

    elif data.startswith("del_"):
        plan_id = int(data.split("_")[1])
        plan = get_plan_by_id(plan_id, uid)
        if not plan:
            await query.edit_message_text("❌ Reja topilmadi.")
            return
        # Confirmation keyboard
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🗑 Ha, o'chirish", callback_data=f"delconfirm_{plan_id}"),
                InlineKeyboardButton("❌ Bekor", callback_data=f"delcancel_{plan_id}"),
            ]
        ])
        await query.message.reply_text(
            f"⚠️ <b>{plan[1]}</b> rejasini o'chirishni tasdiqlaysizmi?",
            parse_mode="HTML",
            reply_markup=kb,
        )

    elif data.startswith("delconfirm_"):
        plan_id = int(data.split("_")[1])
        plan = get_plan_by_id(plan_id, uid)
        title = plan[1] if plan else "Noma'lum"
        delete_plan(plan_id, uid)
        await query.edit_message_text(f"🗑 <b>{title}</b> muvaffaqiyatli o'chirildi!", parse_mode="HTML")

    elif data.startswith("delcancel_"):
        await query.edit_message_text("❌ O'chirish bekor qilindi.")

    elif data.startswith("edit_"):
        plan_id = int(data.split("_")[1])
        plan = get_plan_by_id(plan_id, uid)
        if not plan:
            await query.message.reply_text("❌ Reja topilmadi.")
            return
        context.user_data["edit_id"] = plan_id
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📌 Sarlavha", callback_data=f"editfield_{plan_id}_title"),
                InlineKeyboardButton("📅 Sana",     callback_data=f"editfield_{plan_id}_date"),
            ],
            [
                InlineKeyboardButton("🕐 Vaqt",     callback_data=f"editfield_{plan_id}_time"),
                InlineKeyboardButton("📝 Tavsif",   callback_data=f"editfield_{plan_id}_desc"),
            ],
            [InlineKeyboardButton("❌ Bekor",       callback_data="editcancel")],
        ])
        await query.message.reply_text(
            f"✏️ <b>{plan[1]}</b> – qaysi maydonni tahrirlash?",
            parse_mode="HTML",
            reply_markup=kb,
        )

    elif data.startswith("editfield_"):
        parts = data.split("_")
        plan_id = int(parts[1])
        field = parts[2]
        context.user_data["edit_id"] = plan_id
        context.user_data["edit_field"] = field

        labels = {
            "title": "Sarlavha",
            "date":  "Sana (masalan: 25.06.2025)",
            "time":  "Vaqt (masalan: 14:30)",
            "desc":  "Tavsif",
        }
        await query.message.reply_text(
            f"✏️ Yangi <b>{labels[field]}</b> kiriting:",
            parse_mode="HTML",
        )
        context.user_data["awaiting_edit"] = True

    elif data == "editcancel":
        context.user_data.clear()
        await query.edit_message_text("❌ Tahrirlash bekor qilindi.")

# ── EDIT VALUE MESSAGE HANDLER ────────────────────────────
async def edit_value_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_edit"):
        return

    uid = update.effective_user.id
    plan_id = context.user_data.get("edit_id")
    field = context.user_data.get("edit_field")
    value = update.message.text.strip()

    db_field_map = {
        "title": "title",
        "date":  "plan_date",
        "time":  "plan_time",
        "desc":  "description",
    }

    if field == "date":
        value = parse_date(value)
        if not value:
            await update.message.reply_text(
                "❌ Sana formati noto'g'ri! Masalan: <code>25.06.2025</code>",
                parse_mode="HTML",
            )
            return

    if field == "time":
        value = parse_time(value)
        if not value:
            await update.message.reply_text(
                "❌ Vaqt formati noto'g'ri! Masalan: <code>14:30</code>",
                parse_mode="HTML",
            )
            return

    update_plan_field(plan_id, db_field_map[field], value)
    context.user_data.clear()

    plan = get_plan_by_id(plan_id, uid)
    await update.message.reply_text(
        f"✅ <b>Muvaffaqiyatli yangilandi!</b>\n\n{fmt_plan(plan)}",
        parse_mode="HTML",
        reply_markup=plans_keyboard(plan_id),
    )

# ── KEYBOARD BUTTON TEXT HANDLER ──────────────────────────
async def keyboard_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "📋 Barcha rejalar":
        await cmd_all(update, context)
    elif text == "📅 Bugungi rejalar":
        await cmd_today(update, context)
    elif text == "✅ Bajarilganlar":
        await cmd_done_list(update, context)
    elif text == "⏳ Kutilayotganlar":
        await cmd_pending(update, context)
    elif text == "ℹ️ Yordam":
        await help_cmd(update, context)
    elif text == "➕ Reja qo'shish":
        await add_start(update, context)

# ── REMINDER JOB ─────────────────────────────────────────
async def send_reminders(context: ContextTypes.DEFAULT_TYPE):
    """Har 5 daqiqada tekshirib, vaqti yaqinlashgan rejalarga eslatma yuboradi."""
    rows = get_upcoming_unnotified(minutes=15)
    for row in rows:
        plan_id, user_id, title, pdate, ptime = row
        d = datetime.strptime(pdate, "%Y-%m-%d").strftime("%d.%m.%Y")
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    f"🔔 <b>Eslatma!</b>\n\n"
                    f"📌 <b>{title}</b>\n"
                    f"📅 {d}  🕐 {ptime}\n\n"
                    f"⏳ Bu reja 15 daqiqadan so'ng boshlanadi!"
                ),
                parse_mode="HTML",
            )
            mark_notified(plan_id)
        except Exception as e:
            logger.warning(f"Eslatma yuborishda xatolik (user={user_id}): {e}")

# ─────────────────────────── MAIN ───────────────────────────
def main():
    init_db()

    app = ApplicationBuilder().token(TOKEN).build()

    # ConversationHandler – reja qo'shish
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("add", add_start),
        ],
        states={
            ADD_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_title)],
            ADD_DATE:  [MessageHandler(filters.TEXT & ~filters.COMMAND, add_date)],
            ADD_TIME:  [MessageHandler(filters.TEXT & ~filters.COMMAND, add_time)],
            ADD_DESC:  [MessageHandler(filters.TEXT & ~filters.COMMAND, add_desc)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start",   start))
    app.add_handler(CommandHandler("help",    help_cmd))
    app.add_handler(CommandHandler("today",   cmd_today))
    app.add_handler(CommandHandler("all",     cmd_all))
    app.add_handler(CommandHandler("pending", cmd_pending))
    app.add_handler(CommandHandler("done",    cmd_done_list))
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(callback_handler))

    # Edit value handler (faqat awaiting_edit holatida)
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        edit_value_handler,
    ), group=1)

    # Keyboard button handler (group=2, past priority)
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        keyboard_handler,
    ), group=2)

    # Eslatma job – har 5 daqiqada
    app.job_queue.run_repeating(send_reminders, interval=300, first=10)
    
    logger.info("🤖 Planner Bot ishga tushdi...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
