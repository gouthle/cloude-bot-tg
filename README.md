# cloude-bot-tg
A standalone, secondary internal sales project supported by @botfather for Telegram groups.  Simply put, it’s a store for quick contact, purchases, support, and a variety of payment methods.  All of this is CLOUDE

☁️ Cloude Atmosphere Bot
Профессиональный Telegram-бот для автоматизации продаж (вейп-шоп) в Кракове. Поддерживает витрину товаров, систему реферальных бонусов и интеграцию с InPost.

🚀 Основные функции
Интерактивная витрина: Удобное разделение на категории (жидкости/одноразки) с поддержкой фото.

Автоматизация заказов: Сбор данных для InPost и уведомление админа в реальном времени.

Система лояльности: Генерация уникальных реферальных ссылок для привлечения новых клиентов.

Удержание 24/7: Встроенный Flask-сервер для предотвращения «засыпания» на бесплатных хостингах (типа Render).

База данных: Хранение истории заказов и пользователей в SQLite3.

🛠 Технологический стек
Язык: Python 3.10+

Библиотека: aiogram 3.x (Asynchronous Telegram Bots)

База данных: SQLite3

Веб-сервер: Flask (для Health Checks)

Хостинг: Оптимизировано под Render.com

📋 Инструкция по установке
Клонируйте репозиторий:

Bash
git clone https://github.com/твой-логин/название-репозитория.git
cd название-репозитория
Установите зависимости:

Bash
pip install -r requirements.txt
Настройте переменные окружения:
Создайте файл .env в корневой папке и добавьте туда:

Fragment kodu
BOT_TOKEN=твой_токен_от_BotFather
ADMIN_ID=твой_телеграм_id
Запустите бота:

Bash
python atmosphere.py
⚙️ Настройка контента
Изменение товаров: Весь ассортимент находится в словаре STOCKS внутри atmosphere.py.

Добавление фото: Отправьте фото боту (будучи админом), скопируйте полученный file_id и вставьте его в поле photo соответствующего товара.

Реквизиты: Номер телефона для BLIK меняется в переменной PHONE_NUMBER.

📈 Деплой на Render.com
Создайте новый Web Service.

Подключите свой GitHub репозиторий.

Build Command: pip install -r requirements.txt

Start Command: python atmosphere.py

Добавьте BOT_TOKEN и ADMIN_ID в разделе Environment.

Разработано для Cloude Atmosphere. Краков 2026.

EN

Конечно, держи версию на английском. В IT-среде (и для того же GitHub) это стандарт де-факто, так проект выглядит солиднее.

☁️ Cloude Atmosphere Bot
A professional Telegram bot designed for automating sales (vape shop) in Kraków, Poland. Features a sleek storefront, referral system, and seamless InPost delivery integration.

🚀 Key Features
Interactive Storefront: Categorized product listings (liquids/disposables) with image support.

Order Automation: Automated shipping data collection (InPost) and real-time admin notifications.

Loyalty Program: Unique referral link generation to grow your customer base organically.

24/7 Uptime: Integrated Flask server to prevent "idling" on free hosting platforms like Render.com.

Database Management: Full order history and user tracking using SQLite3.

🛠 Tech Stack
Language: Python 3.10+

Framework: aiogram 3.x (Asynchronous Telegram Bots)

Database: SQLite3

Web Server: Flask (for Health Checks/Keep-alive)

Hosting: Optimized for Render.com

📋 Installation Guide
Clone the repository:

Bash
git clone https://github.com/your-username/repository-name.git
cd repository-name
Install dependencies:

Bash
pip install -r requirements.txt
Configure Environment Variables:
Create a .env file in the root directory and add your credentials:

Fragment kodu
BOT_TOKEN=your_bot_father_token
ADMIN_ID=your_telegram_id
Run the bot:

Bash
python atmosphere.py
⚙️ Content Management
Updating Products: All items are managed within the STOCKS dictionary in atmosphere.py.

Adding Photos: Send a photo to the bot (as an admin), copy the returned file_id, and paste it into the photo field for the respective product.

Payment Details: Update the PHONE_NUMBER variable to change your BLIK payment info.

📈 Deployment (Render.com)
Create a new Web Service.

Connect your GitHub repository.

Build Command: pip install -r requirements.txt

Start Command: python atmosphere.py

Add BOT_TOKEN and ADMIN_ID under the Environment tab.

Developed for Cloude Atmosphere. Kraków 2026.
