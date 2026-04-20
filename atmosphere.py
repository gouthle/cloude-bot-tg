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

REFERRAL_BONUS = 5       # Бонус за приглашённого друга (zł)
LOW_STOCK_THRESHOLD = 2  # Уведомление при остатке <= этого значения

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

def decrement_stock(brand: str, flavor: str) -> int:
    """Списывает 1 шт. и возвращает новый остаток."""
    conn = sqlite3.connect('cloude_base.db')
    conn.execute(
        "UPDATE stock SET quantity = MAX(0, quantity - 1) WHERE brand = ? AND flavor = ?",
        (brand, flavor)
    )
    conn.commit()
    row = conn.execute(
        "SELECT quantity FROM stock WHERE brand = ? AND flavor = ?", (brand, flavor)
    ).fetchone()
    conn.close()
    return row[0] if row else 0

def get_balance(user_id: int) -> int:
    conn = sqlite3.connect('cloude_base.db')
    row = conn.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return row[0] if row else 0

def add_balance(user_id: int, amount: int):
    conn = sqlite3.connect('cloude_base.db')
    conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def spend_balance(user_id: int, amount: int):
    conn = sqlite3.connect('cloude_base.db')
    conn.execute("UPDATE users SET balance = MAX(0, balance - ?) WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def get_all_user_ids() -> list:
    conn = sqlite3.connect('cloude_base.db')
    rows = conn.execute("SELECT user_id FROM users").fetchall()
    conn.close()
    return [r[0] for r in rows]

def init_db():
    conn = sqlite3.connect('cloude_base.db')
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            referrer_id INTEGER,
            balance INTEGER DEFAULT 0
        )
    ''')
    # Добавляем колонку balance если её нет (для существующих БД)
    try:
        cur.execute("ALTER TABLE users ADD COLUMN balance INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

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
            track_number TEXT DEFAULT NULL,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # Добавляем колонку track_number если её нет
    try:
        cur.execute("ALTER TABLE orders ADD COLUMN track_number TEXT DEFAULT NULL")
    except sqlite3.OperationalError:
        pass

    cur.execute('''
        CREATE TABLE IF NOT EXISTS stock (
            brand TEXT,
            flavor TEXT,
            quantity INTEGER DEFAULT 0,
            PRIMARY KEY (brand, flavor)
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS referrals (
            referrer_id INTEGER,
            referred_id INTEGER PRIMARY KEY
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

# Множество для хранения ожидающих рассылку
BROADCAST_PENDING = set()
# Словарь для хранения ожидающих трек-номер: {admin_id: (order_id, user_id)}
TRACK_PENDING = {}
# Словарь для ожидающих скриншот оплаты
PAYMENT_PENDING = {}

# --- ЧАСТЬ 6: ХЕНДЛЕРЫ МЕНЮ ---

@dp.message(CommandStart())
async def start_handler(message: types.Message):
    start_command = message.text.split()
    referrer_raw = start_command[1] if len(start_command) > 1 else None

    referrer_id = None
    if referrer_raw and referrer_raw.isdigit():
        referrer_id = int(referrer_raw)
    elif referrer_raw:
        try:
            import base64
            decoded = base64.urlsafe_b64decode(referrer_raw + "==").decode()
            if decoded.isdigit():
                referrer_id = int(decoded)
        except Exception:
            pass

    db = sqlite3.connect('cloude_base.db')
    is_new = db.execute(
        "SELECT 1 FROM users WHERE user_id = ?", (message.from_user.id,)
    ).fetchone() is None

    db.execute(
        "INSERT OR IGNORE INTO users (user_id, username, referrer_id, balance) VALUES (?, ?, ?, 0)",
        (message.from_user.id, message.from_user.username, referrer_id)
    )
    db.commit()
    db.close()

    # Начисляем бонус рефереру если это новый юзер
    if is_new and referrer_id and referrer_id != message.from_user.id:
        db = sqlite3.connect('cloude_base.db')
        already = db.execute(
            "SELECT 1 FROM referrals WHERE referred_id = ?", (message.from_user.id,)
        ).fetchone()
        if not already:
            db.execute(
                "INSERT OR IGNORE INTO referrals (referrer_id, referred_id) VALUES (?, ?)",
                (referrer_id, message.from_user.id)
            )
            db.commit()
            db.close()
            add_balance(referrer_id, REFERRAL_BONUS)
            try:
                await bot.send_message(
                    referrer_id,
                    f"🎉 По твоей ссылке зарегистрировался новый пользователь!\n"
                    f"На твой счёт начислено <b>+{REFERRAL_BONUS}zł</b> бонусов 💰"
                )
            except Exception:
                pass
        else:
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
    balance = get_balance(message.from_user.id)
    link = await create_start_link(bot, str(message.from_user.id), encode=True)

    db = sqlite3.connect('cloude_base.db')
    ref_count = db.execute(
        "SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (message.from_user.id,)
    ).fetchone()[0]
    db.close()

    await message.answer(
        f"💰 <b>Твой баланс: {balance}zł</b>\n\n"
        f"👥 Приглашено друзей: <b>{ref_count}</b>\n"
        f"🎁 За каждого друга: <b>+{REFERRAL_BONUS}zł</b>\n\n"
        f"Бонусы можно потратить при оформлении заказа!\n\n"
        f"<b>Твоя реферальная ссылка:</b>\n<code>{link}</code>"
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
        "SELECT item_name, flavor, total, status, track_number FROM orders WHERE user_id = ? ORDER BY date DESC LIMIT 5",
        (message.from_user.id,)
    ).fetchall()
    db.close()

    if not rows:
        return await message.answer("У тебя пока нет заказов.")

    text = "📜 <b>Последние заказы:</b>\n\n"
    for item, flav, tot, stat, track in rows:
        text += f"▪️ {item} ({flav}) — {tot}zł\nСтатус: <b>{stat}</b>"
        if track:
            text += f"\n📦 Трек: <code>{track}</code>"
        text += "\n\n"
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
    keyboard.row(types.InlineKeyboardButton(text="📢 Рассылка", callback_data="adm_broadcast"))
    return keyboard.as_markup()

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN:
        return await message.answer("⛔️ Нет доступа.")
    await message.answer(
        "⚙️ <b>Админ-панель</b>\n\nВыбери раздел:",
        reply_markup=get_admin_brands_keyboard()
    )

@dp.callback_query(F.data == "adm_brands")
async def adm_brands(call: types.CallbackQuery):
    if call.from_user.id != ADMIN:
        return await call.answer("⛔️ Нет доступа.", show_alert=True)
    await call.message.edit_text(
        "⚙️ <b>Админ-панель</b>\n\nВыбери раздел:",
        reply_markup=get_admin_brands_keyboard()
    )

@dp.callback_query(F.data == "adm_broadcast")
async def adm_broadcast_start(call: types.CallbackQuery):
    if call.from_user.id != ADMIN:
        return await call.answer("⛔️ Нет доступа.", show_alert=True)
    BROADCAST_PENDING.add(call.from_user.id)
    await call.message.edit_text(
        "📢 <b>Рассылка</b>\n\nОтправь следующим сообщением текст рассылки.\n"
        "Поддерживается HTML-разметка: <b>жирный</b>, <i>курсив</i>, <code>код</code>.\n\n"
        "Для отмены напиши /admin"
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
    balance = get_balance(call.from_user.id)

    keyboard = InlineKeyboardBuilder()
    keyboard.row(types.InlineKeyboardButton(
        text="📦 InPost (+14zł)",
        callback_data=f"pay_i_{brand_idx}_{flavor_idx}_{price_int + 14}_0"
    ))
    keyboard.row(types.InlineKeyboardButton(
        text="🤝 Inpost GRATIS (От 5 штук)",
        callback_data=f"pay_g_{brand_idx}_{flavor_idx}_{price_int}_0"
    ))

    if balance > 0:
        use_bonus = min(balance, price_int)
        keyboard.row(types.InlineKeyboardButton(
            text=f"🎁 InPost со скидкой -{use_bonus}zł (баланс: {balance}zł)",
            callback_data=f"pay_i_{brand_idx}_{flavor_idx}_{price_int + 14}_{use_bonus}"
        ))
        keyboard.row(types.InlineKeyboardButton(
            text=f"🎁 GRATIS со скидкой -{use_bonus}zł (баланс: {balance}zł)",
            callback_data=f"pay_g_{brand_idx}_{flavor_idx}_{price_int}_{use_bonus}"
        ))

    keyboard.row(types.InlineKeyboardButton(
        text="⬅️ Назад к вкусам",
        callback_data=f"brn_{brand_idx}"
    ))

    text = f"📍 <b>Оформление:</b> {brand_name} — {flavor}\n\nВыбери способ получения:"
    if balance > 0:
        text += f"\n\n💰 У тебя есть <b>{balance}zł</b> бонусов — можешь применить при выборе!"

    await call.message.delete()
    await call.bot.send_message(call.from_user.id, text, reply_markup=keyboard.as_markup())


@dp.callback_query(F.data.startswith("pay_"))
async def payment_callback(call: types.CallbackQuery):
    parts = call.data.split("_")
    delivery_code = parts[1]
    brand_idx, flavor_idx, total, bonus_used = parts[2], parts[3], parts[4], parts[5]

    brand_name = idx_to_brand(brand_idx)
    flavors = STOCKS.get(brand_name, {}).get("flavors", [])

    try:
        flavor = flavors[int(flavor_idx)]
    except (IndexError, ValueError):
        return await call.answer("Ошибка: вкус не найден")

    delivery_type = "InPost" if delivery_code == "i" else "GRATIS"
    bonus_int = int(bonus_used)
    total_int = int(total)
    final_total = max(0, total_int - bonus_int)

    pay_text = (
        f"💳 <b>Оплата заказа</b>\n\n"
        f"Товар: {brand_name} ({flavor})\n"
        f"Способ: {delivery_type}\n"
    )
    if bonus_int > 0:
        pay_text += f"🎁 Бонусная скидка: -{bonus_int}zł\n"
    pay_text += (
        f"<b>Сумма к оплате: {final_total}zł</b>\n\n"
        f"Переведи ровную сумму по BLIK на номер:\n<code>{PHONE_NUMBER}</code>\n\n"
        "📸 После оплаты пришли <b>скриншот чека</b> следующим сообщением.\n"
        "Или нажми кнопку ниже если не можешь отправить фото."
    )

    keyboard = InlineKeyboardBuilder()
    keyboard.row(types.InlineKeyboardButton(
        text="✅ Оплатил(а), фото нет",
        callback_data=f"fin_{delivery_code}_{brand_idx}_{flavor_idx}_{final_total}_{bonus_int}"
    ))
    keyboard.row(types.InlineKeyboardButton(text="❌ Отменить", callback_data="back_to_cats"))

    # Сохраняем ожидание скриншота
    PAYMENT_PENDING[call.from_user.id] = {
        "delivery_code": delivery_code,
        "brand_idx": brand_idx,
        "flavor_idx": flavor_idx,
        "total": final_total,
        "bonus": bonus_int
    }

    await call.message.edit_text(pay_text, reply_markup=keyboard.as_markup())


@dp.callback_query(F.data.startswith("fin_"))
async def finish_callback(call: types.CallbackQuery):
    parts = call.data.split("_")
    delivery_code = parts[1]
    brand_idx, flavor_idx, total, bonus_used = parts[2], parts[3], parts[4], parts[5]

    brand_name = idx_to_brand(brand_idx)
    flavors = STOCKS.get(brand_name, {}).get("flavors", [])

    try:
        flavor = flavors[int(flavor_idx)]
    except (IndexError, ValueError):
        return await call.answer("Ошибка: вкус не найден")

    delivery = "InPost" if delivery_code == "i" else "GRATIS"
    bonus_int = int(bonus_used)

    PAYMENT_PENDING.pop(call.from_user.id, None)

    await _create_order(
        bot=call.bot,
        user_id=call.from_user.id,
        username=call.from_user.username or "без ника",
        brand_name=brand_name,
        flavor=flavor,
        total=total,
        delivery=delivery,
        bonus_used=bonus_int,
        photo_id=None,
        message=call.message,
        is_callback=True
    )


async def _create_order(bot, user_id, username, brand_name, flavor, total, delivery, bonus_used, photo_id, message, is_callback=False):
    """Создаёт заказ в БД и уведомляет админа."""
    db = sqlite3.connect('cloude_base.db')
    cur = db.cursor()
    cur.execute(
        "INSERT INTO orders (user_id, item_name, flavor, total, delivery, info, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, brand_name, flavor, total, delivery, "Ожидаем данные InPost", "WAIT_DATA")
    )
    order_id = cur.lastrowid
    db.commit()
    db.close()

    if bonus_used > 0:
        spend_balance(user_id, bonus_used)

    if delivery == "InPost":
        text = (
            "📝 <b>Важно!</b>\nПришли следующим сообщением данные для InPost:\n"
            "1. Твои ФИО\n"
            "2. Номер телефона\n"
            "3. Код пачкомата (напр. KRA01M)"
        )
        if is_callback:
            await message.edit_text(text)
        else:
            await bot.send_message(user_id, text)
    else:
        if ADMIN:
            kb = InlineKeyboardBuilder()
            kb.row(
                types.InlineKeyboardButton(text="✅ Оплата пришла", callback_data=f"confirm_{order_id}_{user_id}"),
                types.InlineKeyboardButton(text="❌ Не пришла", callback_data=f"reject_{order_id}_{user_id}")
            )
            kb.row(
                types.InlineKeyboardButton(text="🚚 Отправить трек", callback_data=f"track_{order_id}_{user_id}")
            )
            admin_text = (
                f"⚡️ <b>НОВЫЙ ЗАКАЗ (GRATIS)</b>\n"
                f"👤 @{username} (<code>{user_id}</code>)\n"
                f"📦 {brand_name} — {flavor}\n"
                f"💵 Сумма: <b>{total}zł</b>"
            )
            if bonus_used > 0:
                admin_text += f" (скидка -{bonus_used}zł)"
            admin_text += (
                f"\n🚚 Доставка: {delivery}\n"
                f"🆔 Заказ №{order_id}"
            )
            if photo_id:
                await bot.send_photo(ADMIN, photo_id, caption=admin_text, reply_markup=kb.as_markup())
            else:
                admin_text += "\n📸 Скриншот: не прислан"
                await bot.send_message(ADMIN, admin_text, reply_markup=kb.as_markup())

        reply_text = "🚀 <b>Заказ принят!</b> Менеджер свяжется с тобой для передачи товара."
        if is_callback:
            await message.edit_text(reply_text)
        else:
            await bot.send_message(user_id, reply_text)


@dp.callback_query(F.data == "back_to_cats")
async def back_to_cats(call: types.CallbackQuery):
    keyboard = InlineKeyboardBuilder()
    for brand in BRAND_LIST:
        idx = brand_to_idx(brand)
        keyboard.row(types.InlineKeyboardButton(text=brand, callback_data=f"brn_{idx}"))

    text = "✨ <b>Каталог продукции</b>\nВыбери бренд:"
    await call.message.delete()
    await call.bot.send_message(call.from_user.id, text, reply_markup=keyboard.as_markup())


# --- ЧАСТЬ 9: ОБРАБОТКА ТЕКСТА И ФОТО ---

@dp.message(F.photo)
async def photo_handler(message: types.Message):
    # Хелпер ID фото для админа (если не ждём скриншот)
    if ADMIN and message.from_user.id == ADMIN and message.from_user.id not in PAYMENT_PENDING:
        await message.answer(f"ID фото для кода:\n<code>{message.photo[-1].file_id}</code>")
        return

    # Скриншот оплаты от пользователя
    if message.from_user.id in PAYMENT_PENDING:
        pending = PAYMENT_PENDING.pop(message.from_user.id)
        delivery_code = pending["delivery_code"]
        brand_idx = pending["brand_idx"]
        flavor_idx = pending["flavor_idx"]
        total = pending["total"]
        bonus_int = pending["bonus"]

        brand_name = idx_to_brand(brand_idx)
        flavors = STOCKS.get(brand_name, {}).get("flavors", [])

        try:
            flavor = flavors[int(flavor_idx)]
        except (IndexError, ValueError):
            return await message.answer("Ошибка: вкус не найден")

        delivery = "InPost" if delivery_code == "i" else "GRATIS"
        photo_id = message.photo[-1].file_id
        username = message.from_user.username or "без ника"

        await message.answer("✅ Скриншот получен! Ожидай подтверждения менеджера.")
        await _create_order(
            bot=bot,
            user_id=message.from_user.id,
            username=username,
            brand_name=brand_name,
            flavor=flavor,
            total=total,
            delivery=delivery,
            bonus_used=bonus_int,
            photo_id=photo_id,
            message=message,
            is_callback=False
        )


@dp.message(F.text, ~F.text.startswith("/"))
async def text_handler(message: types.Message):
    user_id = message.from_user.id

    # Рассылка от админа
    if user_id == ADMIN and user_id in BROADCAST_PENDING:
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

    # Трек-номер от админа
    if user_id == ADMIN and user_id in TRACK_PENDING:
        order_id, buyer_id = TRACK_PENDING.pop(user_id)
        track = message.text.strip()

        db = sqlite3.connect('cloude_base.db')
        db.execute(
            "UPDATE orders SET track_number = ?, status = 'В пути' WHERE order_id = ?",
            (track, order_id)
        )
        db.commit()
        db.close()

        await message.answer(f"✅ Трек-номер <code>{track}</code> сохранён для заказа №{order_id}.")
        try:
            await bot.send_message(
                buyer_id,
                f"📦 <b>Твой заказ отправлен!</b>\n\nТрек-номер: <code>{track}</code>\n"
                "Отследить посылку можно на сайте InPost. 🚀"
            )
        except Exception:
            await message.answer("⚠️ Не удалось уведомить пользователя.")
        return

    # Данные InPost от покупателя
    db = sqlite3.connect('cloude_base.db')
    cursor = db.cursor()
    cursor.execute(
        "SELECT order_id, item_name, flavor, total FROM orders WHERE user_id = ? AND status = 'WAIT_DATA' ORDER BY date DESC LIMIT 1",
        (user_id,)
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
            username = message.from_user.username or "без ника"
            kb = InlineKeyboardBuilder()
            kb.row(
                types.InlineKeyboardButton(text="✅ Оплата пришла", callback_data=f"confirm_{order_id}_{user_id}"),
                types.InlineKeyboardButton(text="❌ Не пришла", callback_data=f"reject_{order_id}_{user_id}")
            )
            kb.row(
                types.InlineKeyboardButton(text="🚚 Отправить трек", callback_data=f"track_{order_id}_{user_id}")
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


# --- ЧАСТЬ 10: ПОДТВЕРЖДЕНИЕ / ОТКЛОНЕНИЕ / ТРЕК ---

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

    db.execute("UPDATE orders SET status = 'Подтверждён' WHERE order_id = ?", (order_id,))
    db.commit()
    db.close()

    new_qty = decrement_stock(item_name, flavor)

    # Уведомление если товар заканчивается
    if new_qty <= LOW_STOCK_THRESHOLD and ADMIN:
        await bot.send_message(
            ADMIN,
            f"⚠️ <b>Внимание! Товар заканчивается!</b>\n"
            f"📦 {item_name} — {flavor}\n"
            f"Остаток: <b>{new_qty} шт.</b>"
        )

    await call.message.edit_text(call.message.text + "\n\n✅ <b>Подтверждено!</b> Склад обновлён.")
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
    row = db.execute("SELECT status FROM orders WHERE order_id = ?", (order_id,)).fetchone()

    if not row:
        db.close()
        return await call.answer("Заказ не найден", show_alert=True)

    if row[0] == "Отклонён":
        db.close()
        return await call.answer("Заказ уже отклонён!", show_alert=True)

    db.execute("UPDATE orders SET status = 'Отклонён' WHERE order_id = ?", (order_id,))
    db.commit()
    db.close()

    await call.message.edit_text(call.message.text + "\n\n❌ <b>Отклонено.</b> Склад не тронут.")
    await bot.send_message(
        user_id,
        "❌ <b>Оплата не найдена.</b>\nПроверь, правильно ли ты перевёл сумму. Если есть вопросы — напиши в поддержку 🤝"
    )


@dp.callback_query(F.data.startswith("track_"))
async def send_track_number(call: types.CallbackQuery):
    if call.from_user.id != ADMIN:
        return await call.answer("⛔️ Нет доступа.", show_alert=True)

    parts = call.data.split("_")
    order_id, user_id = int(parts[1]), int(parts[2])

    TRACK_PENDING[call.from_user.id] = (order_id, user_id)
    await call.answer("Отправь трек-номер следующим сообщением.", show_alert=True)


# --- ЗАПУСК ---
async def main():
    init_db()
    await set_main_menu_button(bot)
    threading.Thread(target=run_server, daemon=True).start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())