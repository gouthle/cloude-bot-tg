import asyncio
import os
import logging
import sqlite3
import threading
from flask import Flask
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import BotCommand
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.utils.deep_linking import create_start_link
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv

# --- ЧАСТЬ 1: СЕРВЕР ДЛЯ ПОДДЕРЖАНИЯ ЖИЗНИ ---
app = Flask('')

@app.route('/')
def home():
    return "Cloude Status: Active and Running"

def run_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# --- ЧАСТЬ 2: НАСТРОЙКИ И ПЕРЕМЕННЫЕ ---
load_dotenv()
logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID_ENV = os.getenv('ADMIN_ID')
ADMIN = int(ADMIN_ID_ENV) if ADMIN_ID_ENV else None

PHONE_NUMBER = "+48 123 456 789"  # ЗАМЕНИ НА СВОЙ НОМЕР BLIK
REVIEWS_URL = "https://t.me/+cbqxYZH0tzE4MDUy"

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# --- ЧАСТЬ 4: АССОРТИМЕНТ ТОВАРОВ ---
STOCKS = {
    "VOZOL Salt": {
        "flavors": ["Strawberry Watermelon", "Kiwi Guava", "White Peach", "Berries"],
        "photo": "AgACAgIAAxkBAAICbmnlTR8eWQcAATCwLgAB4Qpan_dwJF4AAiIZaxugqSlLvokeaQm4iO8BAAMCAAN3AAM7BA",
        "price": 45
    },
    "ELFLIQ Salt": {
        "flavors": ["Grape Cherry", "Blueberry Sour Raspberry", "Blueberry Lemon", "Watermelon", "Pina Colada"],
        "photo": "AgACAgIAAxkBAAICfGnlUOyZ0JA7KfcuGPo4vncBgBhpAAIqGWsboKkpS0545fr-HtvFAQADAgADeAADOwQ",
        "price": 45
    }
}

BRAND_LIST = list(STOCKS.keys())

def brand_to_idx(brand_name: str) -> str:
    try:
        return str(BRAND_LIST.index(brand_name))
    except ValueError:
        return "0"

def idx_to_brand(idx: str) -> str:
    try:
        return BRAND_LIST[int(idx)]
    except (ValueError, IndexError):
        return BRAND_LIST[0]

# --- ЧАСТЬ 3: РАБОТА С БАЗОЙ ДАННЫХ ---
def get_stock(brand: str, flavor: str) -> int:
    conn = sqlite3.connect('cloude_base.db')
    row = conn.execute(
        "SELECT quantity FROM stock WHERE brand = ? AND flavor = ?", (brand, flavor)
    ).fetchone()
    conn.close()
    return row[0] if row else 0

def set_stock(brand: str, flavor: str, quantity: int):
    conn = sqlite3.connect('cloude_base.db')
    conn.execute(
        "INSERT OR REPLACE INTO stock (brand, flavor, quantity) VALUES (?, ?, ?)",
        (brand, flavor, quantity)
    )
    conn.commit()
    conn.close()

def decrement_stock(brand: str, flavor: str):
    conn = sqlite3.connect('cloude_base.db')
    conn.execute(
        "UPDATE stock SET quantity = MAX(0, quantity - 1) WHERE brand = ? AND flavor = ?",
        (brand, flavor)
    )
    conn.commit()
    conn.close()

def init_db():
    conn = sqlite3.connect('cloude_base.db')
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            referrer_id INTEGER
        )
    ''')
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
    cur.execute('''
        CREATE TABLE IF NOT EXISTS stock (
            brand TEXT,
            flavor TEXT,
            quantity INTEGER DEFAULT 0,
            PRIMARY KEY (brand, flavor)
        )
    ''')
    conn.commit()
    conn.close()
    conn = sqlite3.connect('cloude_base.db')
    for brand, data in STOCKS.items():
        for flavor in data["flavors"]:
            conn.execute(
                "INSERT OR IGNORE INTO stock (brand, flavor, quantity) VALUES (?, ?, 0)",
                (brand, flavor)
            )
    conn.commit()
    conn.close()

# --- ЧАСТЬ 5: КНОПКИ МЕНЮ ---
async def set_main_menu_button(bot: Bot):
    commands = [
        BotCommand(command='/start', description='Главное меню / Запуск'),
        BotCommand(command='/help', description='Помощь и поддержка'),
        BotCommand(command='/admin', description='Админ-панель (только для админа)'),
    ]
    await bot.set_my_commands(commands)

def get_main_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.row(types.KeyboardButton(text="☁️ Витрина"), types.KeyboardButton(text="📥 Мои заказы"))
    builder.row(types.KeyboardButton(text="💰 Бонусы"), types.KeyboardButton(text="⭐️ Отзывы"))
    builder.row(types.KeyboardButton(text="🤝 Поддержка"))
    return builder.as_markup(resize_keyboard=True)

# --- ЧАСТЬ 6: ХЕНДЛЕРЫ МЕНЮ ---

@dp.message(CommandStart())
async def start_handler(message: types.Message):
    start_command = message.text.split()
    referrer = start_command[1] if len(start_command) > 1 and start_command[1].isdigit() else None

    db = sqlite3.connect('cloude_base.db')
    db.execute(
        "INSERT OR IGNORE INTO users (user_id, username, referrer_id) VALUES (?, ?, ?)",
        (message.from_user.id, message.from_user.username, referrer)
    )
    db.commit()
    db.close()

    welcome_text = (
        f"Salute, <b>{message.from_user.first_name}</b>! 👋\n\n"
        "Ты попал в <b>Cloude Atmosphere</b>. Самое лучшее качество у нас!\n\n"
        "Пользуйся меню снизу, чтобы сделать заказ. Если возникнут вопросы — жми 'Поддержка'."
    )
    await message.answer(welcome_text, reply_markup=get_main_keyboard())


@dp.message(F.text == "☁️ Витрина")
async def catalog_handler(message: types.Message):
    keyboard = InlineKeyboardBuilder()
    for brand in BRAND_LIST:
        idx = brand_to_idx(brand)
        keyboard.row(types.InlineKeyboardButton(text=brand, callback_data=f"brn_{idx}"))
    await message.answer("✨ <b>Каталог продукции</b>\nВыбери бренд:", reply_markup=keyboard.as_markup())


@dp.message(F.text == "💰 Бонусы")
async def bonus_handler(message: types.Message):
    link = await create_start_link(bot, str(message.from_user.id), encode=True)
    await message.answer(
        f"🎁 <b>Твоя реферальная ссылка:</b>\n\n<code>{link}</code>\n\n"
        "Приглашай друзей и получай бонусы на свой баланс!"
    )


@dp.message(F.text == "⭐️ Отзывы")
async def reviews_handler(message: types.Message):
    keyboard = InlineKeyboardBuilder()
    keyboard.row(types.InlineKeyboardButton(text="📖 Перейти в канал", url=REVIEWS_URL))
    await message.answer("Честные отзывы наших покупателей здесь 👇", reply_markup=keyboard.as_markup())


@dp.message(F.text == "📥 Мои заказы")
async def my_orders_handler(message: types.Message):
    db = sqlite3.connect('cloude_base.db')
    rows = db.execute(
        "SELECT item_name, flavor, total, status FROM orders WHERE user_id = ? ORDER BY date DESC LIMIT 5",
        (message.from_user.id,)
    ).fetchall()
    db.close()

    if not rows:
        return await message.answer("У тебя пока нет заказов.")

    text = "📜 <b>Последние заказы:</b>\n\n"
    for item, flav, tot, stat in rows:
        text += f"▪️ {item} ({flav}) — {tot}zł\nСтатус: <b>{stat}</b>\n\n"
    await message.answer(text)


@dp.message(F.text == "🤝 Поддержка")
async def support_handler(message: types.Message):
    await message.answer("Связь с менеджером: @твой_ник\nПиши по любым вопросам! 🚀")


# --- ЧАСТЬ 7: АДМИН-ПАНЕЛЬ СКЛАДА ---

def get_admin_stock_keyboard(brand_idx: str):
    brand_name = idx_to_brand(brand_idx)
    brand_data = STOCKS.get(brand_name, {})
    keyboard = InlineKeyboardBuilder()

    for i, flavor in enumerate(brand_data.get("flavors", [])):
        qty = get_stock(brand_name, flavor)
        status = f"✅ {qty} шт." if qty > 0 else "❌ Sold Out"
        keyboard.row(
            types.InlineKeyboardButton(text=f"{flavor} — {status}", callback_data="noop")
        )
        keyboard.row(
            types.InlineKeyboardButton(text="➖1", callback_data=f"adm_m_{brand_idx}_{i}"),
            types.InlineKeyboardButton(text="➕1", callback_data=f"adm_p_{brand_idx}_{i}"),
            types.InlineKeyboardButton(text="➕5", callback_data=f"adm_p5_{brand_idx}_{i}"),
            types.InlineKeyboardButton(text="🔄 Сброс", callback_data=f"adm_r_{brand_idx}_{i}"),
        )

    keyboard.row(types.InlineKeyboardButton(text="⬅️ К брендам", callback_data="adm_brands"))
    return keyboard.as_markup()

def get_admin_brands_keyboard():
    keyboard = InlineKeyboardBuilder()
    for brand in BRAND_LIST:
        idx = brand_to_idx(brand)
        keyboard.row(types.InlineKeyboardButton(text=f"📦 {brand}", callback_data=f"adm_b_{idx}"))
    return keyboard.as_markup()

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN:
        return await message.answer("⛔️ Нет доступа.")
    await message.answer(
        "⚙️ <b>Админ-панель — Управление складом</b>\n\nВыбери бренд:",
        reply_markup=get_admin_brands_keyboard()
    )

@dp.callback_query(F.data == "adm_brands")
async def adm_brands(call: types.CallbackQuery):
    if call.from_user.id != ADMIN:
        return await call.answer("⛔️ Нет доступа.", show_alert=True)
    await call.message.edit_text(
        "⚙️ <b>Админ-панель — Управление складом</b>\n\nВыбери бренд:",
        reply_markup=get_admin_brands_keyboard()
    )

@dp.callback_query(F.data.startswith("adm_b_"))
async def adm_brand_stock(call: types.CallbackQuery):
    if call.from_user.id != ADMIN:
        return await call.answer("⛔️ Нет доступа.", show_alert=True)
    brand_idx = call.data.split("_")[2]
    brand_name = idx_to_brand(brand_idx)
    await call.message.edit_text(
        f"⚙️ <b>Склад — {brand_name}</b>\n\nУправляй остатками:",
        reply_markup=get_admin_stock_keyboard(brand_idx)
    )

@dp.callback_query(F.data == "noop")
async def noop_handler(call: types.CallbackQuery):
    await call.answer()

@dp.callback_query(F.data.startswith("adm_"))
async def adm_stock_action(call: types.CallbackQuery):
    if call.from_user.id != ADMIN:
        return await call.answer("⛔️ Нет доступа.", show_alert=True)

    parts = call.data.split("_")
    action = parts[1]
    brand_idx = parts[2]
    flavor_idx = int(parts[3])

    brand_name = idx_to_brand(brand_idx)
    flavors = STOCKS.get(brand_name, {}).get("flavors", [])

    if flavor_idx >= len(flavors):
        return await call.answer("Ошибка: вкус не найден")

    flavor = flavors[flavor_idx]
    current = get_stock(brand_name, flavor)

    if action == "m":
        new_qty = max(0, current - 1)
    elif action == "p":
        new_qty = current + 1
    elif action == "p5":
        new_qty = current + 5
    elif action == "r":
        new_qty = 0
    else:
        return await call.answer("Неизвестное действие")

    set_stock(brand_name, flavor, new_qty)

    status = f"✅ {new_qty} шт." if new_qty > 0 else "❌ Sold Out"
    await call.answer(f"{flavor}: {status}")
    await call.message.edit_reply_markup(reply_markup=get_admin_stock_keyboard(brand_idx))


# --- ЧАСТЬ 8: ВИТРИНА — INLINE CALLBACKS ---

@dp.callback_query(F.data.startswith("brn_"))
async def flavors_callback(call: types.CallbackQuery):
    brand_idx = call.data.split("_", 1)[1]
    brand_name = idx_to_brand(brand_idx)
    brand_data = STOCKS.get(brand_name)
    keyboard = InlineKeyboardBuilder()

    if brand_data:
        for i, flavor in enumerate(brand_data["flavors"]):
            price = brand_data["price"]
            qty = get_stock(brand_name, flavor)
            if qty > 0:
                keyboard.row(types.InlineKeyboardButton(
                    text=f"{flavor} ({qty} шт.)",
                    callback_data=f"sl_{brand_idx}_{i}_{price}"
                ))
            else:
                keyboard.row(types.InlineKeyboardButton(
                    text=f"❌ {flavor} — Sold Out",
                    callback_data="soldout"
                ))

    keyboard.row(types.InlineKeyboardButton(text="⬅️ Назад к каталогу", callback_data="back_to_cats"))
    caption = f"🍒 <b>Вкусы {brand_name}:</b>\nВыбирай свой вариант:"

    if brand_data and brand_data["photo"]:
        await call.message.delete()
        await call.bot.send_photo(
            call.from_user.id,
            brand_data["photo"],
            caption=caption,
            reply_markup=keyboard.as_markup()
        )
    else:
        await call.message.edit_text(caption, reply_markup=keyboard.as_markup())


@dp.callback_query(F.data == "soldout")
async def soldout_handler(call: types.CallbackQuery):
    await call.answer("😔 Этого вкуса нет в наличии. Выбери другой!", show_alert=True)


@dp.callback_query(F.data.startswith("sl_"))
async def delivery_callback(call: types.CallbackQuery):
    parts = call.data.split("_")
    brand_idx, flavor_idx, price = parts[1], parts[2], parts[3]

    brand_name = idx_to_brand(brand_idx)
    flavors = STOCKS.get(brand_name, {}).get("flavors", [])

    try:
        flavor = flavors[int(flavor_idx)]
    except (IndexError, ValueError):
        return await call.answer("Ошибка: вкус не найден")

    if get_stock(brand_name, flavor) <= 0:
        await call.answer("😔 Только что разобрали! Выбери другой вкус.", show_alert=True)
        return

    price_int = int(price)
    keyboard = InlineKeyboardBuilder()
    keyboard.row(types.InlineKeyboardButton(
        text="📦 InPost (+14zł)",
        callback_data=f"pay_i_{brand_idx}_{flavor_idx}_{price_int + 14}"
    ))
    keyboard.row(types.InlineKeyboardButton(
        text="🤝 Inpost GRATIS (От 5 штук)",
        callback_data=f"pay_g_{brand_idx}_{flavor_idx}_{price_int}"
    ))
    keyboard.row(types.InlineKeyboardButton(
        text="⬅️ Назад к вкусам",
        callback_data=f"brn_{brand_idx}"
    ))

    text = f"📍 <b>Оформление:</b> {brand_name} — {flavor}\n\nВыбери способ получения:"

    # FIX: удаляем фото-сообщение и отправляем текстовое
    await call.message.delete()
    await call.bot.send_message(call.from_user.id, text, reply_markup=keyboard.as_markup())


@dp.callback_query(F.data.startswith("pay_"))
async def payment_callback(call: types.CallbackQuery):
    parts = call.data.split("_")
    delivery_code = parts[1]
    brand_idx, flavor_idx, total = parts[2], parts[3], parts[4]

    brand_name = idx_to_brand(brand_idx)
    flavors = STOCKS.get(brand_name, {}).get("flavors", [])

    try:
        flavor = flavors[int(flavor_idx)]
    except (IndexError, ValueError):
        return await call.answer("Ошибка: вкус не найден")

    delivery_type = "InPost" if delivery_code == "i" else "GRATIS"

    pay_text = (
        f"💳 <b>Оплата заказа</b>\n\n"
        f"Товар: {brand_name} ({flavor})\n"
        f"Способ: {delivery_type}\n"
        f"<b>Сумма к оплате: {total}zł</b>\n\n"
        f"Переведи ровную сумму по BLIK на номер:\n<code>{PHONE_NUMBER}</code>\n\n"
        "После совершения платежа обязательно нажми кнопку ниже!"
    )

    keyboard = InlineKeyboardBuilder()
    keyboard.row(types.InlineKeyboardButton(
        text="✅ Я оплатил(а)",
        callback_data=f"fin_{delivery_code}_{brand_idx}_{flavor_idx}_{total}"
    ))
    keyboard.row(types.InlineKeyboardButton(text="❌ Отменить", callback_data="back_to_cats"))

    await call.message.edit_text(pay_text, reply_markup=keyboard.as_markup())


@dp.callback_query(F.data.startswith("fin_"))
async def finish_callback(call: types.CallbackQuery):
    parts = call.data.split("_")
    delivery_code = parts[1]
    brand_idx, flavor_idx, total = parts[2], parts[3], parts[4]

    brand_name = idx_to_brand(brand_idx)
    flavors = STOCKS.get(brand_name, {}).get("flavors", [])

    try:
        flavor = flavors[int(flavor_idx)]
    except (IndexError, ValueError):
        return await call.answer("Ошибка: вкус не найден")

    delivery = "InPost" if delivery_code == "i" else "GRATIS"

    db = sqlite3.connect('cloude_base.db')
    cur = db.cursor()
    cur.execute(
        "INSERT INTO orders (user_id, item_name, flavor, total, delivery, info, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (call.from_user.id, brand_name, flavor, total, delivery, "Ожидаем данные InPost", "WAIT_DATA")
    )
    order_id = cur.lastrowid
    db.commit()
    db.close()

    user_id = call.from_user.id
    username = call.from_user.username or "без ника"

    if delivery == "InPost":
        await call.message.edit_text(
            "📝 <b>Важно!</b>\nПришли следующим сообщением данные для InPost:\n"
            "1. Твои ФИО\n"
            "2. Номер телефона\n"
            "3. Код пачкомата (напр. KRA01M)"
        )
    else:
        if ADMIN:
            kb = InlineKeyboardBuilder()
            kb.row(
                types.InlineKeyboardButton(text="✅ Оплата пришла", callback_data=f"confirm_{order_id}_{user_id}"),
                types.InlineKeyboardButton(text="❌ Не пришла", callback_data=f"reject_{order_id}_{user_id}")
            )
            await bot.send_message(
                ADMIN,
                f"⚡️ <b>НОВЫЙ ЗАКАЗ (GRATIS)</b>\n"
                f"👤 @{username} (<code>{user_id}</code>)\n"
                f"📦 {brand_name} — {flavor}\n"
                f"💵 Сумма: <b>{total}zł</b>\n"
                f"🚚 Доставка: {delivery}\n"
                f"🆔 Заказ №{order_id}",
                reply_markup=kb.as_markup()
            )
        await call.message.edit_text(
            "🚀 <b>Заказ принят!</b> Менеджер свяжется с тобой для передачи товара."
        )


@dp.callback_query(F.data == "back_to_cats")
async def back_to_cats(call: types.CallbackQuery):
    keyboard = InlineKeyboardBuilder()
    for brand in BRAND_LIST:
        idx = brand_to_idx(brand)
        keyboard.row(types.InlineKeyboardButton(text=brand, callback_data=f"brn_{idx}"))

    text = "✨ <b>Каталог продукции</b>\nВыбери бренд:"

    # FIX: удаляем фото-сообщение и отправляем текстовое
    await call.message.delete()
    await call.bot.send_message(call.from_user.id, text, reply_markup=keyboard.as_markup())


# --- ЧАСТЬ 9: ОБРАБОТКА ТЕКСТА И ФОТО ---

@dp.message(F.photo)
async def photo_id_helper(message: types.Message):
    if ADMIN and message.from_user.id == ADMIN:
        await message.answer(f"ID фото для кода:\n<code>{message.photo[-1].file_id}</code>")


@dp.message(F.text, ~F.text.startswith("/"))
async def text_handler(message: types.Message):
    db = sqlite3.connect('cloude_base.db')
    cursor = db.cursor()
    cursor.execute(
        "SELECT order_id, item_name, flavor, total FROM orders WHERE user_id = ? AND status = 'WAIT_DATA' ORDER BY date DESC LIMIT 1",
        (message.from_user.id,)
    )
    order = cursor.fetchone()

    if order:
        order_id, item, flavor, total = order
        cursor.execute(
            "UPDATE orders SET info = ?, status = 'Ожидает подтверждения' WHERE order_id = ?",
            (message.text, order_id)
        )
        db.commit()
        db.close()

        await message.answer(
            "✅ <b>Данные получены!</b>\nМенеджер проверит оплату и отправит твой заказ. Спасибо, что выбрал Cloude!"
        )

        if ADMIN:
            user_id = message.from_user.id
            username = message.from_user.username or "без ника"
            kb = InlineKeyboardBuilder()
            kb.row(
                types.InlineKeyboardButton(text="✅ Оплата пришла", callback_data=f"confirm_{order_id}_{user_id}"),
                types.InlineKeyboardButton(text="❌ Не пришла", callback_data=f"reject_{order_id}_{user_id}")
            )
            await bot.send_message(
                ADMIN,
                f"💰 <b>НОВЫЙ ЗАКАЗ (InPost)</b>\n"
                f"👤 @{username} (<code>{user_id}</code>)\n"
                f"📦 {item} — {flavor}\n"
                f"💵 Сумма: <b>{total}zł</b>\n"
                f"🚚 Доставка: InPost\n"
                f"📋 Данные: {message.text}\n"
                f"🆔 Заказ №{order_id}",
                reply_markup=kb.as_markup()
            )
    else:
        db.close()
        await message.answer(
            "Используй кнопки меню для заказа. Если есть вопросы — пиши в поддержку."
        )


@dp.callback_query(F.data.startswith("confirm_"))
async def confirm_order(call: types.CallbackQuery):
    if call.from_user.id != ADMIN:
        return await call.answer("⛔️ Нет доступа.", show_alert=True)

    parts = call.data.split("_")
    order_id, user_id = int(parts[1]), int(parts[2])

    db = sqlite3.connect('cloude_base.db')
    row = db.execute(
        "SELECT item_name, flavor, status FROM orders WHERE order_id = ?", (order_id,)
    ).fetchone()

    if not row:
        db.close()
        return await call.answer("Заказ не найден", show_alert=True)

    item_name, flavor, status = row

    if status == "Подтверждён":
        db.close()
        return await call.answer("Заказ уже подтверждён!", show_alert=True)

    db.execute(
        "UPDATE orders SET status = 'Подтверждён' WHERE order_id = ?", (order_id,)
    )
    db.commit()
    db.close()

    decrement_stock(item_name, flavor)

    await call.message.edit_text(
        call.message.text + "\n\n✅ <b>Подтверждено!</b> Склад обновлён."
    )
    await bot.send_message(
        user_id,
        "✅ <b>Оплата подтверждена!</b>\nТвой заказ принят в обработку. Скоро получишь трек-номер или свяжемся по деталям. 🚀"
    )


@dp.callback_query(F.data.startswith("reject_"))
async def reject_order(call: types.CallbackQuery):
    if call.from_user.id != ADMIN:
        return await call.answer("⛔️ Нет доступа.", show_alert=True)

    parts = call.data.split("_")
    order_id, user_id = int(parts[1]), int(parts[2])

    db = sqlite3.connect('cloude_base.db')
    row = db.execute(
        "SELECT status FROM orders WHERE order_id = ?", (order_id,)
    ).fetchone()

    if not row:
        db.close()
        return await call.answer("Заказ не найден", show_alert=True)

    if row[0] == "Отклонён":
        db.close()
        return await call.answer("Заказ уже отклонён!", show_alert=True)

    db.execute(
        "UPDATE orders SET status = 'Отклонён' WHERE order_id = ?", (order_id,)
    )
    db.commit()
    db.close()

    await call.message.edit_text(
        call.message.text + "\n\n❌ <b>Отклонено.</b> Склад не тронут."
    )
    await bot.send_message(
        user_id,
        "❌ <b>Оплата не найдена.</b>\nПроверь, правильно ли ты перевёл сумму. Если есть вопросы — напиши в поддержку 🤝"
    )


# --- ЗАПУСК ---
async def main():
    init_db()
    await set_main_menu_button(bot)
    threading.Thread(target=run_server, daemon=True).start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())