import asyncio
import os
import logging
import sqlite3
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv('BOT_TOKEN')
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- РАБОТА С БАЗОЙ ДАННЫХ ---
def init_db():
    conn = sqlite3.connect('cloude_base.db')
    cursor = conn.cursor()
    # Таблица корзины (временная)
    cursor.execute('''CREATE TABLE IF NOT EXISTS cart 
                      (user_id INTEGER, item_name TEXT, price INTEGER)''')
    # Таблица заказов (история)
    cursor.execute('''CREATE TABLE IF NOT EXISTS orders 
                      (user_id INTEGER, order_content TEXT, total_price INTEGER, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

init_db()

# --- КЛАВИАТУРЫ ---
def main_menu_kb():
    builder = ReplyKeyboardBuilder()
    builder.row(types.KeyboardButton(text="☁️ Витрина"), types.KeyboardButton(text="📥 Корзина"))
    builder.row(types.KeyboardButton(text="📜 История заказов"), types.KeyboardButton(text="🤝 Поддержка"))
    return builder.as_markup(resize_keyboard=True)

def categories_kb():
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🧂 Солевые", callback_data="cat_salt"))
    builder.row(types.InlineKeyboardButton(text="💨 Одноразки", callback_data="cat_disposable"))
    return builder.as_markup()

# --- ХЕНДЛЕРЫ ---
@dp.message(CommandStart())
async def start_command(message: types.Message):
    await message.answer(f"Привет, {message.from_user.first_name}! Ты в **Cloude**.🌬", reply_markup=main_menu_kb())

@dp.message(F.text == "☁️ Витрина")
async def shop_catalog(message: types.Message):
    await message.answer("✨ **Витрина Cloude**\nВыбери категорию:", reply_markup=categories_kb())

# Выбор товаров в категории
@dp.callback_query(F.data.startswith("cat_"))
async def show_items(callback: types.CallbackQuery):
    category = callback.data.split("_")[1]
    builder = InlineKeyboardBuilder()
    
    if category == "salt":
        items = [("Husky Double Ice", 45), ("Chilly Mans", 42)]
    else:
        items = [("Elf Bar 5000", 65), ("Lost Mary", 70)]

    for name, price in items:
        builder.row(types.InlineKeyboardButton(text=f"{name} — {price}zł", callback_data=f"buy_{name}_{price}"))
    
    builder.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_cats"))
    await callback.message.edit_text("Выбери товар для добавления в корзину:", reply_markup=builder.as_markup())

# Добавление в корзину
@dp.callback_query(F.data.startswith("buy_"))
async def add_to_cart(callback: types.CallbackQuery):
    _, name, price = callback.data.split("_")
    conn = sqlite3.connect('cloude_base.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO cart (user_id, item_name, price) VALUES (?, ?, ?)", (callback.from_user.id, name, int(price)))
    conn.commit()
    conn.close()
    await callback.answer(f"✅ {name} добавлен в корзину!")

# Работа с корзиной
@dp.message(F.text == "📥 Корзина")
async def show_cart(message: types.Message):
    conn = sqlite3.connect('cloude_base.db')
    cursor = conn.cursor()
    cursor.execute("SELECT item_name, price FROM cart WHERE user_id = ?", (message.from_user.id,))
    items = cursor.fetchall()
    conn.close()

    if not items:
        await message.answer("🛒 Твоя корзина пуста.")
        return

    res = "🛒 **Твоя корзина:**\n\n"
    total = 0
    for name, price in items:
        res += f"• {name} — {price}zł\n"
        total += price
    res += f"\n**Итого: {total}zł**"

    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="✅ Оформить заказ", callback_data="checkout"))
    builder.row(types.InlineKeyboardButton(text="🗑 Очистить", callback_data="clear_cart"))
    await message.answer(res, reply_markup=builder.as_markup(), parse_mode="Markdown")

# Оформление заказа (перенос в историю)
@dp.callback_query(F.data == "checkout")
async def checkout(callback: types.CallbackQuery):
    conn = sqlite3.connect('cloude_base.db')
    cursor = conn.cursor()
    cursor.execute("SELECT item_name, price FROM cart WHERE user_id = ?", (callback.from_user.id,))
    items = cursor.fetchall()
    
    if items:
        order_text = ", ".join([i[0] for i in items])
        total = sum([i[1] for i in items])
        cursor.execute("INSERT INTO orders (user_id, order_content, total_price) VALUES (?, ?, ?)", 
                       (callback.from_user.id, order_text, total))
        cursor.execute("DELETE FROM cart WHERE user_id = ?", (callback.from_user.id,))
        conn.commit()
        await callback.message.edit_text(f"🚀 **Заказ оформлен!**\nСостав: {order_text}\nСумма: {total}zł\nМенеджер свяжется с тобой.")
    conn.close()
    await callback.answer()

# История заказов
@dp.message(F.text == "📜 История заказов")
async def show_history(message: types.Message):
    conn = sqlite3.connect('cloude_base.db')
    cursor = conn.cursor()
    cursor.execute("SELECT order_content, total_price, date FROM orders WHERE user_id = ? ORDER BY date DESC", (message.from_user.id,))
    orders = cursor.fetchall()
    conn.close()

    if not orders:
        await message.answer("У тебя еще нет завершенных заказов.")
        return

    res = "📜 **Твоя история покупок:**\n\n"
    for content, total, date in orders:
        res += f"📅 {date[:10]} | {total}zł\n📦 {content}\n\n"
    await message.answer(res, parse_mode="Markdown")

@dp.callback_query(F.data == "clear_cart")
async def clear_cart(callback: types.CallbackQuery):
    conn = sqlite3.connect('cloude_base.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM cart WHERE user_id = ?", (callback.from_user.id,))
    conn.commit()
    conn.close()
    await callback.message.edit_text("🗑 Корзина очищена.")
    await callback.answer()

@dp.callback_query(F.data == "back_to_cats")
async def back_to_cats(callback: types.CallbackQuery):
    await callback.message.edit_text("✨ **Витрина Cloude**\nВыбери категорию:", reply_markup=categories_kb())
    await callback.answer()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())