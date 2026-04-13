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

# --- Веб-заглушка для рендера ---
app = Flask('')
@app.route('/')
def main_page(): return "Cloude Bot: Active"

def start_web_server():
    app.run(host='0.0.0.0', port=8080)

# --- Конфиг ---
load_dotenv()
logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv('BOT_TOKEN')
ADMIN = os.getenv('ADMIN_ID')
# Переводим в int только если ID прилетел
if ADMIN:
    ADMIN = int(ADMIN)

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- Работа с БД (sqlite) ---
def setup_db():
    with sqlite3.connect('cloude_base.db') as db:
        cur = db.cursor()
        cur.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT)')
        cur.execute('CREATE TABLE IF NOT EXISTS cart (user_id INTEGER, item_name TEXT, price INTEGER)')
        cur.execute('CREATE TABLE IF NOT EXISTS orders (user_id INTEGER, order_content TEXT, total_price INTEGER, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
        db.commit()

# --- Кнопки ---
def get_main_menu():
    kb = ReplyKeyboardBuilder()
    kb.row(types.KeyboardButton(text="☁️ Витрина"), types.KeyboardButton(text="📥 Корзина"))
    kb.row(types.KeyboardButton(text="📜 История заказов"), types.KeyboardButton(text="🤝 Поддержка"))
    return kb.as_markup(resize_keyboard=True)

def get_cats_kb():
    kb = InlineKeyboardBuilder()
    kb.add(types.InlineKeyboardButton(text="🧂 Солевые", callback_data="cat_salt"))
    kb.add(types.InlineKeyboardButton(text="💨 Одноразки", callback_data="cat_disposable"))
    kb.row(types.InlineKeyboardButton(text="❌ Назад в меню", callback_data="exit_shop"))
    return kb.as_markup()

# --- Логика бота ---

@dp.message(CommandStart())
async def welcome(msg: types.Message):
    # Логиним юзера в базу при старте
    with sqlite3.connect('cloude_base.db') as db:
        db.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", 
                   (msg.from_user.id, msg.from_user.username))
    
    await msg.answer(
        f"Салют, {msg.from_user.first_name}! 👋\n\nЭто **Cloude**. "
        "Твой проводник в мире пара в Кракове. Глянь, что у нас есть:",
        reply_markup=get_main_menu(),
        parse_mode="Markdown"
    )

@dp.message(F.text == "☁️ Витрина")
async def show_catalog(msg: types.Message):
    await msg.answer("Минутку, открываю каталог...", reply_markup=types.ReplyKeyboardRemove())
    await msg.answer("🔥 **Каталог Cloude**\nВыбирай категорию:", reply_markup=get_cats_kb(), parse_mode="Markdown")

@dp.callback_query(F.data == "exit_shop")
async def exit_shop(call: types.CallbackQuery):
    await call.message.delete()
    await call.message.answer("Главное меню:", reply_markup=get_main_menu())
    await call.answer()

@dp.callback_query(F.data.startswith("cat_"))
async def items_list(call: types.CallbackQuery):
    cat = call.data.split("_")[1]
    kb = InlineKeyboardBuilder()
    
    # Список товаров (можно потом в БД вынести)
    if cat == "salt":
        data = [("Husky Double Ice", 45), ("Chilly Mans", 42), ("Jam Monster", 50)]
    else:
        data = [("Elf Bar 5000", 65), ("Lost Mary 5000", 70)]

    for name, price in data:
        kb.row(types.InlineKeyboardButton(text=f"{name} — {price}zł", callback_data=f"add_{name}_{price}"))
    
    kb.row(types.InlineKeyboardButton(text="⬅️ К категориям", callback_data="back_cats"))
    await call.message.edit_text("🛒 Кликни на позицию, чтобы закинуть в корзину:", reply_markup=kb.as_markup())
    await call.answer()

@dp.callback_query(F.data == "back_cats")
async def back_cats(call: types.CallbackQuery):
    await call.message.edit_text("🔥 **Каталог Cloude**\nВыбирай категорию:", reply_markup=get_cats_kb(), parse_mode="Markdown")
    await call.answer()

@dp.callback_query(F.data.startswith("add_"))
async def to_cart(call: types.CallbackQuery):
    _, name, price = call.data.split("_")
    with sqlite3.connect('cloude_base.db') as db:
        db.execute("INSERT INTO cart (user_id, item_name, price) VALUES (?, ?, ?)", 
                   (call.from_user.id, name, int(price)))
    await call.answer(f"➕ {name} в корзине!")

@dp.message(F.text == "📥 Корзина")
async def view_cart(msg: types.Message):
    with sqlite3.connect('cloude_base.db') as db:
        items = db.execute("SELECT item_name, price FROM cart WHERE user_id = ?", (msg.from_user.id,)).fetchall()

    if not items:
        return await msg.answer("В корзине пока пусто... Исправим? 😏")

    text = "🛒 **Твоя корзина:**\n\n"
    total = sum(i[1] for i in items)
    for n, p in items:
        text += f"▫️ {n} — {p}zł\n"
    text += f"\n**Итого к оплате: {total}zł**"

    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="🚀 Заказать", callback_data="confirm_order"))
    kb.row(types.InlineKeyboardButton(text="🗑 Очистить", callback_data="empty_cart"))
    await msg.answer(text, reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data == "confirm_order")
async def make_order(call: types.CallbackQuery):
    with sqlite3.connect('cloude_base.db') as db:
        items = db.execute("SELECT item_name, price FROM cart WHERE user_id = ?", (call.from_user.id,)).fetchall()
        
        if items:
            summary = ", ".join([i[0] for i in items])
            total = sum(i[1] for i in items)
            db.execute("INSERT INTO orders (user_id, order_content, total_price) VALUES (?, ?, ?)", 
                       (call.from_user.id, summary, total))
            db.execute("DELETE FROM cart WHERE user_id = ?", (call.from_user.id,))
            
            # Стук админу
            if ADMIN:
                try:
                    await bot.send_message(ADMIN, f"⚡️ **НОВЫЙ ЧЕК!**\n\nЮзер: {call.from_user.first_name} (@{call.from_user.username})\nЗаказ: {summary}\nПрайс: {total}zł")
                except: pass

            await call.message.edit_text(f"🚀 **Улетело в обработку!**\nСумма: {total}zł\nСкоро свяжемся с тобой.")
    await call.answer()

@dp.message(F.text == "📜 История заказов")
async def history(msg: types.Message):
    with sqlite3.connect('cloude_base.db') as db:
        rows = db.execute("SELECT order_content, total_price, date FROM orders WHERE user_id = ? ORDER BY date DESC", (msg.from_user.id,)).fetchall()

    if not rows:
        return await msg.answer("Тут пока нет записей о покупках.")

    res = "📜 **Твои прошлые заказы:**\n\n"
    for cont, pr, dt in rows:
        res += f"📅 {dt[:10]} | {pr}zł\n📦 {cont}\n\n"
    await msg.answer(res, parse_mode="Markdown")

@dp.callback_query(F.data == "empty_cart")
async def empty_cart(call: types.CallbackQuery):
    with sqlite3.connect('cloude_base.db') as db:
        db.execute("DELETE FROM cart WHERE user_id = ?", (call.from_user.id,))
    await call.message.edit_text("🗑 Корзина теперь пуста.")
    await call.answer()

@dp.message(F.text == "🤝 Поддержка")
async def help_me(msg: types.Message):
    await msg.answer("Есть вопросы или предложения? Пиши нам: @твой_ник\nДоставка по городу 💨")

# --- Рассылка для админа ---
@dp.message(F.text.startswith("!send"), F.from_user.id == ADMIN)
async def spam(msg: types.Message):
    text = msg.text.replace("!send", "").strip()
    with sqlite3.connect('cloude_base.db') as db:
        users = db.execute("SELECT user_id FROM users").fetchall()

    count = 0
    for (u_id,) in users:
        try:
            await bot.send_message(u_id, f"📣 **Cloude News:**\n\n{text}", parse_mode="Markdown")
            count += 1
            await asyncio.sleep(0.1)
        except: pass
    await msg.answer(f"Разослал {count} людям.")

# --- Запуск ---
async def start():
    setup_db()
    threading.Thread(target=start_web_server, daemon=True).start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(start())