import asyncio
import os
import logging
import sqlite3
import threading
from flask import Flask
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from dotenv import load_dotenv

# --- Server для Render ---
app = Flask('')
@app.route('/')
def home(): return "Cloude: Online"

def run_server():
    app.run(host='0.0.0.0', port=8080)

# --- Настройки ---
load_dotenv()
logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv('BOT_TOKEN')
ADMIN = os.getenv('ADMIN_ID')
if ADMIN: ADMIN = int(ADMIN)

# Твой номер для BLIK и ссылка на отзывы
PHONE_NUMBER = "+48 123 456 789" 
REVIEWS_URL = "https://t.me/+cbqxYZH0tzE4MDUy"

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- База данных ---
def init_db():
    with sqlite3.connect('cloude_base.db') as db:
        db.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT)')
        db.execute('CREATE TABLE IF NOT EXISTS orders (user_id INTEGER, item_name TEXT, flavor TEXT, total INTEGER, delivery TEXT, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')

# --- Ассортимент вкусов ---
STOCKS = {
    "Husky Double Ice": [
        "Frosty Palm", "Wolfberry", "Chilly Kiwi", 
        "Blueberry", "Explosive Red", "Arctic Strike"
    ],
    "ELFLIQ Salt": [
        "Blueberry Sour Raspberry", "Apple Peach", "Pink Lemonade", 
        "Watermelon", "Kiwi Passion Fruit Guava", "Blue Razz Lemonade",
        "Cotton Candy Ice", "Spearmint", "Strawberry Ice"
    ],
    "VOZOL 10000": [
        "Mixed Berries", "Watermelon Ice", "Grape Ice", 
        "Blue Razz Ice", "Strawberry Raspberry", "Peach Ice",
        "Miami Mint", "Sour Apple", "Kiwi Guava Passion"
    ]
}

# --- Кнопки меню ---
def main_kb():
    kb = ReplyKeyboardBuilder()
    kb.row(types.KeyboardButton(text="☁️ Витрина"), types.KeyboardButton(text="📥 Мои заказы"))
    kb.row(types.KeyboardButton(text="⭐️ Отзывы"), types.KeyboardButton(text="🤝 Поддержка"))
    return kb.as_markup(resize_keyboard=True)

def cats_kb():
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="🧂 Жидкости", callback_data="cat_liq"))
    kb.row(types.InlineKeyboardButton(text="💨 Одноразки", callback_data="cat_disp"))
    kb.row(types.InlineKeyboardButton(text="❌ Закрыть", callback_data="exit"))
    return kb.as_markup()

# --- Обработка команд ---

@dp.message(CommandStart())
async def start(msg: types.Message):
    with sqlite3.connect('cloude_base.db') as db:
        db.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", 
                   (msg.from_user.id, msg.from_user.username))
    await msg.answer(f"Здарова, {msg.from_user.first_name}! 👋\nВыбирай товар в **Cloude**:", 
                     reply_markup=main_kb(), parse_mode="Markdown")

@dp.message(F.text == "☁️ Витрина")
async def open_shop(msg: types.Message):
    await msg.answer("Секунду, открываю каталог...", reply_markup=types.ReplyKeyboardRemove())
    await msg.answer("✨ **Каталог Cloude**\nВыбери раздел:", reply_markup=cats_kb(), parse_mode="Markdown")

@dp.message(F.text == "⭐️ Отзывы")
async def show_reviews(msg: types.Message):
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="📖 Читать отзывы", url=REVIEWS_URL))
    await msg.answer("Наши клиенты говорят сами за себя! 👇", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("cat_"))
async def list_brands(call: types.CallbackQuery):
    cat = call.data.split("_")[1]
    kb = InlineKeyboardBuilder()
    
    if cat == "liq":
        brands = ["Husky Double Ice", "ELFLIQ Salt"]
    else:
        brands = ["VOZOL 10000"]

    for b in brands:
        kb.row(types.InlineKeyboardButton(text=b, callback_data=f"brand_{b}"))
    
    kb.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_cats"))
    await call.message.edit_text("🔥 Выбери бренд:", reply_markup=kb.as_markup())
    await call.answer()

@dp.callback_query(F.data.startswith("brand_"))
async def list_flavors(call: types.CallbackQuery):
    brand = call.data.split("_")[1]
    kb = InlineKeyboardBuilder()
    
    flavors = STOCKS.get(brand, ["Standard"])
    for f in flavors:
        kb.row(types.InlineKeyboardButton(text=f, callback_data=f"sel_{brand}_{f}_45"))
    
    prev = "cat_liq" if "Salt" in brand or "Husky" in brand else "cat_disp"
    kb.row(types.InlineKeyboardButton(text="⬅️ К брендам", callback_data=prev))
    
    await call.message.edit_text(f"🍒 **Вкусы {brand}:**", reply_markup=kb.as_markup())
    await call.answer()

@dp.callback_query(F.data.startswith("sel_"))
async def select_delivery(call: types.CallbackQuery):
    _, brand, flavor, price = call.data.split("_")
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="📦 InPost (+14zł)", callback_data=f"pay_{brand}_{flavor}_{int(price)+14}_InPost"))
    kb.row(types.InlineKeyboardButton(text="🤝 Самовывоз (Free)", callback_data=f"pay_{brand}_{flavor}_{price}_Pickup"))
    kb.row(types.InlineKeyboardButton(text="⬅️ Назад к вкусам", callback_data=f"brand_{brand}"))
    
    await call.message.edit_text(f"📍 **Доставка:**\n{brand} — {flavor}\n\nКак заберешь?", reply_markup=kb.as_markup())
    await call.answer()

@dp.callback_query(F.data.startswith("pay_"))
async def payment(call: types.CallbackQuery):
    _, brand, flavor, total, delivery = call.data.split("_")
    
    text = (f"💳 **Оплата заказа**\n\n"
            f"Товар: {brand} ({flavor})\n"
            f"Тип: {delivery}\n"
            f"**Итого: {total}zł**\n\n"
            f"Переведи сумму по BLIK на номер:\n`{PHONE_NUMBER}`\n\n"
            f"Как только переведешь — жми кнопку ниже.")
    
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="✅ Оплачено", callback_data=f"done_{brand}_{flavor}_{total}_{delivery}"))
    kb.row(types.InlineKeyboardButton(text="❌ Отмена", callback_data="exit"))
    
    await call.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="Markdown")
    await call.answer()

@dp.callback_query(F.data.startswith("done_"))
async def order_done(call: types.CallbackQuery):
    _, brand, flavor, total, delivery = call.data.split("_")
    
    with sqlite3.connect('cloude_base.db') as db:
        db.execute("INSERT INTO orders (user_id, item_name, flavor, total, delivery) VALUES (?, ?, ?, ?, ?)", 
                   (call.from_user.id, brand, flavor, total, delivery))
    
    if ADMIN:
        try:
            admin_msg = (f"💰 **НОВЫЙ ЗАКАЗ**\n\n"
                         f"От: @{call.from_user.username}\n"
                         f"Товар: {brand} ({flavor})\n"
                         f"Прайс: {total}zł\n"
                         f"Доставка: {delivery}")
            await bot.send_message(ADMIN, admin_msg)
        except: pass

    await call.message.edit_text("🚀 **Готово!**\nЗаявка улетела. Менеджер проверит BLIK и отпишет тебе в личку в течение пары минут.")
    await call.answer("Заказ в обработке!", show_alert=True)

@dp.callback_query(F.data == "back_to_cats")
async def back_to_cats(call: types.CallbackQuery):
    await call.message.edit_text("✨ **Каталог Cloude**\nВыбери раздел:", reply_markup=cats_kb(), parse_mode="Markdown")
    await call.answer()

@dp.callback_query(F.data == "exit")
async def exit_shop(call: types.CallbackQuery):
    await call.message.delete()
    await call.message.answer("Меню:", reply_markup=main_kb())
    await call.answer()

@dp.message(F.text == "📥 Мои заказы")
async def history(msg: types.Message):
    with sqlite3.connect('cloude_base.db') as db:
        rows = db.execute("SELECT item_name, flavor, total, date FROM orders WHERE user_id = ? ORDER BY date DESC", (msg.from_user.id,)).fetchall()
    if not rows: return await msg.answer("Пока еще ничего не заказывал.")
    res = "📜 **Твои покупки:**\n\n"
    for b, f, t, d in rows: res += f"📅 {d[:10]} | {t}zł | {b} - {f}\n"
    await msg.answer(res, parse_mode="Markdown")

@dp.message(F.text == "🤝 Поддержка")
async def support(msg: types.Message):
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="⭐️ Группа с отзывами", url=REVIEWS_URL))
    await msg.answer("По всем вопросам: @твой_ник\nРаботаем по Кракову 🚀", reply_markup=kb.as_markup())

@dp.message(F.text.startswith("!send"), F.from_user.id == ADMIN)
async def spam(msg: types.Message):
    t = msg.text.replace("!send", "").strip()
    with sqlite3.connect('cloude_base.db') as db:
        users = db.execute("SELECT user_id FROM users").fetchall()
    c = 0
    for (u_id,) in users:
        try:
            await bot.send_message(u_id, f"📢 **Cloude:**\n\n{t}", parse_mode="Markdown")
            c += 1
            await asyncio.sleep(0.05)
        except: pass
    await msg.answer(f"Доставлено: {c}")

async def run_bot():
    init_db()
    threading.Thread(target=run_server, daemon=True).start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(run_bot())