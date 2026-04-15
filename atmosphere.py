import asyncio
import os
import logging
import sqlite3
import threading
from flask import Flask
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import BotCommand
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.utils.deep_linking import create_start_link
from dotenv import load_dotenv

# --- ЧАСТЬ 1: СЕРВЕР ДЛЯ ПОДДЕРЖАНИЯ ЖИЗНИ ---
app = Flask('')

@app.route('/')
def home():
    return "Cloude Status: Active and Running"

def run_server():
    app.run(host='0.0.0.0', port=8080)

# --- ЧАСТЬ 2: НАСТРОЙКИ И ПЕРЕМЕННЫЕ ---
load_dotenv()
logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID_ENV = os.getenv('ADMIN_ID')

if ADMIN_ID_ENV:
    ADMIN = int(ADMIN_ID_ENV)
else:
    ADMIN = None

# Твои данные
PHONE_NUMBER = "+48 123 456 789"  # ЗАМЕНИ НА СВОЙ НОМЕР БЛИК
REVIEWS_URL = "https://t.me/+cbqxYZH0tzE4MDUy"

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- ЧАСТЬ 3: РАБОТА С БАЗОЙ ДАННЫХ ---
def init_db():
    conn = sqlite3.connect('cloude_base.db')
    cur = conn.cursor()
    # Таблица пользователей
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, 
            username TEXT, 
            referrer_id INTEGER
        )
    ''')
    # Таблица заказов (максимально подробная)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            order_id INTEGER PRIMARY KEY AUTOINCREMENT, 
            user_id INTEGER, 
            item_name TEXT, 
            flavor TEXT, 
            total INTEGER, 
            delivery TEXT, 
            info TEXT, 
            status TEXT DEFAULT "Ожидает оплаты",
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

# --- ЧАСТЬ 4: АССОРТИМЕНТ ТОВАРОВ ---
STOCKS = {
    "Husky Double Ice": {
        "flavors": ["Frosty Palm", "Wolfberry", "Chilly Kiwi", "Blueberry", "Explosive Red", "Arctic Strike"],
        "photo": None
    },
    "ELFLIQ Salt": {
        "flavors": ["Blueberry Sour Raspberry", "Apple Peach", "Pink Lemonade", "Watermelon", "Kiwi Guava", "Cotton Candy"],
        "photo": None
    },
    "VOZOL 10000": {
        "flavors": ["Mixed Berries", "Watermelon Ice", "Grape Ice", "Miami Mint", "Sour Apple", "Peach Ice"],
        "photo": None
    }
}

# --- ЧАСТЬ 5: КНОПКИ МЕНЮ ---
async def set_main_menu_button(bot: Bot):
    commands = [
        BotCommand(command='/start', description='Главное меню / Запуск'),
        BotCommand(command='/help', description='Помощь и поддержка')
    ]
    await bot.set_my_commands(commands)

def get_main_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.row(types.KeyboardButton(text="☁️ Витрина"), types.KeyboardButton(text="📥 Мои заказы"))
    builder.row(types.KeyboardButton(text="💰 Бонусы"), types.KeyboardButton(text="⭐️ Отзывы"))
    builder.row(types.KeyboardButton(text="🤝 Поддержка"))
    return builder.as_markup(resize_keyboard=True)

# --- ЧАСТЬ 6: ОБРАБОТКА СООБЩЕНИЙ ---

@dp.message(CommandStart())
async def start_handler(message: types.Message):
    # Рефералка
    start_command = message.text.split()
    referrer = start_command[1] if len(start_command) > 1 and start_command[1].isdigit() else None
    
    db = sqlite3.connect('cloude_base.db')
    db.execute("INSERT OR IGNORE INTO users (user_id, username, referrer_id) VALUES (?, ?, ?)", 
               (message.from_user.id, message.from_user.username, referrer))
    db.commit()
    db.close()
    
    welcome_text = (
        f"Здарова, {message.from_user.first_name}! 👋\n\n"
        "Ты попал в **Cloude Atmosphere**. Самое лучшее качество - здесь :).\n\n"
        "Пользуйся меню снизу, чтобы сделать заказ. Если возникнут вопросы — жми 'Поддержка'."
    )
    await message.answer(welcome_text, reply_markup=get_main_keyboard(), parse_mode="Markdown")

@dp.message(F.text == "☁️ Витрина")
async def catalog_handler(message: types.Message):
    keyboard = InlineKeyboardBuilder()
    keyboard.row(types.InlineKeyboardButton(text="🧂 Жидкости (Husky, Elfliq)", callback_data="cat_liq"))
    keyboard.row(types.InlineKeyboardButton(text="💨 Одноразки (Vozol)", callback_data="cat_disp"))
    await message.answer("✨ **Каталог продукции**\nВыбери нужную категорию:", reply_markup=keyboard.as_markup())

@dp.callback_query(F.data.startswith("cat_"))
async def brands_callback(call: types.CallbackQuery):
    category = call.data.split("_")[1]
    keyboard = InlineKeyboardBuilder()
    
    if category == "liq":
        brands = ["Husky Double Ice", "ELFLIQ Salt"]
    else:
        brands = ["VOZOL 10000"]
        
    for brand in brands:
        keyboard.row(types.InlineKeyboardButton(text=brand, callback_data=f"brand_{brand}"))
    
    keyboard.row(types.InlineKeyboardButton(text="⬅️ Назад к категориям", callback_data="back_to_cats"))
    await call.message.edit_text("🔥 **Доступные бренды:**", reply_markup=keyboard.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("brand_"))
async def flavors_callback(call: types.CallbackQuery):
    brand_name = call.data.split("_")[1]
    brand_data = STOCKS.get(brand_name)
    keyboard = InlineKeyboardBuilder()
    
    for flavor in brand_data["flavors"]:
        keyboard.row(types.InlineKeyboardButton(text=flavor, callback_data=f"select_{brand_name}_{flavor}_45"))
    
    # Кнопка возврата
    prev_cat = "cat_liq" if brand_name != "VOZOL 10000" else "cat_disp"
    keyboard.row(types.InlineKeyboardButton(text="⬅️ Назад к брендам", callback_data=prev_cat))
    
    if brand_data["photo"]:
        await call.message.delete()
        await call.bot.send_photo(call.from_user.id, brand_data["photo"], caption=f"🍒 **Вкусы {brand_name}:**", reply_markup=keyboard.as_markup())
    else:
        await call.message.edit_text(f"🍒 **Вкусы {brand_name}:**\nВыбирай свой вариант:", reply_markup=keyboard.as_markup())

@dp.callback_query(F.data.startswith("select_"))
async def delivery_callback(call: types.CallbackQuery):
    _, brand, flavor, price = call.data.split("_")
    keyboard = InlineKeyboardBuilder()
    
    keyboard.row(types.InlineKeyboardButton(text="📦 InPost (+14zł)", callback_data=f"pay_{brand}_{flavor}_{int(price)+14}_InPost"))
    keyboard.row(types.InlineKeyboardButton(text="🤝 Самовывоз Краков (Free)", callback_data=f"pay_{brand}_{flavor}_{price}_Pickup"))
    keyboard.row(types.InlineKeyboardButton(text="⬅️ Назад к вкусам", callback_data=f"brand_{brand}"))
    
    await call.message.answer(f"📍 **Оформление:** {brand} — {flavor}\n\nВыбери способ получения:", reply_markup=keyboard.as_markup())
    await call.message.delete()

@dp.callback_query(F.data.startswith("pay_"))
async def payment_callback(call: types.CallbackQuery):
    _, brand, flavor, total, delivery = call.data.split("_")
    
    pay_text = (
        f"💳 **Оплата заказа**\n\n"
        f"Товар: {brand} ({flavor})\n"
        f"Способ: {delivery}\n"
        f"**Сумма к оплате: {total}zł**\n\n"
        f"Переведи ровную сумму по BLIK на номер:\n`{PHONE_NUMBER}`\n\n"
        "После совершения платежа обязательно нажми кнопку ниже!"
    )
    
    keyboard = InlineKeyboardBuilder()
    keyboard.row(types.InlineKeyboardButton(text="✅ Я оплатил(а)", callback_data=f"finish_{brand}_{flavor}_{total}_{delivery}"))
    keyboard.row(types.InlineKeyboardButton(text="❌ Отменить", callback_data="back_to_cats"))
    
    await call.message.edit_text(pay_text, reply_markup=keyboard.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("finish_"))
async def finish_callback(call: types.CallbackQuery):
    _, b, f, t, d = call.data.split("_")
    
    db = sqlite3.connect('cloude_base.db')
    db.execute("INSERT INTO orders (user_id, item_name, flavor, total, delivery, info) VALUES (?, ?, ?, ?, ?, ?)",
               (call.from_user.id, b, f, t, d, "Ожидаем подтверждение"))
    db.commit()
    db.close()
    
    if d == "InPost":
        instruction = "📝 **Важно!**\nПришли следующим сообщением данные для InPost:\n1. Твои ФИО\n2. Номер телефона\n3. Код пачкомата (напр. KRA01M)"
        await call.message.answer(instruction)
    else:
        if ADMIN:
            await bot.send_message(ADMIN, f"⚡️ **НОВЫЙ ЗАКАЗ (САМОВЫВОЗ)**\nЮзер: @{call.from_user.username}\nТовар: {b} {f}\nСумма: {t}zł")
        await call.message.answer("🚀 **Заказ принят!** Менеджер свяжется с тобой для передачи товара.")

# --- ЧАСТЬ 7: ОБРАБОТКА ТЕКСТА (ДАННЫЕ INPOST И ПЕРЕСЫЛКА АДМИНУ) ---
@dp.message(F.text, ~F.text.startswith("/"))
async def text_handler(message: types.Message):
    # Ищем последний заказ этого юзера
    db = sqlite3.connect('cloude_base.db')
    cursor = db.cursor()
    cursor.execute("SELECT order_id, item_name, flavor, total FROM orders WHERE user_id = ? ORDER BY date DESC LIMIT 1", (message.from_user.id,))
    order = cursor.fetchone()
    
    if order:
        order_id, item, flavor, total = order
        # Обновляем инфо в базе
        cursor.execute("UPDATE orders SET info = ?, status = 'Данные получены' WHERE order_id = ?", (message.text, order_id))
        db.commit()
        
        await message.answer("✅ **Данные получены!**\nМенеджер проверит оплату и отправит твой заказ. Спасибо, что выбрал Cloude!")
        
        # Уведомляем админа
        if ADMIN:
            admin_report = (
                f"💰 **НОВЫЙ ЗАКАЗ (InPost)**\n"
                f"От: @{message.from_user.username}\n"
                f"Товар: {item} - {flavor}\n"
                f"Сумма: {total}zł\n"
                f"Данные: {message.text}"
            )
            await bot.send_message(ADMIN, admin_report)
    else:
        await message.answer("Используй кнопки меню для заказа. Если есть вопросы — пиши в поддержку.")
    db.close()

# --- ЧАСТЬ 8: ПРОЧИЕ ФУНКЦИИ ---

@dp.message(F.text == "💰 Бонусы")
async def bonus_handler(message: types.Message):
    link = await create_start_link(bot, str(message.from_user.id), encode=True)
    await message.answer(f"🎁 **Твоя реферальная ссылка:**\n\n`{link}`\n\nПриглашай друзей и получай бонусы на свой баланс!", parse_mode="Markdown")

@dp.message(F.text == "⭐️ Отзывы")
async def reviews_handler(message: types.Message):
    keyboard = InlineKeyboardBuilder()
    keyboard.row(types.InlineKeyboardButton(text="📖 Перейти в канал", url=REVIEWS_URL))
    await message.answer("Честные отзывы наших покупателей здесь 👇", reply_markup=keyboard.as_markup())

@dp.message(F.text == "📥 Мои заказы")
async def my_orders_handler(message: types.Message):
    db = sqlite3.connect('cloude_base.db')
    rows = db.execute("SELECT item_name, flavor, total, status FROM orders WHERE user_id = ? ORDER BY date DESC LIMIT 5", (message.from_user.id,)).fetchall()
    db.close()
    
    if not rows:
        return await message.answer("У тебя пока нет заказов.")
    
    text = "📜 **Последние заказы:**\n\n"
    for item, flav, tot, stat in rows:
        text += f"▪️ {item} ({flav}) — {tot}zł\nСтатус: *{stat}*\n\n"
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "🤝 Поддержка")
async def support_handler(message: types.Message):
    await message.answer("Связь с менеджером: @твой_ник\nПиши по любым вопросам! 🚀")

@dp.callback_query(F.data == "back_to_cats")
async def back_to_cats(call: types.CallbackQuery):
    keyboard = InlineKeyboardBuilder()
    keyboard.row(types.InlineKeyboardButton(text="🧂 Жидкости", callback_data="cat_liq"))
    keyboard.row(types.InlineKeyboardButton(text="💨 Одноразки", callback_data="cat_disp"))
    await call.message.edit_text("✨ **Каталог Cloude**", reply_markup=keyboard.as_markup())

@dp.message(F.photo)
async def photo_id_helper(message: types.Message):
    if message.from_user.id == ADMIN:
        await message.answer(f"ID фото для кода:\n`{message.photo[-1].file_id}`")

# --- ЗАПУСК ---
async def main():
    init_db()
    await set_main_menu_button(bot)
    threading.Thread(target=run_server, daemon=True).start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())