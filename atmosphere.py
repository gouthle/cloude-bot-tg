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

# --- Настройки сервера ---
app = Flask('')
@app.route('/')
def home(): return "Cloude: Ready"

def run_server():
    app.run(host='0.0.0.0', port=8080)

# --- Конфиг ---
load_dotenv()
logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv('BOT_TOKEN')
ADMIN = os.getenv('ADMIN_ID')
if ADMIN: ADMIN = int(ADMIN)

# Данные для оплаты (можешь поменять тут)
PHONE_NUMBER = "+48 123 456 789" 

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- БД ---
def init_db():
    with sqlite3.connect('cloude_base.db') as db:
        db.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT)')
        db.execute('CREATE TABLE IF NOT EXISTS orders (user_id INTEGER, content TEXT, total INTEGER, delivery TEXT, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')

# --- Кнопки ---
def main_kb():
    kb = ReplyKeyboardBuilder()
    kb.row(types.KeyboardButton(text="☁️ Витрина"), types.KeyboardButton(text="📜 Мои заказы"))
    kb.row(types.KeyboardButton(text="🤝 Поддержка"))
    return kb.as_markup(resize_keyboard=True)

def cats_kb():
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="🧂 Жидкости", callback_data="cat_liq"))
    kb.row(types.InlineKeyboardButton(text="💨 Одноразки", callback_data="cat_disp"))
    kb.row(types.InlineKeyboardButton(text="❌ Закрыть", callback_data="exit"))
    return kb.as_markup()

# --- Хендлеры ---

@dp.message(CommandStart())
async def start(msg: types.Message):
    with sqlite3.connect('cloude_base.db') as db:
        db.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", 
                   (msg.from_user.id, msg.from_user.username))
    await msg.answer(f"Привет, {msg.from_user.first_name}! 👋\nВыбирай товар на витрине:", 
                     reply_markup=main_kb(), parse_mode="Markdown")

@dp.message(F.text == "☁️ Витрина")
async def open_shop(msg: types.Message):
    await msg.answer("Открываю витрину...", reply_markup=types.ReplyKeyboardRemove())
    await msg.answer("✨ **Витрина Cloude**\nВыбери категорию:", reply_markup=cats_kb(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("cat_"))
async def list_items(call: types.CallbackQuery):
    cat = call.data.split("_")[1]
    kb = InlineKeyboardBuilder()
    
    # Твой ассортимент
    if cat == "liq":
        items = [("Husky Double Ice", 45), ("ELFLIQ Salt", 45)]
    else:
        items = [("VOZOL 6000", 45), ("VOZOL 10000", 45)]

    for name, price in items:
        kb.row(types.InlineKeyboardButton(text=f"{name} — {price}zł", callback_data=f"sel_{name}_{price}"))
    
    kb.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back"))
    await call.message.edit_text("🛒 Выбери модель:", reply_markup=kb.as_markup())
    await call.answer()

# ВЫБОР ДОСТАВКИ
@dp.callback_query(F.data.startswith("sel_"))
async def select_delivery(call: types.CallbackQuery):
    _, name, price = call.data.split("_")
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="📦 Parcel (+14zł)", callback_data=f"pay_{name}_{int(price)+14}_InPost"))
    kb.row(types.InlineKeyboardButton(text="🤝 Самовывоз (Free)", callback_data=f"pay_{name}_{price}_Pickup"))
    kb.row(types.InlineKeyboardButton(text="⬅️ Отмена", callback_data="back"))
    
    await call.message.edit_text(f"📍 **Доставка для {name}:**\nВыбери способ получения:", reply_markup=kb.as_markup(), parse_mode="Markdown")
    await call.answer()

# ОПЛАТА BLIK
@dp.callback_query(F.data.startswith("pay_"))
async def payment(call: types.CallbackQuery):
    _, name, total, delivery = call.data.split("_")
    
    text = (f"💳 **Оплата заказа**\n\n"
            f"Товар: {name}\n"
            f"Доставка: {delivery}\n"
            f"**К оплате: {total}zł**\n\n"
            f"Переведи сумму по BLIK на номер:\n`{PHONE_NUMBER}`\n\n"
            f"После оплаты нажми кнопку ниже 👇")
    
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="✅ Я оплатил(а)", callback_data=f"done_{name}_{total}_{delivery}"))
    kb.row(types.InlineKeyboardButton(text="❌ Отмена", callback_data="back"))
    
    await call.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="Markdown")
    await call.answer()

# ПОДТВЕРЖДЕНИЕ
@dp.callback_query(F.data.startswith("done_"))
async def order_done(call: types.CallbackQuery):
    _, name, total, delivery = call.data.split("_")
    
    with sqlite3.connect('cloude_base.db') as db:
        db.execute("INSERT INTO orders (user_id, content, total, delivery) VALUES (?, ?, ?, ?)", 
                   (call.from_user.id, name, total, delivery))
    
    # Уведомление админу
    if ADMIN:
        try:
            admin_msg = (f"💰 **НОВЫЙ ЗАКАЗ (ОЖИДАЕТ ПРОВЕРКИ)**\n\n"
                         f"Юзер: @{call.from_user.username}\n"
                         f"Товар: {name}\n"
                         f"Сумма: {total}zł\n"
                         f"Тип: {delivery}")
            await bot.send_message(ADMIN, admin_msg)
        except: pass

    await call.message.edit_text("🚀 **Заявка отправлена!**\nМенеджер проверит оплату и свяжется с тобой в течение 10-15 минут.")
    await call.answer("Заказ оформлен!", show_alert=True)

@dp.callback_query(F.data == "back")
async def back(call: types.CallbackQuery):
    await call.message.edit_text("✨ **Витрина Cloude**\nВыбери категорию:", reply_markup=cats_kb(), parse_mode="Markdown")
    await call.answer()

@dp.callback_query(F.data == "exit")
async def exit_shop(call: types.CallbackQuery):
    await call.message.delete()
    await call.message.answer("Меню:", reply_markup=main_kb())
    await call.answer()

@dp.message(F.text == "📜 Мои заказы")
async def history(msg: types.Message):
    with sqlite3.connect('cloude_base.db') as db:
        rows = db.execute("SELECT content, total, date FROM orders WHERE user_id = ? ORDER BY date DESC", (msg.from_user.id,)).fetchall()
    if not rows: return await msg.answer("Заказов пока нет.")
    res = "📜 **Твоя история:**\n\n"
    for c, t, d in rows: res += f"📅 {d[:10]} | {t}zł | {c}\n"
    await msg.answer(res, parse_mode="Markdown")

@dp.message(F.text == "🤝 Поддержка")
async def support(msg: types.Message):
    await msg.answer("Есть вопросы? Пиши: @твой_ник\nОтправки InPost и самовывоз в Кракове.")

# Рассылка !send
@dp.message(F.text.startswith("!send"), F.from_user.id == ADMIN)
async def spam(msg: types.Message):
    t = msg.text.replace("!send", "").strip()
    with sqlite3.connect('cloude_base.db') as db:
        users = db.execute("SELECT user_id FROM users").fetchall()
    c = 0
    for (u_id,) in users:
        try:
            await bot.send_message(u_id, f"📣 **Cloude:**\n\n{t}", parse_mode="Markdown")
            c += 1
            await asyncio.sleep(0.1)
        except: pass
    await msg.answer(f"Отправлено: {c}")

async def run_bot():
    init_db()
    threading.Thread(target=run_server, daemon=True).start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(run_bot())