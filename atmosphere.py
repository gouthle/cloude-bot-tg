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

if ADMIN_ID_ENV:
    ADMIN = int(ADMIN_ID_ENV)
else:
    ADMIN = None

PHONE_NUMBER = "+48 123 456 789"  # ЗАМЕНИ НА СВОЙ НОМЕР BLIK
REVIEWS_URL = "https://t.me/+cbqxYZH0tzE4MDUy"

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# --- ЧАСТЬ 3: РАБОТА С БАЗОЙ ДАННЫХ ---
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
    conn.commit()
    conn.close()

# --- ЧАСТЬ 4: АССОРТИМЕНТ ТОВАРОВ ---
STOCKS = {
    "VOZOL Salt": {
        "flavors": ["Strawberry Watermelon", "Kiwi Guava", "White Peach", "Berries"],
        "photo": None,  # Сюда вставь file_id фото после получения от бота
        "price": 45
    },
    "ELFLIQ Salt": {
        "flavors": ["Grape Cherry", "Blueberry Sour Raspberry", "Blueberry Lemon", "Watermelon", "Pina Colada"],
        "photo": None,
        "price": 45
    }
}

# Список брендов в порядке индексов — для восстановления полного имени из короткого callback
BRAND_LIST = list(STOCKS.keys())

def brand_to_idx(brand_name: str) -> str:
    """Возвращает строковый индекс бренда (0, 1, 2...)"""
    try:
        return str(BRAND_LIST.index(brand_name))
    except ValueError:
        return "0"

def idx_to_brand(idx: str) -> str:
    """Возвращает полное имя бренда по индексу"""
    try:
        return BRAND_LIST[int(idx)]
    except (ValueError, IndexError):
        return BRAND_LIST[0]

# --- ЧАСТЬ 5: КНОПКИ МЕНЮ ---
async def set_main_menu_button(bot: Bot):
    commands = [
        BotCommand(command='/start', description='Главное меню / Запуск'),
        BotCommand(command='/help', description='Помощь и поддержка')
    ]
    await bot.set_my_commands(commands)

def get_main_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.row(types.KeyboardButton(text="☁️ Витрина"), types.KeyboardButton(text="📥 Мои заказы"))
    builder.row(types.KeyboardButton(text="💰 Бонусы"), types.KeyboardButton(text="⭐️ Отзывы"))
    builder.row(types.KeyboardButton(text="🤝 Поддержка"))
    return builder.as_markup(resize_keyboard=True)

# --- ЧАСТЬ 6: ОБРАБОТКА КНОПОК МЕНЮ (ДОЛЖНЫ БЫТЬ ВЫШЕ text_handler!) ---

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


# --- ЧАСТЬ 7: INLINE CALLBACK ХЕНДЛЕРЫ ---



@dp.callback_query(F.data.startswith("brn_"))
async def flavors_callback(call: types.CallbackQuery):
    # callback_data: brn_{brand_idx}
    brand_idx = call.data.split("_", 1)[1]
    brand_name = idx_to_brand(brand_idx)
    brand_data = STOCKS.get(brand_name)
    keyboard = InlineKeyboardBuilder()

    if brand_data:
        for i, flavor in enumerate(brand_data["flavors"]):
            price = brand_data["price"]
            # callback_data: sl_{brand_idx}_{flavor_idx}_{price}
            keyboard.row(types.InlineKeyboardButton(
                text=flavor,
                callback_data=f"sl_{brand_idx}_{i}_{price}"
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


@dp.callback_query(F.data.startswith("sl_"))
async def delivery_callback(call: types.CallbackQuery):
    # callback_data: sl_{brand_idx}_{flavor_idx}_{price}
    parts = call.data.split("_")
    brand_idx, flavor_idx, price = parts[1], parts[2], parts[3]

    brand_name = idx_to_brand(brand_idx)
    brand_data = STOCKS.get(brand_name, {})
    flavors = brand_data.get("flavors", [])

    try:
        flavor = flavors[int(flavor_idx)]
    except (IndexError, ValueError):
        await call.answer("Ошибка: вкус не найден")
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

    await call.message.edit_text(
        f"📍 <b>Оформление:</b> {brand_name} — {flavor}\n\nВыбери способ получения:",
        reply_markup=keyboard.as_markup()
    )


@dp.callback_query(F.data.startswith("pay_"))
async def payment_callback(call: types.CallbackQuery):
    # callback_data: pay_{i|g}_{brand_idx}_{flavor_idx}_{total}
    parts = call.data.split("_")
    delivery_code = parts[1]
    brand_idx, flavor_idx, total = parts[2], parts[3], parts[4]

    brand_name = idx_to_brand(brand_idx)
    brand_data = STOCKS.get(brand_name, {})
    flavors = brand_data.get("flavors", [])

    try:
        flavor = flavors[int(flavor_idx)]
    except (IndexError, ValueError):
        await call.answer("Ошибка: вкус не найден")
        return

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
    # callback_data: fin_{i|g}_{brand_idx}_{flavor_idx}_{total}
    parts = call.data.split("_")
    delivery_code = parts[1]
    brand_idx, flavor_idx, total = parts[2], parts[3], parts[4]

    brand_name = idx_to_brand(brand_idx)
    brand_data = STOCKS.get(brand_name, {})
    flavors = brand_data.get("flavors", [])

    try:
        flavor = flavors[int(flavor_idx)]
    except (IndexError, ValueError):
        await call.answer("Ошибка: вкус не найден")
        return

    delivery = "InPost" if delivery_code == "i" else "GRATIS"

    db = sqlite3.connect('cloude_base.db')
    db.execute(
        "INSERT INTO orders (user_id, item_name, flavor, total, delivery, info, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (call.from_user.id, brand_name, flavor, total, delivery, "Ожидаем данные InPost", "WAIT_DATA")
    )
    db.commit()
    db.close()

    if delivery == "InPost":
        instruction = (
            "📝 <b>Важно!</b>\nПришли следующим сообщением данные для InPost:\n"
            "1. Твои ФИО\n"
            "2. Номер телефона\n"
            "3. Код пачкомата (напр. KRA01M)"
        )
        await call.message.edit_text(instruction)
    else:
        if ADMIN:
            await bot.send_message(
                ADMIN,
                f"⚡️ <b>НОВЫЙ ЗАКАЗ (GRATIS)</b>\n"
                f"Юзер: @{call.from_user.username}\n"
                f"Товар: {brand_name} {flavor}\n"
                f"Сумма: {total}zł"
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
    await call.message.edit_text(
        "✨ <b>Каталог продукции</b>\nВыбери бренд:",
        reply_markup=keyboard.as_markup()
    )


# --- ЧАСТЬ 8: ОБРАБОТКА ТЕКСТА (ДАННЫЕ INPOST) ---
# ВАЖНО: этот хендлер ПОСЛЕДНИЙ среди текстовых, иначе перехватит кнопки меню

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
            "UPDATE orders SET info = ?, status = 'Данные получены' WHERE order_id = ?",
            (message.text, order_id)
        )
        db.commit()
        db.close()

        await message.answer(
            "✅ <b>Данные получены!</b>\nМенеджер проверит оплату и отправит твой заказ. Спасибо, что выбрал Cloude!"
        )

        if ADMIN:
            admin_report = (
                f"💰 <b>НОВЫЙ ЗАКАЗ (InPost)</b>\n"
                f"От: @{message.from_user.username}\n"
                f"Товар: {item} - {flavor}\n"
                f"Сумма: {total}zł\n"
                f"Данные: {message.text}"
            )
            await bot.send_message(ADMIN, admin_report)
    else:
        db.close()
        await message.answer(
            "Используй кнопки меню для заказа. Если есть вопросы — пиши в поддержку."
        )


# --- ЗАПУСК ---
async def main():
    init_db()
    await set_main_menu_button(bot)
    threading.Thread(target=run_server, daemon=True).start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())