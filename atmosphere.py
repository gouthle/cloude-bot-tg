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

# --- МИКРО-СЕРВЕР ДЛЯ RENDER ---
app = Flask('')
@app.route('/')
def home(): return "Cloude Status: Active"

def run_server():
    app.run(host='0.0.0.0', port=8080)

# --- ИНИЦИАЛИЗАЦИЯ ---
load_dotenv()
logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv('BOT_TOKEN')
ADMIN = os.getenv('ADMIN_ID')
if ADMIN: 
    ADMIN = int(ADMIN)

# НАСТРОЙКИ
PHONE_NUMBER = "+48 123 456 789"  # ЗАМЕНИ НА СВОЙ НОМЕР БЛИК
REVIEWS_URL = "https://t.me/+cbqxYZH0tzE4MDUy"

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- СИНЯЯ КНОПКА МЕНЮ ---
async def set_main_menu(bot: Bot):
    main_menu_commands = [
        BotCommand(command='/start', description='Запустить бота / Главное меню'),
        BotCommand(command='/help', description='Связаться с менеджером')
    ]
    await bot.set_my_commands(main_menu_commands)

# --- БАЗА ДАННЫХ ---
def init_db():
    with sqlite3.connect('cloude_base.db') as db:
        cur = db.cursor()
        # Таблица пользователей
        cur.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, 
            username TEXT, 
            referrer_id INTEGER)''')
        # Таблица заказов
        cur.execute('''CREATE TABLE IF NOT EXISTS orders (
            order_id INTEGER PRIMARY KEY AUTOINCREMENT, 
            user_id INTEGER, 
            item_name TEXT, 
            flavor TEXT, 
            total INTEGER, 
            delivery TEXT, 
            info TEXT, 
            status TEXT DEFAULT "Ожидает оплаты",
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        db.commit()

# --- АССОРТИМЕНТ ---
STOCKS = {
    "Husky Double Ice": {
        "flavors": ["Frosty Palm", "Wolfberry", "Chilly Kiwi", "Blueberry", "Explosive Red", "Arctic Strike"],
        "photo": None # Сюда вставить file_id после получения
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

# --- КЛАВИАТУРЫ ---
def get_main_menu_kb():
    kb = ReplyKeyboardBuilder()
    kb.row(types.KeyboardButton(text="☁️ Витрина"), types.KeyboardButton(text="📥 Мои заказы"))
    kb.row(types.KeyboardButton(text="💰 Бонусы"), types.KeyboardButton(text="⭐️ Отзывы"))
    kb.row(types.KeyboardButton(text="🤝 Поддержка"))
    return kb.as_markup(resize_keyboard=True)

# --- ОБРАБОТКА КОМАНД ---

@dp.message(CommandStart())
async def cmd_start(msg: types.Message):
    args = msg.text.split()
    ref_id = args[1] if len(args) > 1 and args[1].isdigit() else None
    
    with sqlite3.connect('cloude_base.db') as db:
        db.execute("INSERT OR IGNORE INTO users (user_id, username, referrer_id) VALUES (?, ?, ?)", 
                   (msg.from_user.id, msg.from_user.username, ref_id))
    
    await msg.answer(
        f"Здарова, {msg.from_user.first_name}! 👋\n\n"
        "Добро пожаловать в **Cloude Atmosphere**. \n"
        "Лучший ассортимент и быстрая доставка в Кракове.\n\n"
        "Выбирай что нужно на витрине! 👇", 
        reply_markup=get_main_menu_kb(), 
        parse_mode="Markdown"
    )

@dp.message(F.text == "☁️ Витрина")
async def show_catalog(msg: types.Message):
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="🧂 Жидкости (Husky/Elfliq)", callback_data="cat_liq"))
    kb.row(types.InlineKeyboardButton(text="💨 Одноразки (Vozol)", callback_data="cat_disp"))
    await msg.answer("✨ **Каталог Cloude**\nВыбери категорию товара:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("cat_"))
async def brand_list(call: types.CallbackQuery):
    cat = call.data.split("_")[1]
    kb = InlineKeyboardBuilder()
    if cat == "liq":
        brands = ["Husky Double Ice", "ELFLIQ Salt"]
    else:
        brands = ["VOZOL 10000"]
    
    for b in brands:
        kb.row(types.InlineKeyboardButton(text=b, callback_data=f"brand_{b}"))
    kb.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="exit_shop"))
    await call.message.edit_text("🔥 **Выбери бренд:**", reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("brand_"))
async def flavor_list(call: types.CallbackQuery):
    brand = call.data.split("_")[1]
    data = STOCKS.get(brand)
    kb = InlineKeyboardBuilder()
    
    for f in data["flavors"]:
        kb.row(types.InlineKeyboardButton(text=f, callback_data=f"sel_{brand}_{f}_45"))
    
    back_cat = "cat_liq" if "Husky" in brand or "ELFLIQ" in brand else "cat_disp"
    kb.row(types.InlineKeyboardButton(text="⬅️ К брендам", callback_data=back_cat))
    
    if data["photo"]:
        await call.message.delete()
        await call.bot.send_photo(call.from_user.id, data["photo"], caption=f"🍒 **Вкусы {brand}:**\nВыбирай модель:", reply_markup=kb.as_markup())
    else:
        await call.message.edit_text(f"🍒 **Вкусы {brand}:**\nВыбирай модель:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("sel_"))
async def delivery_choice(call: types.CallbackQuery):
    _, brand, flavor, price = call.data.split("_")
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="📦 InPost (+14zł)", callback_data=f"pay_{brand}_{flavor}_{int(price)+14}_InPost"))
    kb.row(types.InlineKeyboardButton(text="🤝 Самовывоз (Free)", callback_data=f"pay_{brand}_{flavor}_{price}_Pickup"))
    kb.row(types.InlineKeyboardButton(text="⬅️ К вкусам", callback_data=f"brand_{brand}"))
    
    await call.message.answer(f"📍 **Выбор доставки:**\n{brand} — {flavor}\n\nКак планируешь забирать?", reply_markup=kb.as_markup())
    await call.message.delete()

@dp.callback_query(F.data.startswith("pay_"))
async def pay_info(call: types.CallbackQuery):
    _, brand, flavor, total, delivery = call.data.split("_")
    text = (f"💳 **Оплата заказа**\n\n"
            f"Товар: {brand} ({flavor})\n"
            f"Доставка: {delivery}\n"
            f"**Итого к оплате: {total}zł**\n\n"
            f"Переведи сумму по BLIK на номер:\n`{PHONE_NUMBER}`\n\n"
            f"После подтверждения в банке нажми кнопку ниже 👇")
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="✅ Оплачено", callback_data=f"confirm_{brand}_{flavor}_{total}_{delivery}"))
    kb.row(types.InlineKeyboardButton(text="❌ Отмена", callback_data="exit_shop"))
    await call.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("confirm_"))
async def confirm_order(call: types.CallbackQuery):
    _, brand, flavor, total, delivery = call.data.split("_")
    
    if delivery == "InPost":
        # Если InPost, сначала просим данные
        await call.message.answer("📝 **Данные для доставки InPost**\n\nПришли одним сообщением:\n1. ФИО\n2. Номер телефона\n3. Код пачкомата (например, KRA01M)")
        # Техническая запись в БД
        with sqlite3.connect('cloude_base.db') as db:
            db.execute("INSERT INTO orders (user_id, item_name, flavor, total, delivery, info) VALUES (?, ?, ?, ?, ?, ?)",
                       (call.from_user.id, brand, flavor, total, delivery, "Ожидаем данные InPost"))
    else:
        # Самовывоз
        with sqlite3.connect('cloude_base.db') as db:
            db.execute("INSERT INTO orders (user_id, item_name, flavor, total, delivery, info) VALUES (?, ?, ?, ?, ?, ?)",
                       (call.from_user.id, brand, flavor, total, delivery, "Самовывоз Краков"))
        
        if ADMIN:
            try: await bot.send_message(ADMIN, f"⚡️ **ЗАКАЗ (САМОВЫВОЗ)**\nЮзер: @{call.from_user.username}\nТовар: {brand} {flavor}\nСумма: {total}zł")
            except: pass
        
        await call.message.edit_text("🚀 **Заказ принят!**\nМенеджер свяжется с тобой через пару минут для уточнения места встречи.")

@dp.message(F.text == "💰 Бонусы")
async def bonuses(msg: types.Message):
    link = await create_start_link(bot, str(msg.from_user.id), encode=True)
    await msg.answer(
        f"🎁 **Реферальная система Cloude**\n\n"
        f"Приглашай друзей и получай бонусы на свой счет!\n\n"
        f"Твоя личная ссылка:\n`{link}`", 
        parse_mode="Markdown"
    )

@dp.message(F.text == "⭐️ Отзывы")
async def reviews(msg: types.Message):
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="📖 Читать отзывы", url=REVIEWS_URL))
    await msg.answer("Нам доверяют лучшие. Посмотри отзывы наших клиентов 👇", reply_markup=kb.as_markup())

@dp.message(F.text == "📥 Мои заказы")
async def my_orders(msg: types.Message):
    with sqlite3.connect('cloude_base.db') as db:
        rows = db.execute("SELECT item_name, flavor, total, status FROM orders WHERE user_id = ? ORDER BY date DESC LIMIT 5", (msg.from_user.id,)).fetchall()
    
    if not rows:
        return await msg.answer("У тебя пока нет активных заказов. Пора это исправить! 😉")
    
    res = "📜 **Твои последние заказы:**\n\n"
    for b, f, t, s in rows:
        res += f"▫️ {b} ({f}) — {t}zł\nСтатус: *{s}*\n\n"
    await msg.answer(res, parse_mode="Markdown")

@dp.message(F.text == "🤝 Поддержка")
async def help_support(msg: types.Message):
    await msg.answer("Есть вопросы или предложения? \n\nМенеджер: @твой_ник\nРаботаем по всему Кракову! 🚀")

@dp.callback_query(F.data == "exit_shop")
async def exit_shop(call: types.CallbackQuery):
    await call.message.delete()
    await call.message.answer("Главное меню:", reply_markup=get_main_menu_kb())

# ХЕНДЛЕР ФОТО (Для админа, чтобы получить ID картинок)
@dp.message(F.photo)
async def get_photo_id(msg: types.Message):
    if msg.from_user.id == ADMIN:
        await msg.answer(f"ID твоей фотки:\n`{msg.photo[-1].file_id}`", parse_mode="Markdown")

# --- ЗАПУСК ---
async def main():
    init_db()
    # Ставим кнопку меню
    await set_main_menu(bot)
    # Запуск сервера
    threading.Thread(target=run_server, daemon=True).start()
    # Поллинг
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())