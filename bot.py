import os
import logging
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from aiogram.enums import ParseMode
from aiogram.utils.chat_action import ChatActionSender
from aiogram.exceptions import TelegramBadRequest
from dotenv import load_dotenv
from openai import AsyncOpenAI

# Atrof-muhit o'zgaruvchilarini yuklash
load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not BOT_TOKEN or not OPENAI_API_KEY:
    raise ValueError(
        "DIQQAT: TELEGRAM_BOT_TOKEN va OPENAI_API_KEY muhit o'zgaruvchilari o'rnatilishi shart! "
        "Loyiha papkasida .env faylini yarating va unga kalitlarni yozing."
    )

# OpenAI Clientini yaratish
client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# Tizim yo'riqnomasi (System Prompt) - faqat dasturlash va IT sohasiga ruxsat berish
system_instruction = (
    "Siz faqat dasturlash, IT (axborot texnologiyalari), ma'lumotlar bazasi, veb-dasturlash, "
    "mobil dasturlash, sun'iy intellekt, algoritmlar va kompyuter ilmlariga (computer science) oid savollarga javob beradigan yordamchisiz. "
    "Agar foydalanuvchi boshqa mavzuda (masalan, ovqat pishirish, sport, ob-havo, siyosat, musiqa, tarix, umumiy suhbatlar va h.k.) savol bersa, "
    "muloyimlik bilan faqat dasturlash va IT ga oid savollarga javob bera olishingizni tushuntiring va javob berishdan mutlaqo bosh torting. "
    "Boshqa mavzulardagi savollarga hech qanday holatda javob bermang. Javoblarni o'zbek tilida, aniq, tushunarli, tizimli va chiroyli formatda taqdim eting. "
    "Dasturlashga doir savollarga javob berganda amaliy kod namunalarini ko'rsating va ularni izohlab bering."
)

# Logging (jurnal yuritish) sozlamalari
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Bot va Dispatcher obyektlarini yaratish
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(CommandStart())
async def command_start_handler(message: types.Message) -> None:
    """
    /start komandasi uchun handler. Foydalanuvchini kutib oladi.
    """
    user_name = message.from_user.full_name
    welcome_text = (
        f"Assalomu alaykum, {user_name}! 🚀\n\n"
        "Men faqat dasturlash, kompyuter texnologiyalari va IT sohasiga oid savollarga "
        "javob beruvchi sun'iy intellekt yordamchisiman (GPT). 💻\n\n"
        "Menga dasturlash tillari, algoritmlar, ma'lumotlar bazalari yoki IT sohasidagi "
        "har qanday texnik savolingizni yo'llashingiz mumkin.\n\n"
        "Sizga qanday yordam bera olaman?"
    )
    await message.answer(welcome_text)

@dp.message(Command("help"))
async def command_help_handler(message: types.Message) -> None:
    """
    /help komandasi uchun handler. Qoidalarni ko'rsatadi.
    """
    help_text = (
        "📖 **Botdan foydalanish bo'yicha yo'riqnoma:**\n\n"
        "1. **Faqat dasturlash va IT** sohasidagi savollarni so'rang.\n"
        "2. Boshqa mavzulardagi (masalan: tarix, geografiya, ovqatlar, sport, ob-havo) savollarga bot javob bermaydi.\n"
        "3. Savolni batafsil va tushunarli qilib yozsangiz, javob ham shunga yarasha aniq bo'ladi.\n\n"
        "💡 **Misol savollar:**\n"
        "• *Python-da ro'yxatni qanday tartiblash mumkin?*\n"
        "• *REST API va GraphQL o'rtasidagi farq nima?*\n"
        "• *Docker nima va u nima uchun kerak?*"
    )
    await message.answer(help_text, parse_mode=ParseMode.MARKDOWN)

@dp.message()
async def message_handler(message: types.Message) -> None:
    """
    Kelgan barcha matnli xabarlarni qayta ishlovchi handler.
    Xabarni olib OpenAI API'ga yuboradi va javobni foydalanuvchiga qaytaradi.
    """
    if not message.text:
        await message.answer("Iltimos, faqat matn ko'rinishidagi savollarni yuboring. ✍️")
        return

    # Foydalanuvchi javob kutayotganida 'typing...' statusini ko'rsatish
    async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
        try:
            # OpenAI API ga asinxron murojaat qilish
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": message.text}
                ]
            )
            
            answer_text = response.choices[0].message.content
            
            try:
                # Markdown formatida javobni yuborishga urinib ko'rish
                await message.answer(answer_text, parse_mode=ParseMode.MARKDOWN)
            except TelegramBadRequest:
                # Agar markdown formati Telegram qoidalariga mos kelmay xato bersa, oddiy matn ko'rinishida yuboriladi
                await message.answer(answer_text)
                
        except Exception as e:
            logging.error(f"OpenAI API yoki Telegram'da xatolik yuz berdi: {e}")
            await message.answer(
                "Kechirasiz, savolingizga javob olishda xatolik yuz berdi. "
                "Iltimos, bir ozdan so'ng qaytadan urinib ko'ring. 🔄"
            )

async def main() -> None:
    """
    Botni ishga tushirish (Long Polling)
    """
    logging.info("Bot ishga tushmoqda...")
    # Eski yangilanishlarni (updates) tozalab tashlash
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot to'xtatildi!")
