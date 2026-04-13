import asyncio
import os
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.utils.keyboard import ReplyKeyboardBuilder

# Включаем логирование, чтобы видеть ошибки в консоли Render/Codespaces
logging.basicConfig(level=logging.INFO)

# Вытягиваем токен из настроек (Environment Variables)
BOT_TOKEN = os.getenv('BOT_TOKEN')

if not BOT_TOKEN:
    print("ОШИБКА: Токен не найден! Проверь настройки Environment Variables.")
    exit()

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- ФУНКЦИЯ ДЛЯ ГЛАВНОГО МЕНЮ ---
def main_menu_kb():
    builder = ReplyKeyboardBuilder()
    builder.row(types.KeyboardButton(text="☁️ Витрина"), types.KeyboardButton(text="📥 Корзина"))
    builder.row(types.KeyboardButton(text="📜 История заказов"), types.KeyboardButton(text="🤝 Поддержка"))
    return builder.as_markup(resize_keyboard=True)

# --- ОБРАБОТКА КОМАНДЫ /START ---
@dp.message(CommandStart())
async def start_command(message: types.Message):
    await message.answer(
        f"Привет, {message.from_user.first_name}! 👋\n\n"
        "Добро пожаловать в **Cloude** — место с правильной атмосферой. "
        "Выбирай лучшие жижки и девайсы в нашем меню ниже. 👇",
        reply_markup=main_menu_kb(),
        parse_mode="Markdown"
    )

# --- ОБРАБОТКА КНОПКИ ВИТРИНА ---
@dp.message(F.text == "☁️ Витрина")
async def shop_catalog(message: types.Message):
    # Пока просто текст, позже прикрутим инлайн-кнопки с товарами
    await message.answer(
        "💨 **Наша Витрина**\n\n"
        "1. Солевые жидкости (Salt)\n"
        "2. Щелочные жидкости\n"
        "3. Одноразовые POD-системы\n\n"
        "Что тебя интересует?",
        parse_mode="Markdown"
    )

# --- ОБРАБОТКА КНОПКИ ПОДДЕРЖКА ---
@dp.message(F.text == "🤝 Поддержка")
async def support_info(message: types.Message):
    await message.answer(
        "Возникли вопросы? Пиши нашему менеджеру: @твой_юзернейм\n"
        "Доставка по Кракову в течение часа! 🚀"
    )

# --- ЗАПУСК БОТА ---
async def main():
    try:
        print("--- Бот Cloude успешно запущен ---")
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Бот остановлен")