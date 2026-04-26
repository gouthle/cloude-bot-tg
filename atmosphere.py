import asyncio
import os
import json
import logging
import threading
import psycopg2
import psycopg2.extras
from flask import Flask
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import BotCommand, LinkPreviewOptions
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv
try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False

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

ADMIN2_ID_ENV = os.getenv('ADMIN2_ID')
ADMIN2 = int(ADMIN2_ID_ENV) if ADMIN2_ID_ENV else None

ADMINS = [a for a in [ADMIN, ADMIN2] if a is not None]

def is_admin(user_id: int) -> bool:
    return user_id in ADMINS

REVIEWS_CHANNEL_ID_ENV = os.getenv('REVIEWS_CHANNEL_ID')
REVIEWS_CHANNEL_ID = int(REVIEWS_CHANNEL_ID_ENV) if REVIEWS_CHANNEL_ID_ENV else None

DATABASE_URL = os.getenv('DATABASE_URL')

PHONE_NUMBER = "536169149"
REVIEWS_URL = "https://t.me/+cbqxYZH0tzE4MDUy"

SHEETS_ID = os.getenv('SHEETS_ID')
GOOGLE_CREDS_JSON = os.getenv('GOOGLE_CREDS_JSON')

ORDER_GROUP_ID_ENV = os.getenv('ORDER_GROUP_ID')
ORDER_GROUP_ID = int(ORDER_GROUP_ID_ENV) if ORDER_GROUP_ID_ENV else None

def get_sheet():
    if not GSPREAD_AVAILABLE or not SHEETS_ID or not GOOGLE_CREDS_JSON:
        return None
    try:
        creds_dict = json.loads(GOOGLE_CREDS_JSON)
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SHEETS_ID).sheet1
        return sheet
    except Exception as e:
        logging.error(f"Google Sheets error: {e}")
        return None

def init_sheet_headers():
    sheet = get_sheet()
    if not sheet: return
    try:
        if not sheet.get_all_values():
            sheet.append_row([
                "Дата и время", "Заказ №", "Юзернейм", 
                "Товар", "Доставка", "Сумма заказа (zł)", "Общая касса (zł)"
            ])
    except Exception as e:
        logging.error(f"Sheet header init error: {e}")

async def append_order_to_sheet(order_id, username, item_name, flavor, qty, total, delivery, total_revenue):
    def _write():
        sheet = get_sheet()
        if not sheet: return
        from datetime import datetime
        date_str = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        try:
            sheet.append_row([
                date_str, order_id, f"@{username}", 
                f"{item_name} — {flavor} (x{qty})", delivery, total, total_revenue
            ])
        except Exception as e:
            logging.error(f"Sheet append error: {e}")
    await asyncio.get_event_loop().run_in_executor(None, _write)

LOW_STOCK_THRESHOLD = 2

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

async def send_group_report(order_id, username, item, flavor, qty, total, delivery, total_revenue):
    if not ORDER_GROUP_ID:
        logging.error("❌ ORDER_GROUP_ID не найден в переменных среды Render")
        return

    from datetime import datetime
    date_str = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    report_text = (
        f"💰 <b>ЗАКАЗ №{order_id} ОПЛАЧЕН</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⏰ Время: {date_str}\n"
        f"👤 Клиент: @{username}\n"
        f"📦 Заказ: {item} — {flavor} (<b>{qty} шт.</b>)\n"
        f"🚚 Доставка: {delivery}\n"
        f"💵 Сумма заказа: <b>{total} zł</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>Общая касса: {total_revenue} zł</b>"
    )
    try:
        await bot.send_message(ORDER_GROUP_ID, report_text)
    except Exception as e:
        logging.error(f"Error sending group report: {e}")


# --- ЧАСТЬ 3: РАБОТА С БАЗОЙ ДАННЫХ И КОРЗИНОЙ ---
def get_conn():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

# Логика Корзины
def get_cart(user_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT brand, flavor, quantity, price FROM cart WHERE user_id = %s", (user_id,))
    rows = cur.fetchall()
    conn.close()
    return rows

def add_to_cart(user_id: int, brand: str, flavor: str, qty: int, price: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT quantity FROM cart WHERE user_id = %s AND brand = %s AND flavor = %s", (user_id, brand, flavor))
    row = cur.fetchone()
    if row:
        cur.execute("UPDATE cart SET quantity = quantity + %s WHERE user_id = %s AND brand = %s AND flavor = %s", (qty, user_id, brand, flavor))
    else:
        cur.execute("INSERT INTO cart (user_id, brand, flavor, quantity, price) VALUES (%s, %s, %s, %s, %s)", (user_id, brand, flavor, qty, price))
    conn.commit()
    conn.close()

def clear_cart(user_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM cart WHERE user_id = %s", (user_id,))
    conn.commit()
    conn.close()

def get_stock(brand: str, flavor: str) -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT quantity FROM stock WHERE brand = %s AND flavor = %s", (brand, flavor))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else 0

def set_stock(brand: str, flavor: str, quantity: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO stock (brand, flavor, quantity) VALUES (%s, %s, %s) "
        "ON CONFLICT (brand, flavor) DO UPDATE SET quantity = EXCLUDED.quantity",
        (brand, flavor, quantity)
    )
    conn.commit()
    conn.close()

def decrement_stock(brand: str, flavor: str, amount: int = 1) -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE stock SET quantity = GREATEST(0, quantity - %s) WHERE brand = %s AND flavor = %s",
        (amount, brand, flavor)
    )
    conn.commit()
    cur.execute("SELECT quantity FROM stock WHERE brand = %s AND flavor = %s", (brand, flavor))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else 0

def get_all_user_ids() -> list:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users")
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]

def collect_exists(user_id: int) -> bool:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM pending_collect WHERE user_id = %s", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row is not None

def get_collect(user_id: int) -> dict | None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT order_id, step, name, phone, email, paczkomat FROM pending_collect WHERE user_id = %s",
        (user_id,)
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {"order_id": row[0], "step": row[1], "name": row[2],
            "phone": row[3], "email": row[4], "paczkomat": row[5]}

def set_collect(user_id: int, data: dict):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO pending_collect (user_id, order_id, step, name, phone, email, paczkomat) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (user_id) DO UPDATE SET order_id=EXCLUDED.order_id, step=EXCLUDED.step, "
        "name=EXCLUDED.name, phone=EXCLUDED.phone, email=EXCLUDED.email, paczkomat=EXCLUDED.paczkomat",
        (user_id, data.get("order_id"), data.get("step", "name"),
         data.get("name", ""), data.get("phone", ""), data.get("email", ""), data.get("paczkomat", ""))
    )
    conn.commit()
    conn.close()

def delete_collect(user_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM pending_collect WHERE user_id = %s", (user_id,))
    conn.commit()
    conn.close()

def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS cart (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            brand TEXT,
            flavor TEXT,
            quantity INTEGER,
            price INTEGER
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id SERIAL PRIMARY KEY,
            user_id BIGINT,
            item_name TEXT,
            flavor TEXT,
            quantity INTEGER DEFAULT 1,
            total INTEGER,
            delivery TEXT,
            info TEXT,
            status TEXT DEFAULT 'Ожидает оплаты',
            track_number TEXT DEFAULT NULL,
            photo_id TEXT DEFAULT NULL,
            cart_data TEXT DEFAULT '[]',
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    try:
        cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS quantity INTEGER DEFAULT 1")
        cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS cart_data TEXT DEFAULT '[]'")
    except Exception:
        pass

    cur.execute("""
        CREATE TABLE IF NOT EXISTS stock (
            brand TEXT,
            flavor TEXT,
            quantity INTEGER DEFAULT 0,
            PRIMARY KEY (brand, flavor)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS pending_collect (
            user_id BIGINT PRIMARY KEY,
            order_id INTEGER,
            step TEXT,
            name TEXT DEFAULT '',
            phone TEXT DEFAULT '',
            email TEXT DEFAULT '',
            paczkomat TEXT DEFAULT ''
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            review_id SERIAL PRIMARY KEY,
            user_id BIGINT,
            username TEXT,
            order_id INTEGER,
            item_name TEXT,
            flavor TEXT,
            rating INTEGER,
            strength INTEGER DEFAULT NULL,
            taste INTEGER DEFAULT NULL,
            vapor INTEGER DEFAULT NULL,
            device TEXT DEFAULT NULL,
            text TEXT DEFAULT NULL,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    for col, coltype in [("strength", "INTEGER"), ("taste", "INTEGER"), ("vapor", "INTEGER"), ("device", "TEXT")]:
        try:
            cur.execute(f"ALTER TABLE reviews ADD COLUMN IF NOT EXISTS {col} {coltype} DEFAULT NULL")
        except Exception:
            pass

    conn.commit()

    for brand, data in STOCKS.items():
        for flavor in data["flavors"]:
            cur.execute(
                "INSERT INTO stock (brand, flavor, quantity) VALUES (%s, %s, 0) "
                "ON CONFLICT (brand, flavor) DO NOTHING",
                (brand, flavor)
            )
    conn.commit()
    conn.close()

# --- ЧАСТЬ 4: АССОРТИМЕНТ ТОВАРОВ ---
STOCKS = {
    "VOZOL Salt": {
        "flavors": ["Strawberry Watermelon", "Kiwi Passion Fruit Guava", "Berry", "Berry Peach"],
        "photo": "AgACAgIAAxkBAAICbmnlTR8eWQcAATCwLgAB4Qpan_dwJF4AAiIZaxugqSlLvokeaQm4iO8BAAMCAAN3AAM7BA",
        "price": 45
    },
    "ELFLIQ Salt": {
        "flavors": ["Blackberry Lemon", "Blueberry Sour Raspberry", "Blueberry Lemon", "Watermelon", "Pina Colada"],
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
    builder.row(types.KeyboardButton(text="☁️ Витрина"), types.KeyboardButton(text="🛒 Корзина"))
    builder.row(types.KeyboardButton(text="📥 Мои заказы"), types.KeyboardButton(text="⭐️ Отзывы"))
    builder.row(types.KeyboardButton(text="🤝 Поддержка"))
    return builder.as_markup(resize_keyboard=True)

BROADCAST_PENDING = set()
TRACK_PENDING = {}
PAYMENT_PENDING = {}
REVIEW_PENDING = {}

# --- ЧАСТЬ 6: ХЕНДЛЕРЫ МЕНЮ ---

@dp.message(CommandStart())
async def start_handler(message: types.Message):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (user_id, username) VALUES (%s, %s) "
        "ON CONFLICT (user_id) DO NOTHING",
        (message.from_user.id, message.from_user.username)
    )
    conn.commit()
    conn.close()

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


@dp.message(F.text == "⭐️ Отзывы")
async def reviews_handler(message: types.Message):
    keyboard = InlineKeyboardBuilder()
    keyboard.row(types.InlineKeyboardButton(text="📖 Перейти в канал", url=REVIEWS_URL))
    await message.answer("Честные отзывы наших покупателей здесь 👇", reply_markup=keyboard.as_markup())


@dp.message(F.text == "📥 Мои заказы")
async def my_orders_handler(message: types.Message):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT item_name, flavor, quantity, total, status, track_number FROM orders "
        "WHERE user_id = %s ORDER BY date DESC LIMIT 5",
        (message.from_user.id,)
    )
    rows = cur.fetchall()
    conn.close()

    if not rows:
        return await message.answer("У тебя пока нет заказов.")

    text = "📜 <b>Последние заказы:</b>\n\n"
    for item, flav, qty, tot, stat, track in rows:
        text += f"▪️ {item} ({flav}) x{qty} шт. — {tot}zł\nСтатус: <b>{stat}</b>"
        if track:
            text += f"\n📦 Трек: <a href='https://inpost.pl/sledzenie-przesylek?number={track}'>{track}</a>"
        text += "\n\n"
    await message.answer(text, link_preview_options=LinkPreviewOptions(is_disabled=True))


@dp.message(F.text == "🤝 Поддержка")
async def support_handler(message: types.Message):
    await message.answer("Связь с менеджером: @Alinagdmo\nПиши по любым вопросам! 🚀")


# --- ЧАСТЬ 7: АДМИН-ПАНЕЛЬ СКЛАДА И СТАТИСТИКА ---

def get_main_admin_keyboard():
    keyboard = InlineKeyboardBuilder()
    keyboard.row(types.InlineKeyboardButton(text="📦 Управление складом", callback_data="admin_stock_main"))
    keyboard.row(types.InlineKeyboardButton(text="📊 Статистика магазина", callback_data="admin_stats"))
    keyboard.row(types.InlineKeyboardButton(text="📢 Рассылка пользователям", callback_data="adm_broadcast"))
    return keyboard.as_markup()

def get_admin_brands_keyboard():
    keyboard = InlineKeyboardBuilder()
    for brand in BRAND_LIST:
        idx = brand_to_idx(brand)
        keyboard.row(types.InlineKeyboardButton(text=f"📦 {brand}", callback_data=f"adm_b_{idx}"))
    keyboard.row(types.InlineKeyboardButton(text="⬅️ В главное меню", callback_data="admin_main"))
    return keyboard.as_markup()

def get_admin_stock_keyboard(brand_idx: str):
    brand_name = idx_to_brand(brand_idx)
    brand_data = STOCKS.get(brand_name, {})
    keyboard = InlineKeyboardBuilder()

    for i, flavor in enumerate(brand_data.get("flavors", [])):
        qty = get_stock(brand_name, flavor)
        status = f"✅ {qty} шт." if qty > 0 else "❌ Sold Out"
        keyboard.row(types.InlineKeyboardButton(text=f"{flavor} — {status}", callback_data="noop"))
        keyboard.row(
            types.InlineKeyboardButton(text="➖" + "1", callback_data=f"adm_m_{brand_idx}_{i}"),
            types.InlineKeyboardButton(text="➕" + "1", callback_data=f"adm_p_{brand_idx}_{i}"),
            types.InlineKeyboardButton(text="➕" + "5", callback_data=f"adm_p5_{brand_idx}_{i}"),
            types.InlineKeyboardButton(text="🔄 Сброс", callback_data=f"adm_r_{brand_idx}_{i}"),
        )

    keyboard.row(types.InlineKeyboardButton(text="⬅️ К брендам", callback_data="admin_stock_main"))
    return keyboard.as_markup()

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔️ Нет доступа.")
    await message.answer("⚙️ <b>Главная Админ-панель</b>\n\nЧто будем делать?", reply_markup=get_main_admin_keyboard())

@dp.callback_query(F.data == "admin_main")
async def admin_main_menu(call: types.CallbackQuery):
    if not is_admin(call.from_user.id): return
    await call.message.edit_text("⚙️ <b>Главная Админ-панель</b>\n\nЧто будем делать?", reply_markup=get_main_admin_keyboard())

@dp.callback_query(F.data == "admin_stock_main")
async def adm_brands(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer("⛔️ Нет доступа.", show_alert=True)
    await call.message.edit_text("⚙️ <b>Склад магазина</b>\n\nВыбери бренд для управления остатками:", reply_markup=get_admin_brands_keyboard())

@dp.callback_query(F.data == "admin_stats")
async def admin_statistics(call: types.CallbackQuery):
    if not is_admin(call.from_user.id): return
    
    conn = get_conn()
    cur = conn.cursor()
    
    cur.execute("SELECT COUNT(*) FROM users")
    users_count = cur.fetchone()[0]
    
    cur.execute("SELECT SUM(total), COUNT(*) FROM orders WHERE status IN ('Подтверждён', 'Доставлен', 'В пути')")
    sales_data = cur.fetchone()
    total_revenue = sales_data[0] or 0
    total_orders = sales_data[1] or 0
    
    cur.execute("""
        SELECT item_name, flavor, SUM(quantity) as sold 
        FROM orders 
        WHERE status IN ('Подтверждён', 'Доставлен', 'В пути') 
        GROUP BY item_name, flavor 
        ORDER BY sold DESC LIMIT 3
    """)
    top_flavors = cur.fetchall()
    conn.close()
    
    text = f"📊 <b>Статистика Cloude Atmosphere:</b>\n\n"
    text += f"👥 Всего клиентов в боте: <b>{users_count}</b>\n"
    text += f"🛍 Успешных заказов: <b>{total_orders}</b>\n"
    text += f"💰 Общая выручка: <b>{total_revenue} zł</b>\n\n"
    
    text += f"🏆 <b>Топ-3 продаж:</b>\n"
    if top_flavors:
        for t in top_flavors:
            text += f"▪️ {t[0]} ({t[1]}) — {t[2]} шт.\n"
    else:
        text += "Пока нет подтвержденных продаж.\n"
        
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_main"))
    await call.message.edit_text(text, reply_markup=kb.as_markup())


@dp.callback_query(F.data == "adm_broadcast")
async def adm_broadcast_start(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer("⛔️ Нет доступа.", show_alert=True)
    BROADCAST_PENDING.add(call.from_user.id)
    await call.message.edit_text(
        "📢 <b>Рассылка</b>\n\nОтправь следующим сообщением текст рассылки.\n"
        "Поддерживается HTML-разметка: <b>жирный</b>, <i>курсив</i>, <code>код</code>.\n\n"
        "Для отмены напиши /admin"
    )

@dp.callback_query(F.data.startswith("adm_b_"))
async def adm_brand_stock(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
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
    if not is_admin(call.from_user.id):
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


# --- ЧАСТЬ 8: ВИТРИНА И КОРЗИНА — INLINE CALLBACKS ---

@dp.callback_query(F.data.startswith("brn_"))
async def flavors_callback(call: types.CallbackQuery):
    brand_idx = call.data.split("_", 1)[1]
    brand_name = idx_to_brand(brand_idx)
    brand_data = STOCKS.get(brand_name)
    keyboard = InlineKeyboardBuilder()

    if brand_data:
        for i, flavor in enumerate(brand_data["flavors"]):
            qty = get_stock(brand_name, flavor)
            if qty > 0:
                keyboard.row(types.InlineKeyboardButton(
                    text=f"{flavor} ({qty} шт.)",
                    callback_data=f"sl_{brand_idx}_{i}"
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
        await call.bot.send_photo(call.from_user.id, brand_data["photo"], caption=caption, reply_markup=keyboard.as_markup())
    else:
        await call.message.edit_text(caption, reply_markup=keyboard.as_markup())


@dp.callback_query(F.data == "soldout")
async def soldout_handler(call: types.CallbackQuery):
    await call.answer("😔 Этого вкуса нет в наличии. Выбери другой!", show_alert=True)


@dp.callback_query(F.data.startswith("sl_"))
async def quantity_callback(call: types.CallbackQuery):
    parts = call.data.split("_")
    brand_idx, flavor_idx = parts[1], parts[2]
    
    brand_name = idx_to_brand(brand_idx)
    brand_data = STOCKS.get(brand_name)
    flavors = brand_data.get("flavors", [])

    try:
        flavor = flavors[int(flavor_idx)]
    except (IndexError, ValueError):
        return await call.answer("Ошибка: вкус не найден")

    stock = get_stock(brand_name, flavor)
    if stock <= 0:
        return await call.answer("Только что разобрали!", show_alert=True)

    price = brand_data["price"]
    max_qty = min(stock, 10) 

    keyboard = InlineKeyboardBuilder()
    row1 = []
    for q in range(1, min(6, max_qty + 1)):
        row1.append(types.InlineKeyboardButton(text=f"{q} шт.", callback_data=f"addcart_{brand_idx}_{flavor_idx}_{q}"))
    keyboard.row(*row1)

    if max_qty > 5:
        row2 = []
        for q in range(6, max_qty + 1):
            row2.append(types.InlineKeyboardButton(text=f"{q} шт.", callback_data=f"addcart_{brand_idx}_{flavor_idx}_{q}"))
        keyboard.row(*row2)

    keyboard.row(types.InlineKeyboardButton(text="⬅️ Назад к вкусам", callback_data=f"brn_{brand_idx}"))

    text = (
        f"📍 <b>Выбран вкус:</b> {brand_name} — {flavor}\n"
        f"💸 Цена за 1 шт: {price}zł\n"
        f"📦 В наличии: {stock} шт.\n\n"
        f"👇 <b>Сколько штук берем?</b>\n\n"
        f"<i>🎁 Внимание: при заказе от 5 штук — доставка InPost по Польше БЕСПЛАТНО!</i>"
    )

    await call.message.delete()
    await call.bot.send_message(call.from_user.id, text, reply_markup=keyboard.as_markup())


# Добавление в корзину
@dp.callback_query(F.data.startswith("addcart_"))
async def add_to_cart_callback(call: types.CallbackQuery):
    parts = call.data.split("_")
    brand_idx, flavor_idx, qty = parts[1], parts[2], int(parts[3])
    brand_name = idx_to_brand(brand_idx)
    flavor = STOCKS[brand_name]["flavors"][int(flavor_idx)]
    price = STOCKS[brand_name]["price"]

    add_to_cart(call.from_user.id, brand_name, flavor, qty, price)

    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="🛒 Перейти в корзину", callback_data="show_cart"))
    kb.row(types.InlineKeyboardButton(text="⬅️ Продолжить покупки", callback_data="back_to_cats"))

    await call.message.edit_text(f"✅ Успешно добавлено в корзину:\n<b>{brand_name} — {flavor} ({qty} шт.)</b>\n\nЧто делаем дальше?", reply_markup=kb.as_markup())


# Отображение корзины
@dp.message(F.text == "🛒 Корзина")
async def show_cart_msg(message: types.Message):
    await handle_show_cart(message, message.from_user.id)

@dp.callback_query(F.data == "show_cart")
async def show_cart_cb(call: types.CallbackQuery):
    await handle_show_cart(call.message, call.from_user.id)

async def handle_show_cart(message: types.Message, user_id: int):
    cart = get_cart(user_id)
    if not cart:
        text = "🛒 <b>Твоя корзина пуста.</b>\nЗагляни в витрину!"
        kb = InlineKeyboardBuilder()
        kb.row(types.InlineKeyboardButton(text="☁️ В витрину", callback_data="back_to_cats"))
        if isinstance(message, types.Message) and message.text == "🛒 Корзина":
            await message.answer(text, reply_markup=kb.as_markup())
        else:
            await message.edit_text(text, reply_markup=kb.as_markup())
        return

    text = "🛒 <b>Твоя корзина:</b>\n\n"
    total_sum = 0
    total_qty = 0
    for i, (brand, flavor, qty, price) in enumerate(cart, 1):
        item_sum = qty * price
        total_sum += item_sum
        total_qty += qty
        text += f"{i}. {brand} — {flavor}\n   {qty} шт. x {price}zł = <b>{item_sum}zł</b>\n"

    text += f"\n📦 <b>Всего товаров:</b> {total_qty} шт.\n"
    text += f"💰 <b>Сумма:</b> {total_sum}zł\n"
    if total_qty >= 5:
        text += "<i>🎁 Доставка InPost (Польша) будет бесплатной!</i>\n"

    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="✅ Оформить заказ", callback_data=f"cart_checkout_{total_sum}_{total_qty}"))
    kb.row(types.InlineKeyboardButton(text="🗑 Очистить корзину", callback_data="cart_clear"))
    kb.row(types.InlineKeyboardButton(text="⬅️ Продолжить покупки", callback_data="back_to_cats"))

    if isinstance(message, types.Message) and message.text == "🛒 Корзина":
        await message.answer(text, reply_markup=kb.as_markup())
    else:
        await message.edit_text(text, reply_markup=kb.as_markup())


@dp.callback_query(F.data == "cart_clear")
async def clear_cart_cb(call: types.CallbackQuery):
    clear_cart(call.from_user.id)
    await call.answer("Корзина очищена 🗑", show_alert=True)
    await handle_show_cart(call.message, call.from_user.id)


@dp.callback_query(F.data.startswith("cart_checkout_"))
async def cart_checkout(call: types.CallbackQuery):
    parts = call.data.split("_")
    total_sum, total_qty = int(parts[2]), int(parts[3])

    inpost_pl_price = 0 if total_qty >= 5 else 14
    inpost_eu_price = 25 

    keyboard = InlineKeyboardBuilder()

    pl_text = "📦 InPost (Польша) - БЕСПЛАТНО" if inpost_pl_price == 0 else f"📦 InPost (Польша) +{inpost_pl_price}zł"
    eu_text = f"🌍 InPost EU (Европа) +{inpost_eu_price}zł"

    keyboard.row(types.InlineKeyboardButton(text=pl_text, callback_data=f"pay_pl_cart_{total_qty}_{total_sum}"))
    keyboard.row(types.InlineKeyboardButton(text=eu_text, callback_data=f"pay_eu_cart_{total_qty}_{total_sum}"))

    keyboard.row(types.InlineKeyboardButton(text="⬅️ Вернуться в корзину", callback_data="show_cart"))

    text = (f"📍 <b>Оформление заказа</b> (Всего: {total_qty} шт.)\n"
            f"💰 Сумма за товары: {total_sum}zł\n\n"
            f"Выбери способ доставки:")

    await call.message.edit_text(text, reply_markup=keyboard.as_markup())


@dp.callback_query(F.data.startswith("pay_"))
async def payment_callback(call: types.CallbackQuery):
    parts = call.data.split("_")
    d_code = parts[1]
    qty, base_price = int(parts[3]), int(parts[4])

    if d_code == 'pl':
        delivery_price = 0 if qty >= 5 else 14
        delivery_name = "InPost (Польша)"
    else:
        delivery_price = 25
        delivery_name = "InPost EU"

    final_total = base_price + delivery_price

    pay_text = (
        f"💳 <b>Оплата заказа</b>\n\n"
        f"Товаров: <b>{qty} шт.</b>\n"
        f"Способ: {delivery_name}\n"
        f"<b>Сумма к оплате: {final_total}zł</b>\n\n"
        f"Переведи ровную сумму по BLIK на номер:\n<code>{PHONE_NUMBER}</code>\n\n"
        "📸 После оплаты пришли <b>скриншот чека</b> следующим сообщением.\n"
        "Или нажми кнопку ниже если не можешь отправить фото."
    )

    keyboard = InlineKeyboardBuilder()
    keyboard.row(types.InlineKeyboardButton(
        text="✅ Оплатил(а), фото нет",
        callback_data=f"fin_{d_code}_cart_{qty}_{final_total}"
    ))
    keyboard.row(types.InlineKeyboardButton(text="❌ Отменить", callback_data="show_cart"))

    PAYMENT_PENDING[call.from_user.id] = {
        "d_code": d_code, "qty": qty, "total": final_total
    }
    await call.message.edit_text(pay_text, reply_markup=keyboard.as_markup())


@dp.callback_query(F.data.startswith("fin_"))
async def finish_callback(call: types.CallbackQuery):
    parts = call.data.split("_")
    delivery_code = parts[1]
    qty, total = int(parts[3]), int(parts[4])

    PAYMENT_PENDING.pop(call.from_user.id, None)
    delivery_name = "InPost (Польша)" if delivery_code == 'pl' else "InPost EU"

    await _create_cart_order(
        bot=call.bot, user_id=call.from_user.id,
        username=call.from_user.username or "без ника",
        qty=qty, total=total,
        delivery=delivery_name,
        photo_id=None,
        message=call.message, is_callback=True
    )


def _build_admin_order_kb(order_id, user_id):
    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(text="✅ Оплата пришла", callback_data=f"confirm_{order_id}_{user_id}"),
        types.InlineKeyboardButton(text="❌ Не пришла", callback_data=f"reject_{order_id}_{user_id}")
    )
    kb.row(types.InlineKeyboardButton(text="🚛 Отправить трек", callback_data=f"track_{order_id}_{user_id}"))
    kb.row(types.InlineKeyboardButton(text="📦 Доставлено", callback_data=f"delivered_{order_id}_{user_id}"))
    return kb.as_markup()


async def _create_cart_order(bot, user_id, username, qty, total, delivery, photo_id, message, is_callback=False):
    cart = get_cart(user_id)
    if not cart:
        if is_callback: await message.edit_text("Корзина пуста.")
        else: await bot.send_message(user_id, "Корзина пуста.")
        return

    # Собираем данные корзины в JSON для базы и в строку для Гугл Таблиц
    cart_json_data = json.dumps([{"b": b, "f": f, "q": q} for b, f, q, p in cart])
    flavor_str = ", ".join([f"{b} {f} (x{q})" for b, f, q, p in cart])
    brand_name = "Сборный заказ"

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO orders (user_id, item_name, flavor, quantity, total, delivery, info, status, photo_id, cart_data) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING order_id",
        (user_id, brand_name, flavor_str, qty, total, delivery, "", "Ожидает данные доставки", photo_id, cart_json_data)
    )
    order_id = cur.fetchone()[0]
    conn.commit()
    conn.close()

    clear_cart(user_id)

    set_collect(user_id, {"step": "name", "order_id": order_id,
                           "name": "", "phone": "", "email": "", "paczkomat": ""})
    text = f"📝 <b>Данные для доставки ({delivery})</b>\n\nШаг 1/4 — Напиши своё <b>полное имя и фамилию</b>:"
    
    if is_callback:
        await message.edit_text(text)
    else:
        await bot.send_message(user_id, text)


@dp.callback_query(F.data == "back_to_cats")
async def back_to_cats(call: types.CallbackQuery):
    keyboard = InlineKeyboardBuilder()
    for brand in BRAND_LIST:
        idx = brand_to_idx(brand)
        keyboard.row(types.InlineKeyboardButton(text=brand, callback_data=f"brn_{idx}"))
    await call.message.delete()
    await call.bot.send_message(call.from_user.id, "✨ <b>Каталог продукции</b>\nВыбери бренд:", reply_markup=keyboard.as_markup())


# --- ЧАСТЬ 9: ОБРАБОТКА ТЕКСТА И ФОТО ---

@dp.message(Command("reset_kassa"))
async def reset_kassa_command(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE orders SET status = 'Тестовый' WHERE status = 'Подтверждён'")
    conn.commit()
    conn.close()
    await message.answer("✅ Касса успешно обнулена! Все прошлые заказы переведены в статус 'Тестовый'.")

@dp.message(F.photo)
async def photo_handler(message: types.Message):
    if ADMIN and is_admin(message.from_user.id) and message.from_user.id not in PAYMENT_PENDING:
        await message.answer(f"ID фото для кода:\n<code>{message.photo[-1].file_id}</code>")
        return

    if message.from_user.id in PAYMENT_PENDING:
        pending = PAYMENT_PENDING.pop(message.from_user.id)
        delivery_name = "InPost (Польша)" if pending["d_code"] == 'pl' else "InPost EU"

        await message.answer("✅ Скриншот получен! Сейчас заполним данные для доставки.")
        await _create_cart_order(
            bot=bot, user_id=message.from_user.id,
            username=message.from_user.username or "без ника",
            qty=pending["qty"], total=pending["total"],
            delivery=delivery_name,
            photo_id=message.photo[-1].file_id,
            message=message, is_callback=False
        )


@dp.message(F.text, ~F.text.startswith("/"))
async def text_handler(message: types.Message):
    user_id = message.from_user.id

    if is_admin(user_id) and user_id in BROADCAST_PENDING:
        BROADCAST_PENDING.discard(user_id)
        all_users = get_all_user_ids()
        sent, failed = 0, 0
        for uid in all_users:
            try:
                await bot.send_message(uid, f"📢 <b>Сообщение от Cloude Atmosphere:</b>\n\n{message.text}")
                sent += 1
            except Exception:
                failed += 1
        await message.answer(f"✅ Рассылка завершена!\nОтправлено: {sent}\nОшибок: {failed}")
        return

    if is_admin(user_id) and user_id in TRACK_PENDING:
        order_id, buyer_id = TRACK_PENDING.pop(user_id)
        track = message.text.strip()
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("UPDATE orders SET track_number = %s, status = 'В пути' WHERE order_id = %s", (track, order_id))
        conn.commit()
        conn.close()
        await message.answer(f"✅ Трек-номер <code>{track}</code> сохранён для заказа №{order_id}.")
        try:
            await bot.send_message(buyer_id,
                f"📦 <b>Твой заказ отправлен!</b>\n\nТрек-номер: <code>{track}</code>\n"
                f"Отследить посылку InPost: <a href='https://inpost.pl/sledzenie-przesylek?number={track}'>Нажми сюда</a> 🚀",
                link_preview_options=LinkPreviewOptions(is_disabled=True))
        except Exception:
            await message.answer("⚠️ Не удалось уведомить пользователя.")
        return

    if user_id in REVIEW_PENDING and REVIEW_PENDING[user_id].get("step") == "device":
        REVIEW_PENDING[user_id]["device"] = message.text.strip()
        REVIEW_PENDING[user_id]["step"] = "text"
        rating = REVIEW_PENDING[user_id]["rating"]
        order_id = REVIEW_PENDING[user_id]["order_id"]
        stars = "⭐" * rating
        kb = InlineKeyboardBuilder()
        kb.row(types.InlineKeyboardButton(text="➡️ Пропустить комментарий",
                                           callback_data=f"revnotext_{order_id}_{rating}"))
        await message.answer(
            f"Ты поставил {stars}\n\n💬 Хочешь добавить комментарий? Напиши его.\n"
            "Или нажми кнопку, чтобы пропустить.",
            reply_markup=kb.as_markup()
        )
        return

    if user_id in REVIEW_PENDING and REVIEW_PENDING[user_id].get("step") == "text":
        pending = REVIEW_PENDING.pop(user_id)
        await _save_review(
            user_id=user_id, username=pending["username"],
            order_id=pending["order_id"], item_name=pending["item_name"],
            flavor=pending["flavor"], rating=pending["rating"], text=message.text.strip(),
            strength=pending.get("strength"), taste=pending.get("taste"),
            vapor=pending.get("vapor"), device=pending.get("device")
        )
        await message.answer("💬 Спасибо за отзыв! Твоё мнение очень важно для нас ☁️",
                             reply_markup=get_main_keyboard())
        return

    if collect_exists(user_id):
        collect = get_collect(user_id)
        step = collect["step"]

        if step == "name":
            collect["name"] = message.text.strip()
            collect["step"] = "phone"
            set_collect(user_id, collect)
            await message.answer("📞 Шаг 2/4 — Напиши свой <b>номер телефона</b>:")

        elif step == "phone":
            collect["phone"] = message.text.strip()
            collect["step"] = "email"
            set_collect(user_id, collect)
            await message.answer("📧 Шаг 3/4 — Напиши свой <b>email</b>:")

        elif step == "email":
            collect["email"] = message.text.strip()
            collect["step"] = "paczkomat"
            set_collect(user_id, collect)
            await message.answer("📦 Шаг 4/4 — Напиши <b>код пачкомата</b> (или полный адрес для InPost EU):")

        elif step == "paczkomat":
            collect["paczkomat"] = message.text.strip()
            delete_collect(user_id)

            order_id = collect["order_id"]
            info_text = (
                f"Имя: {collect['name']}\n"
                f"Телефон: {collect['phone']}\n"
                f"Email: {collect['email']}\n"
                f"Пачкомат/Адрес: {collect['paczkomat']}"
            )

            conn = get_conn()
            cur = conn.cursor()
            cur.execute("SELECT item_name, flavor, quantity, total, photo_id, delivery FROM orders WHERE order_id = %s", (order_id,))
            row = cur.fetchone()
            cur.execute("UPDATE orders SET info = %s, status = 'Ожидает подтверждения' WHERE order_id = %s",
                        (info_text, order_id))
            conn.commit()
            conn.close()

            await message.answer(
                "✅ <b>Все данные получены!</b>\n"
                "Менеджер проверит оплату и отправит твой заказ. Спасибо, что выбрал Cloude! ☁️"
            )

            if ADMINS and row:
                item, flavor, qty, total, saved_photo, delivery = row
                username = message.from_user.username or "без ника"
                admin_text = (
                    f"💰 <b>НОВЫЙ ЗАКАЗ</b>\n"
                    f"👤 @{username} (<code>{user_id}</code>)\n"
                    f"📦 {item}\n🔖 {flavor}\n"
                    f"💵 Сумма: <b>{total}zł</b>\n"
                    f"🚚 Доставка: {delivery}\n\n"
                    f"📋 <b>Данные доставки:</b>\n{info_text}\n\n"
                    f"🆔 Заказ №{order_id}"
                )
                if not saved_photo:
                    admin_text += "\n📸 Скриншот: не прислан"
                for adm in ADMINS:
                    try:
                        if saved_photo:
                            await bot.send_photo(adm, saved_photo, caption=admin_text,
                                                 reply_markup=_build_admin_order_kb(order_id, user_id))
                        else:
                            await bot.send_message(adm, admin_text,
                                                   reply_markup=_build_admin_order_kb(order_id, user_id))
                    except Exception:
                        pass
        return

    await message.answer("Используй кнопки меню для заказа. Если есть вопросы — пиши в поддержку.")


# --- ЧАСТЬ 10: ПОДТВЕРЖДЕНИЕ / ОТКЛОНЕНИЕ / ТРЕК ---

@dp.callback_query(F.data.startswith("confirm_"))
async def confirm_order(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer("⛔️ Нет доступа.", show_alert=True)
    
    parts = call.data.split("_")
    order_id, user_id = int(parts[1]), int(parts[2])

    conn = get_conn()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT o.item_name, o.flavor, o.quantity, o.total, o.delivery, o.status, o.cart_data, u.username 
        FROM orders o 
        LEFT JOIN users u ON o.user_id = u.user_id 
        WHERE o.order_id = %s
    """, (order_id,))
    row = cur.fetchone()
    
    if not row:
        conn.close()
        return await call.answer("Заказ не найден", show_alert=True)
    
    item_name, flavor, qty, total, delivery, status, cart_data_json, username = row
    username_str = username if username else str(user_id)
    
    if status == "Подтверждён":
        conn.close()
        return await call.answer("Заказ уже подтверждён!", show_alert=True)

    cur.execute("UPDATE orders SET status = 'Подтверждён' WHERE order_id = %s", (order_id,))
    
    cur.execute("SELECT SUM(total) FROM orders WHERE status = 'Подтверждён'")
    total_revenue = cur.fetchone()[0] or 0
    
    conn.commit()
    conn.close()

    if cart_data_json and cart_data_json != '[]':
        try:
            items = json.loads(cart_data_json)
            for item in items:
                new_qty = decrement_stock(item['b'], item['f'], amount=item['q'])
                if new_qty <= LOW_STOCK_THRESHOLD:
                    for adm in ADMINS:
                        try: await bot.send_message(adm, f"⚠️ <b>Товар заканчивается!</b>\n📦 {item['b']} — {item['f']}\nОстаток: <b>{new_qty} шт.</b>")
                        except Exception: pass
        except Exception:
            pass
    else:
        new_qty = decrement_stock(item_name, flavor, amount=qty)
        if new_qty <= LOW_STOCK_THRESHOLD:
            for adm in ADMINS:
                try: await bot.send_message(adm, f"⚠️ <b>Товар заканчивается!</b>\n📦 {item_name} — {flavor}\nОстаток: <b>{new_qty} шт.</b>")
                except Exception: pass
    
    await call.message.edit_text(call.message.text + "\n\n✅ <b>Подтверждено!</b>")
    await bot.send_message(user_id, "✅ <b>Оплата подтверждена!</b>\nТвой заказ принят в обработку. Скоро получишь трек-номер. 🚀")

    await append_order_to_sheet(order_id, username_str, item_name, flavor, qty, total, delivery, total_revenue)
    await send_group_report(order_id, username_str, item_name, flavor, qty, total, delivery, total_revenue)


@dp.callback_query(F.data.startswith("reject_"))
async def reject_order(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer("⛔️ Нет доступа.", show_alert=True)
    parts = call.data.split("_")
    order_id, user_id = int(parts[1]), int(parts[2])

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT status FROM orders WHERE order_id = %s", (order_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return await call.answer("Заказ не найден", show_alert=True)
    if row[0] == "Отклонён":
        conn.close()
        return await call.answer("Заказ уже отклонён!", show_alert=True)
    cur.execute("UPDATE orders SET status = 'Отклонён' WHERE order_id = %s", (order_id,))
    conn.commit()
    conn.close()

    await call.message.edit_text(call.message.text + "\n\n❌ <b>Отклонено.</b>")
    await bot.send_message(user_id,
        "❌ <b>Оплата не найдена.</b>\nПроверь перевод. Вопросы — в поддержку 🤝")


@dp.callback_query(F.data.startswith("track_"))
async def send_track_number(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer("⛔️ Нет доступа.", show_alert=True)
    parts = call.data.split("_")
    order_id, user_id = int(parts[1]), int(parts[2])
    TRACK_PENDING[call.from_user.id] = (order_id, user_id)
    await call.answer("Отправь трек-номер следующим сообщением.", show_alert=True)


# --- ЧАСТЬ 11: СИСТЕМА ОТЗЫВОВ ---

@dp.callback_query(F.data.startswith("delivered_"))
async def order_delivered(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer("⛔️ Нет доступа.", show_alert=True)
    parts = call.data.split("_")
    order_id, user_id = int(parts[1]), int(parts[2])

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT item_name, flavor, status FROM orders WHERE order_id = %s", (order_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return await call.answer("Заказ не найден", show_alert=True)
    item_name, flavor, status = row
    if status == "Доставлен":
        conn.close()
        return await call.answer("Заказ уже отмечен как доставленный!", show_alert=True)
    cur.execute("UPDATE orders SET status = 'Доставлен' WHERE order_id = %s", (order_id,))
    conn.commit()
    conn.close()

    await call.message.edit_text(call.message.text + "\n\n📦 <b>Доставлено!</b> Запрос отзыва отправлен клиенту.")

    kb = InlineKeyboardBuilder()
    for i, s in enumerate(["⭐", "⭐⭐", "⭐⭐⭐", "⭐⭐⭐⭐", "⭐⭐⭐⭐⭐"], 1):
        kb.button(text=s, callback_data=f"revrate_{i}_{order_id}")
    kb.adjust(5)
    kb.row(types.InlineKeyboardButton(text="🙅 Пропустить", callback_data=f"revskip_{order_id}"))

    try:
        await bot.send_message(user_id,
            f"☁️ <b>Как тебе заказ?</b>\n\n📦 <b>{item_name}</b>\n\n"
            f"Сначала поставь общую оценку 👇",
            reply_markup=kb.as_markup())
    except Exception:
        await call.answer("⚠️ Не удалось отправить запрос отзыва.", show_alert=True)


@dp.callback_query(F.data.startswith("revrate_"))
async def review_rating(call: types.CallbackQuery):
    parts = call.data.split("_")
    rating, order_id = int(parts[1]), int(parts[2])

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT item_name, flavor FROM orders WHERE order_id = %s", (order_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return await call.answer("Заказ не найден", show_alert=True)
    item_name, flavor = row

    REVIEW_PENDING[call.from_user.id] = {
        "step": "strength", "order_id": order_id, "rating": rating,
        "item_name": item_name, "flavor": flavor,
        "strength": None, "taste": None, "vapor": None, "device": None, "text": None,
        "username": call.from_user.username or call.from_user.first_name or "Покупатель"
    }

    stars = "⭐" * rating
    kb = InlineKeyboardBuilder()
    for i in range(1, 6):
        kb.button(text=str(i), callback_data=f"revparam_strength_{i}_{order_id}")
    kb.adjust(5)
    kb.row(types.InlineKeyboardButton(text="⏩ Пропустить всё", callback_data=f"revnotext_{order_id}_{rating}"))

    await call.message.edit_text(
        f"Ты поставил {stars}\n\n"
        f"<b>1/3 💨 Крепость</b>\nОцени насколько крепкая жидкость (1 — лёгкая, 5 — очень крепкая):",
        reply_markup=kb.as_markup()
    )


@dp.callback_query(F.data.startswith("revparam_"))
async def review_param(call: types.CallbackQuery):
    parts = call.data.split("_")
    param, value, order_id = parts[1], int(parts[2]), int(parts[3])

    user_id = call.from_user.id
    if user_id not in REVIEW_PENDING:
        return await call.answer("Сессия истекла, начни заново.", show_alert=True)

    REVIEW_PENDING[user_id][param] = value

    if param == "strength":
        REVIEW_PENDING[user_id]["step"] = "taste"
        kb = InlineKeyboardBuilder()
        for i in range(1, 6):
            kb.button(text=str(i), callback_data=f"revparam_taste_{i}_{order_id}")
        kb.adjust(5)
        kb.row(types.InlineKeyboardButton(text="⏩ Пропустить всё", callback_data=f"revnotext_{order_id}_{REVIEW_PENDING[user_id]['rating']}"))
        await call.message.edit_text(
            f"<b>2/3 🍓 Насыщенность вкуса</b>\nОцени насколько насыщен вкус (1 — слабый, 5 — яркий):",
            reply_markup=kb.as_markup()
        )

    elif param == "taste":
        REVIEW_PENDING[user_id]["step"] = "vapor"
        kb = InlineKeyboardBuilder()
        for i in range(1, 6):
            kb.button(text=str(i), callback_data=f"revparam_vapor_{i}_{order_id}")
        kb.adjust(5)
        kb.row(types.InlineKeyboardButton(text="⏩ Пропустить всё", callback_data=f"revnotext_{order_id}_{REVIEW_PENDING[user_id]['rating']}"))
        await call.message.edit_text(
            f"<b>3/3 💨 Густота пара</b>\nОцени количество пара (1 — мало, 5 — очень много):",
            reply_markup=kb.as_markup()
        )

    elif param == "vapor":
        REVIEW_PENDING[user_id]["step"] = "device"
        kb = InlineKeyboardBuilder()
        kb.row(types.InlineKeyboardButton(text="⏩ Пропустить", callback_data=f"revdevice_skip_{order_id}"))
        await call.message.edit_text(
            "🔧 <b>На чём куришь?</b>\nНапиши название своего устройства (например: Vaporesso XROS, Voopoo Drag S):",
            reply_markup=kb.as_markup()
        )

@dp.callback_query(F.data.startswith("revdevice_"))
async def review_device(call: types.CallbackQuery):
    parts = call.data.split("_")
    device_raw, order_id = parts[1], int(parts[2])

    user_id = call.from_user.id
    if user_id not in REVIEW_PENDING:
        return await call.answer("Сессия истекла, начни заново.", show_alert=True)

    device_map = {"Pod": "Pod", "Mod": "Mod", "Odn": "Одноразка", "skip": None}
    REVIEW_PENDING[user_id]["device"] = device_map.get(device_raw)
    REVIEW_PENDING[user_id]["step"] = "text"

    rating = REVIEW_PENDING[user_id]["rating"]
    stars = "⭐" * rating
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="➡️ Пропустить комментарий",
                                       callback_data=f"revnotext_{order_id}_{rating}"))
    await call.message.edit_text(
        f"Ты поставил {stars}\n\n💬 Хочешь добавить комментарий? Напиши его.\n"
        "Или нажми кнопку, чтобы пропустить.",
        reply_markup=kb.as_markup()
    )


@dp.callback_query(F.data.startswith("revnotext_"))
async def review_no_text(call: types.CallbackQuery):
    parts = call.data.split("_")
    order_id, rating = int(parts[1]), int(parts[2])
    pending = REVIEW_PENDING.pop(call.from_user.id, {})

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT item_name, flavor FROM orders WHERE order_id = %s", (order_id,))
    row = cur.fetchone()
    conn.close()

    item_name, flavor = row if row else ("Товар", "—")
    username = call.from_user.username or call.from_user.first_name or "Покупатель"
    await _save_review(
        user_id=call.from_user.id, username=username, order_id=order_id,
        item_name=item_name, flavor=flavor, rating=rating, text=None,
        strength=pending.get("strength"), taste=pending.get("taste"),
        vapor=pending.get("vapor"), device=pending.get("device")
    )
    await call.message.edit_text("💬 Спасибо за оценку! Это помогает нам становиться лучше ☁️")


@dp.callback_query(F.data.startswith("revskip_"))
async def review_skip(call: types.CallbackQuery):
    await call.message.edit_text("Хорошо! Если захочешь — оставь отзыв через ⭐️ Отзывы 😊")


def _format_bar(value):
    if value is None:
        return "—"
    filled = "█" * value
    empty = "░" * (5 - value)
    return f"{filled}{empty} {value}/5"


async def _save_review(user_id, username, order_id, item_name, flavor, rating, text,
                       strength=None, taste=None, vapor=None, device=None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO reviews (user_id, username, order_id, item_name, flavor, rating, strength, taste, vapor, device, text) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING review_id",
        (user_id, username, order_id, item_name, flavor, rating, strength, taste, vapor, device, text)
    )
    review_id = cur.fetchone()[0]
    conn.commit()
    conn.close()

    if not ADMIN:
        return

    stars = "⭐" * rating
    admin_text = (
        f"💬 <b>Новый отзыв!</b>\n\n"
        f"👤 @{username} (<code>{user_id}</code>)\n"
        f"📦 {item_name} — {flavor}\n"
        f"Оценка: {stars} ({rating}/5)\n"
    )
    if any(v is not None for v in [strength, taste, vapor]):
        admin_text += (
            f"\n💨 Крепость: {_format_bar(strength)}"
            f"\n🍓 Вкус: {_format_bar(taste)}"
            f"\n💨 Пар: {_format_bar(vapor)}"
        )
    if device:
        admin_text += f"\n🔧 Устройство: {device}"
    admin_text += f"\n\n💬 <i>«{text}»</i>" if text else f"\n\n💬 <i>Без комментария</i>"
    admin_text += f"\n\n🆔 Отзыв №{review_id} | Заказ №{order_id}"

    kb = InlineKeyboardBuilder()
    if REVIEWS_CHANNEL_ID:
        kb.row(types.InlineKeyboardButton(text="📢 Опубликовать в канал", callback_data=f"revpub_{review_id}"))
    kb.row(types.InlineKeyboardButton(text="🗑 Не публиковать", callback_data=f"revdel_{review_id}"))
    for adm in ADMINS:
        try:
            await bot.send_message(adm, admin_text, reply_markup=kb.as_markup())
        except Exception:
            pass


@dp.callback_query(F.data.startswith("revpub_"))
async def review_publish(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer("⛔️ Нет доступа.", show_alert=True)
    if not REVIEWS_CHANNEL_ID:
        return await call.answer("⚠️ REVIEWS_CHANNEL_ID не задан!", show_alert=True)

    review_id = int(call.data.split("_")[1])
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT username, item_name, flavor, rating, strength, taste, vapor, device, text FROM reviews WHERE review_id = %s", (review_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return await call.answer("Отзыв не найден", show_alert=True)

    username, item_name, flavor, rating, strength, taste, vapor, device, text = row
    stars = "⭐" * rating
    channel_text = (
        f"☁️ <b>Отзыв покупателя</b>\n\n"
        f"📦 <b>{item_name}</b>\n"
        f"🔖 {flavor}\n"
        f"Оценка: {stars}\n"
    )
    if any(v is not None for v in [strength, taste, vapor]):
        channel_text += (
            f"\n💨 Крепость: {_format_bar(strength)}"
            f"\n🍓 Вкус: {_format_bar(taste)}"
            f"\n💨 Пар: {_format_bar(vapor)}"
        )
    if device:
        channel_text += f"\n🔧 Устройство: {device}"
    if text:
        channel_text += f"\n\n💬 <i>«{text}»</i>"
    channel_text += f"\n\n👤 @{username}"

    try:
        await bot.send_message(REVIEWS_CHANNEL_ID, channel_text)
        await call.message.edit_text(call.message.text + "\n\n✅ <b>Опубликовано в канал!</b>")
    except Exception as e:
        await call.answer(f"Ошибка: {e}", show_alert=True)


@dp.callback_query(F.data.startswith("revdel_"))
async def review_delete(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer("⛔️ Нет доступа.", show_alert=True)
    await call.message.edit_text(call.message.text + "\n\n🗑 <b>Не опубликован.</b>")


# --- ЗАПУСК ---
async def main():
    init_db()
    init_sheet_headers()
    await set_main_menu_button(bot)
    threading.Thread(target=run_server, daemon=True).start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())