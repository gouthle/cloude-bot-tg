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

# --- Server for Render ---
app = Flask('')
@app.route('/')
def home(): return "Cloude status: OK"

def run_server():
    app.run(host='0.0.0.0', port=8080)

# --- Настройки ---
load_dotenv()
logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv('BOT_TOKEN')
ADMIN = os.getenv('ADMIN_ID')
if ADMIN:
    ADMIN = int(ADMIN)

DELIVERY_COST = 14 # Цена InPost

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- База данных ---
def init_db():
    with sqlite3.connect('cloude_base.db') as db:
        cur = db.cursor()
        cur.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT)')
        cur.execute('CREATE TABLE IF NOT EXISTS cart (user_id INTEGER, item_name TEXT, price INTEGER)')
        cur.execute('CREATE TABLE IF NOT EXISTS orders (user_id INTEGER, content TEXT, total INTEGER, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
        db.commit()

# --- Кнопки ---
def main_kb():
    kb = ReplyKeyboardBuilder()
    kb.row(types.KeyboardButton(text="☁️ Витрина"), types.KeyboardButton(text="📥 Корзина"))
    kb.row(types.KeyboardButton(text="📜 История"), types.KeyboardButton(text="🤝 Поддержка"))
    return kb.as_markup(resize_keyboard=True)

def cats_kb():
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="🧂 Жидкости (Husky/Elfliq)", callback_data="cat_liq"))
    kb.row(types.InlineKeyboardButton(text="💨 Одноразки (Vozol)", callback_data="cat_disp"))
    kb.row(types.InlineKeyboardButton(text="❌ Закрыть", callback_data="exit"))
    return kb.as_markup()

# --- Логика ---

@dp.message(CommandStart())
async def start(msg: types.Message):
    with sqlite3.connect('cloude_base.db') as db:
        db.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", 
                   (msg.from_user.id, msg.from_user.username))
    await msg.answer(f"Привет, {msg.from_user.first_name}! 👋\nДобро пожаловать в **Cloude**.\nВыбирай товар в меню:", 
                     reply_markup=main_kb(), parse_mode="Markdown")

@dp.message(F.text == "☁️ Витрина")
async def open_shop(msg: types.Message):
    await msg.answer("Открываю витрину...", reply_markup=types.ReplyKeyboardRemove())
    await msg.answer("✨ **Витрина Cloude**\nВсе позиции по **45zł** (+14 InPost)", reply_markup=cats_kb(), parse_mode="Markdown")

@dp.callback_query(F.data == "exit")
async def exit_shop(call: types.CallbackQuery):
    await call.message.delete()
    await call.message.answer("Главное меню:", reply_markup=main_kb())
    await call.answer()

@dp.callback_query(F.data.startswith("cat_"))
async def list_items(call: types.CallbackQuery):
    cat = call.data.split("_")[1]
    kb = InlineKeyboardBuilder()
    
    # Твой ассортимент по 45zł
    if cat == "liq":
        items = [("Husky Double Ice", 45), ("ELFLIQ Salt", 45)]
    else:
        items = [("VOZOL 6000", 45), ("VOZOL 10000", 45)]

    for name, price in items:
        kb.row(types.InlineKeyboardButton(text=f"{name} — {price}zł", callback_data=f"add_{name}_{price}"))
    
    kb.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back"))
    await call.message.edit_text("🛒 Что добавим в корзину?", reply_markup=kb.as_markup())
    await call.answer()

@dp.callback_query(F.data == "back")
async def back(call: types.CallbackQuery):
    await call.message.edit_text("✨ **Витрина Cloude**\nВыбери категорию:", reply_markup=cats_kb(), parse_mode="Markdown")
    await call.answer()

@dp.callback_query(F.data.startswith("add_"))
async def add_item(call: types.CallbackQuery):
    _, name, price = call.data.split("_")
    with sqlite3.connect('cloude_base.db') as db:
        db.execute("INSERT INTO cart (user_id, item_name, price) VALUES (?, ?, ?)", (call.from_user.id, name, int(price)))
    await call.answer(f"➕ {name} в корзине!")

@dp.message(F.text == "📥 Корзина")
async def cart(msg: types.Message):
    with sqlite3.connect('cloude_base.db') as db:
        items = db.execute("SELECT item_name, price FROM cart WHERE user_id = ?", (msg.from_user.id,)).fetchall()

    if not items:
        return await msg.answer("В корзине пусто. Пора это исправить! 🌬️")

    subtotal = sum(i[1] for i in items)
    total = subtotal + DELIVERY_COST
    
    text = "🛒 **Твоя корзина:**\n\n"
    for n, p in items:
        text += f"▫️ {n} — {p}zł\n"
    text += f"\n📦 Доставка InPost: {DELIVERY_COST}zł"
    text += f"\n\n**Итого: {total}zł**"

    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="🚀 Оформить заказ", callback_data="order"))
    kb.row(types.InlineKeyboardButton(text="🗑 Очистить", callback_data="clear"))
    await msg.answer(text, reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data == "order")
async def order(call: types.CallbackQuery):
    with sqlite3.connect('cloude_base.db') as db:
        items = db.execute("SELECT item_name, price FROM cart WHERE user_id = ?", (call.from_user.id,)).fetchall()
        
        if items:
            names = ", ".join([i[0] for i in items])
            total = sum(i[1] for i in items) + DELIVERY_COST
            db.execute("INSERT INTO orders (user_id, content, total) VALUES (?, ?, ?)", (call.from_user.id, names, total))
            db.execute("DELETE FROM cart WHERE user_id = ?", (call.from_user.id,))
            
            if ADMIN:
                try:
                    await bot.send_message(ADMIN, f"🔥 **ЗАКАЗ!**\n\nЮзер: @{call.from_user.username}\nСостав: {names}\nСумма: {total}zł")
                except: pass

            await call.message.edit_text(f"🚀 **Принято!**\nИтого с доставкой: {total}zł\nМенеджер напишет для данных InPost.")
    await call.answer()

@dp.message(F.text == "📜 История")
async def history(msg: types.Message):
    with sqlite3.connect('cloude_base.db') as db:
        rows = db.execute("SELECT content, total, date FROM orders WHERE user_id = ? ORDER BY date DESC", (msg.from_user.id,)).fetchall()
    if not rows: return await msg.answer("Заказов пока не было.")
    res = "📜 **Твои заказы:**\n\n"
    for c, t, d in rows: res += f"📅 {d[:10]} | {t}zł\n📦 {c}\n\n"
    await msg.answer(res, parse_mode="Markdown")

@dp.callback_query(F.data == "clear")
async def clear(call: types.CallbackQuery):
    with sqlite3.connect('cloude_base.db') as db:
        db.execute("DELETE FROM cart WHERE user_id = ?", (call.from_user.id,))
    await call.message.edit_text("🗑 Корзина пуста.")
    await call.answer()

@dp.message(F.text == "🤝 Поддержка")
async def help(msg: types.Message):
    await msg.answer("Вопросы? Пиши: @твой_ник\nInPost отправки каждый день! 📦")

# --- Рассылка ---
@dp.message(F.text.startswith("!send"), F.from_user.id == ADMIN)
async def spam(msg: types.Message):
    t = msg.text.replace("!send", "").strip()
    with sqlite3.connect('cloude_base.db') as db:
        users = db.execute("SELECT user_id FROM users").fetchall()
    c = 0
    for (u_id,) in users:
        try:
            await bot.send_message(u_id, f"📣 **Cloude:**\n\n{t}", parse_mode="Markdown")
            count += 1
            await asyncio.sleep(0.1)
        except: pass
    await msg.answer(f"Отправлено: {c}")

async def start_bot():
    init_db()
    threading.Thread(target=run_server, daemon=True).start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(start_bot())