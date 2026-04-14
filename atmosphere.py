import asyncio
import os
import logging
import sqlite3
import threading
from flask import Flask
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.utils.deep_linking import create_start_link
from dotenv import load_dotenv

# --- МИКРО-СЕРВЕР (Для жизни на Render) ---
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
if ADMIN: ADMIN = int(ADMIN)

# НАСТРОЙКИ (Поменяй под себя)
PHONE_NUMBER = "+48 123 456 789"  # Твой номер BLIK
REVIEWS_URL = "https://t.me/+cbqxYZH0tzE4MDUy"

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- БАЗА ДАННЫХ ---
def init_db():
    with sqlite3.connect('cloude_base.db') as db:
        # Таблица юзеров + кто пригласил (для рефералки)
        db.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, referrer_id INTEGER)')
        # Таблица заказов со всеми деталями
        db.execute('''CREATE TABLE IF NOT EXISTS orders (
            order_id INTEGER PRIMARY KEY AUTOINCREMENT, 
            user_id INTEGER, 
            item_name TEXT, 
            flavor TEXT, 
            total INTEGER, 
            delivery TEXT, 
            info TEXT, 
            status TEXT DEFAULT "Pending")''')
        db.commit()

# --- АССОРТИМЕНТ ---
STOCKS = {
    "Husky Double Ice": {
        "flavors": ["Frosty Palm", "Wolfberry", "Chilly Kiwi", "Blueberry", "Explosive Red"],
        "photo": None # Сюда вставишь ID фото (инструкция ниже)
    },
    "ELFLIQ Salt": {
        "flavors": ["Blueberry Sour Raspberry", "Apple Peach", "Pink Lemonade", "Watermelon", "Cotton Candy"],
        "photo": None
    },
    "VOZOL 10000": {
        "flavors": ["Mixed Berries", "Watermelon Ice", "Grape Ice", "Miami Mint", "Sour Apple"],
        "photo": None
    }
}

# --- МЕНЮ ---
def get_main_menu():
    kb = ReplyKeyboardBuilder()
    kb.row(types.KeyboardButton(text="☁️ Витрина"), types.KeyboardButton(text="📥 Мои заказы"))
    kb.row(types.KeyboardButton(text="💰 Бонусы"), types.KeyboardButton(text="⭐️ Отзывы"))
    kb.row(types.KeyboardButton(text="🤝 Поддержка"))
    return kb.as_markup(resize_keyboard=True)

# --- ЛОГИКА БОТА ---

@dp.message(CommandStart())
async def cmd_start(msg: types.Message):
    # Логика реферальной ссылки
    args = msg.text.split()
    ref_id = args[1] if len(args) > 1 and args[1].isdigit() else None
    
    with sqlite3.connect('cloude_base.db') as db:
        db.execute("INSERT OR IGNORE INTO users (user_id, username, referrer_id) VALUES (?, ?, ?)", 
                   (msg.from_user.id, msg.from_user.username, ref_id))
    
    await msg.answer(f"Салют, {msg.from_user.first_name}! 👋\nДобро пожаловать в Cloude — твой дымный уголок в Кракове.", 
                     reply_markup=get_main_menu(), parse_mode="Markdown")

@dp.message(F.text == "☁️ Витрина")
async def show_cats(msg: types.Message):
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="🧂 Жидкости (45zł)", callback_data="cat_liq"))
    kb.row(types.InlineKeyboardButton(text="💨 Одноразки (45zł)", callback_data="cat_disp"))
    await msg.answer("✨ **Витрина Cloude**\nЧто ищем сегодня?", reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("cat_"))
async def brand_list(call: types.CallbackQuery):
    cat = call.data.split("_")[1]
    kb = InlineKeyboardBuilder()
    brands = ["Husky Double Ice", "ELFLIQ Salt"] if cat == "liq" else ["VOZOL 10000"]
    
    for brand in brands:
        kb.row(types.InlineKeyboardButton(text=brand, callback_data=f"brand_{brand}"))
    kb.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main"))
    
    await call.message.edit_text("🔥 Выбери бренд:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("brand_"))
async def flavor_list(call: types.CallbackQuery):
    brand = call.data.split("_")[1]
    data = STOCKS.get(brand)
    kb = InlineKeyboardBuilder()
    
    for f in data["flavors"]:
        kb.row(types.InlineKeyboardButton(text=f, callback_data=f"sel_{brand}_{f}_45"))
    kb.row(types.InlineKeyboardButton(text="⬅️ К брендам", callback_data="cat_liq"))
    
    # Если есть фото — шлем фото, если нет — текст
    if data["photo"]:
        await call.message.delete()
        await call.bot.send_photo(call.from_user.id, data["photo"], caption=f"🍒 **Вкусы {brand}:**", reply_markup=kb.as_markup())
    else:
        await call.message.edit_text(f"🍒 **Вкусы {brand}:**", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("sel_"))
async def delivery_choice(call: types.CallbackQuery):
    _, brand, flavor, price = call.data.split("_")
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="📦 InPost (+14zł)", callback_data=f"pay_{brand}_{flavor}_{int(price)+14}_InPost"))
    kb.row(types.InlineKeyboardButton(text="🤝 Самовывоз (Free)", callback_data=f"pay_{brand}_{flavor}_{price}_Pickup"))
    
    await call.message.answer(f"📍 **Доставка для {brand} ({flavor}):**\nКак тебе удобнее получить заказ?", reply_markup=kb.as_markup())
    await call.message.delete()

@dp.callback_query(F.data.startswith("pay_"))
async def pay_info(call: types.CallbackQuery):
    _, brand, flavor, total, delivery = call.data.split("_")
    
    text = (f"💳 **Оформление заказа**\n\n"
            f"Товар: {brand} ({flavor})\n"
            f"Доставка: {delivery}\n"
            f"**Сумма: {total}zł**\n\n"
            f"Переведи по BLIK на номер:\n`{PHONE_NUMBER}`\n\n"
            "После оплаты нажми кнопку ниже. Если выбрал InPost — бот спросит данные.")
    
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="✅ Оплачено (Подтвердить)", callback_data=f"confirm_{brand}_{flavor}_{total}_{delivery}"))
    kb.row(types.InlineKeyboardButton(text="❌ Отмена", callback_data="exit_shop"))
    await call.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("confirm_"))
async def confirm_order(call: types.CallbackQuery):
    _, brand, flavor, total, delivery = call.data.split("_")
    
    if delivery == "InPost":
        await call.message.answer("📝 **Почти готово!**\nПришли следующим сообщением данные для InPost:\n1. ФИО\n2. Номер телефона\n3. Код пачкомата")
        # Сохраняем черновик
        with sqlite3.connect('cloude_base.db') as db:
            db.execute("INSERT INTO orders (user_id, item_name, flavor, total, delivery, info) VALUES (?, ?, ?, ?, ?, ?)",
                       (call.from_user.id, brand, flavor, total, delivery, "Waiting for details..."))
    else:
        # Для самовывоза всё проще
        with sqlite3.connect('cloude_base.db') as db:
            db.execute("INSERT INTO orders (user_id, item_name, flavor, total, delivery, info) VALUES (?, ?, ?, ?, ?, ?)",
                       (call.from_user.id, brand, flavor, total, delivery, "Pickup requested"))
        
        if ADMIN:
            await bot.send_message(ADMIN, f"⚡️ **НОВЫЙ ЗАКАЗ (САМОВЫВОЗ)**\nЮзер: @{call.from_user.username}\nТовар: {brand} {flavor}")

        await call.message.edit_text("🚀 **Заказ принят!** Менеджер напишет тебе для согласования времени встречи.")

@dp.message(F.text == "💰 Бонусы")
async def bonus_system(msg: types.Message):
    # Генерируем реферальную ссылку
    link = await create_start_link(bot, str(msg.from_user.id), encode=True)
    await msg.answer(f"🎁 **Твои бонусы**\n\nПриглашай друзей и получай скидки на следующие заказы!\n\nТвоя ссылка для приглашения:\n`{link}`", parse_mode="Markdown")

@dp.message(F.text == "⭐️ Отзывы")
async def reviews(msg: types.Message):
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="📖 Смотреть отзывы", url=REVIEWS_URL))
    await msg.answer("Работаем честно и быстро. Глянь, что пишут другие 👇", reply_markup=kb.as_markup())

@dp.message(F.text == "📥 Мои заказы")
async def my_orders(msg: types.Message):
    with sqlite3.connect('cloude_base.db') as db:
        rows = db.execute("SELECT item_name, flavor, total, status FROM orders WHERE user_id = ? ORDER BY date DESC", (msg.from_user.id,)).fetchall()
    
    if not rows:
        return await msg.answer("Ты еще не делал заказов. Самое время начать! 😉")
    
    res = "📜 **Твоя история:**\n\n"
    for b, f, t, s in rows:
        res += f"▫️ {b} ({f}) — {t}zł\nСтатус: *{s}*\n\n"
    await msg.answer(res, parse_mode="Markdown")

@dp.message(F.text == "🤝 Поддержка")
async def help_support(msg: types.Message):
    await msg.answer("Возникли вопросы? Менеджер на связи: @твой_ник\nРаботаем 24/7 🚀")

# Хендлер для получения ID фоток (только для тебя)
@dp.message(F.photo)
async def get_photo_id(msg: types.Message):
    if msg.from_user.id == ADMIN:
        await msg.answer(f"Лови ID этой фотки для кода:\n`{msg.photo[-1].file_id}`")

# Запуск
async def main():
    init_db()
    threading.Thread(target=run_server, daemon=True).start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())