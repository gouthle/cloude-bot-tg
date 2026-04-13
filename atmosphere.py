import asyncio
import os
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from dotenv import load_dotenv

# Настройка логирования, чтобы видеть ошибки в консоли Codespaces
logging.basicConfig(level=logging.INFO)

load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- КЛАВИАТУРЫ ---
def main_kb():
    buttons = [
        [types.KeyboardButton(text="☁️ Витрина"), types.KeyboardButton(text="📥 Корзина")],
        [types.KeyboardButton(text="📜 История"), types.KeyboardButton(text="🤝 Контакты")]
    ]
    return types.ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# --- ХЕНДЛЕРЫ ---
@dp.message(CommandStart())
async def start_handler(message: types.Message):
    await message.answer(
        f"Добро пожаловать в **Cloude**, {message.from_user.first_name}!\n\n"
        "Создаем правильную атмосферу вместе с лучшими вкусами. 🌬",
        reply_markup=main_kb(),
        parse_mode="Markdown"
    )

@dp.message(F.text == "☁️ Витрина")
async def catalog_handler(message: types.Message):
    await message.answer("Выберите категорию:\n\n1. Солевые (Salt)\n2. Щелочные\n3. Одноразки")

# --- ЗАПУСК ---
async def main():
    try:
        print("Бот Cloude запущен и создает атмосферу...")
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())