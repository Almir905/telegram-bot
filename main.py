import os
import sqlite3
import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler, \
    ConversationHandler

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Настройки
ADMIN_IDS = [6608395537]  # Замените на ваш ID
DB_NAME = 'shop.db'

# Состояния для ConversationHandler
CATEGORY, NAME, PRICE, STOCK, PHOTO, GENDER, CONFIRM = range(7)
EDIT_CHOOSE, EDIT_FIELD, EDIT_VALUE = range(7, 10)
DELETE_CONFIRM = range(10, 11)

# Новые состояния для оплаты и доставки
PAYMENT_METHOD, DELIVERY_ADDRESS, PHONE_NUMBER = range(11, 14)


# ==================== БАЗА ДАННЫХ ====================
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Таблица товаров
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            gender TEXT,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            in_stock INTEGER DEFAULT 0,
            photo TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Таблица корзины
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cart (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER DEFAULT 1,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products (id)
        )
    ''')

    # Таблица заказов (обновлена с информацией о доставке и оплате)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            user_name TEXT,
            user_phone TEXT,
            products TEXT NOT NULL,
            total_price REAL NOT NULL,
            payment_method TEXT,
            delivery_address TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Таблица отзывов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            user_name TEXT,
            rating INTEGER,
            comment TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()


# ==================== КЛАВИАТУРЫ ====================
def get_main_keyboard(user_id=None):
    keyboard = [
        ["📿 Каталог", "🛒 Корзина"],
        ["🚚 Доставка", "📞 Контакты"],
        ["⭐ Отзывы", "ℹ️ О нас"]
    ]
    if user_id and user_id in ADMIN_IDS:
        keyboard.append(["👑 Админ-панель"])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_back_keyboard():
    return ReplyKeyboardMarkup([["⬅️ Назад"]], resize_keyboard=True)


def get_admin_keyboard():
    keyboard = [
        ["➕ Добавить товар", "✏️ Редактировать товар"],
        ["❌ Удалить товар", "📊 Статистика"],
        ["📦 Управление заказами", "⭐ Управление отзывами"],
        ["⬅️ Главное меню"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_categories_keyboard():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT category FROM products ORDER BY category")
    categories = cursor.fetchall()
    conn.close()

    buttons = []
    row = []
    for i, (category,) in enumerate(categories, 1):
        row.append(KeyboardButton(category))
        if i % 2 == 0 or i == len(categories):
            buttons.append(row)
            row = []
    buttons.append(["⬅️ Назад"])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)


def get_cart_keyboard():
    keyboard = [
        ["💳 Оформить заказ", "🔄 Очистить корзину"],
        ["⬅️ Продолжить покупки"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_payment_keyboard():
    keyboard = [
        ["💳 Оплата картой", "💰 Оплата наличными"],
        ["📱 Элсом", "🏦 М-Банк"],
        ["⬅️ Назад"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_order_status_keyboard(order_id):
    keyboard = [
        [InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm_{order_id}")],
        [InlineKeyboardButton("🚚 Отправить", callback_data=f"ship_{order_id}")],
        [InlineKeyboardButton("✅ Завершить", callback_data=f"complete_{order_id}")],
        [InlineKeyboardButton("❌ Отменить", callback_data=f"cancel_{order_id}")]
    ]
    return InlineKeyboardMarkup(keyboard)


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
def is_admin(user_id):
    return user_id in ADMIN_IDS


def get_cart_count(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT SUM(quantity) FROM cart WHERE user_id=?", (user_id,))
    result = cursor.fetchone()[0]
    conn.close()
    return result or 0


# ==================== ОСНОВНЫЕ КОМАНДЫ ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"السلام عليكم ورحمة الله وبركاته 🌙\n"
        f"Добро пожаловать в магазин *Nazif.store*!\n\n"
        f"*Ассалому алейкум, {user.first_name}!* 👋\n\n"
        f"📿 *Наш ассортимент:*\n"
        f"• Джайнамазы (намазлыки) ручной работы\n"
        f"• Исламские книги на кыргызском и русском\n"
        f"• Тасбихи из натуральных материалов\n"
        f"• Подарки для мусульман\n\n"
        f"🕌 *Качество и халяльность гарантированы!*",
        parse_mode='Markdown',
        reply_markup=get_main_keyboard(user.id)
    )


async def show_contacts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📞 *Контакты Nazif.store*\n\n"
        "📍 *Адрес:* г. Бишкек, ул. Токтогула, 123\n"
        "📱 *Телефон:* +996 (990)807407\n"
        "✉️ *Email:* info@nazif.store\n"
        "📲 *Instagram:* @nazif.store\n\n"
        "⏰ *Время работы:*\n"
        "Пн-Пт: 9:00 - 19:00\n"
        "Сб-Вс: 10:00 - 18:00\n\n"
        "📦 *Доставка по всему Кыргызстану!*\n"
        "Мы всегда на связи! Иншаллах 🤲"
    )
    await update.message.reply_text(text, parse_mode='Markdown')


async def show_delivery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🚚 *Условия доставки*\n\n"
        "🏙️ *По Бишкеку:*\n"
        "• Курьерская доставка: 150 сом\n"
        "• Бесплатно при заказе от 1000 сом\n"
        "• Время доставки: 1-3 часа\n\n"
        "🇰🇬 *По регионам Кыргызстана:*\n"
        "• Доставка через Nurkhan Express\n"
        "• Стоимость: от 250 сом\n"
        "• Сроки: 1-3 дня\n\n"
        "📦 *Самовывоз:*\n"
        "• Адрес: г. Бишкек, ул. Токтогула, 123\n"
        "• Время: Пн-Вс с 9:00 до 19:00\n\n"
        "*Для оформления доставки добавьте товары в корзину и нажмите «Оформить заказ»*"
    )
    await update.message.reply_text(text, parse_mode='Markdown')


async def show_about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🕌 *О Nazif.store*\n\n"
        "*Nazif.store* — это первый исламский магазин в Кыргызстане, специализирующийся на:\n\n"
        "📿 *Джайнамазы (намазлыки):*\n"
        "• Ручная вышивка\n"
        "• Натуральные ткани (хлопок, шёлк)\n"
        "• Различные размеры и дизайны\n\n"
        "📚 *Исламские книги:*\n"
        "• На кыргызском и русском языках\n"
        "• Коран с переводом\n"
        "• Книги по фикху и акыде\n"
        "• Детская исламская литература\n\n"
        "🕋 *Тасбихи и подарки:*\n"
        "• Тасбихи из оливкового дерева\n"
        "• Серебряные изделия\n"
        "• Подарки для Эйдов\n\n"
        "✨ *Наши преимущества:*\n"
        "✅ 100% халяльные товары\n"
        "✅ Гарантия качества\n"
        "✅ Быстрая доставка\n"
        "✅ Поддержка 24/7\n\n"
        "*С нами вы обретёте качественные товары для поклонения!* 🤲"
    )
    await update.message.reply_text(text, parse_mode='Markdown')


async def show_reviews(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT user_name, rating, comment, created_at 
        FROM reviews 
        ORDER BY created_at DESC 
        LIMIT 10
    """)

    reviews = cursor.fetchall()
    conn.close()

    if not reviews:
        text = "⭐ *Отзывы о Nazif.store*\n\nПока нет отзывов. Будьте первым!"
        await update.message.reply_text(text, parse_mode='Markdown')
        return

    text = "⭐ *Отзывы о Nazif.store*\n\n"

    for user_name, rating, comment, created_at in reviews:
        stars = "⭐" * rating
        text += f"*{user_name}* {stars}\n"
        if comment:
            text += f"_{comment}_\n"
        text += f"📅 {created_at[:10]}\n\n"

    keyboard = [[InlineKeyboardButton("📝 Оставить отзыв", callback_data="add_review")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=reply_markup)


# ==================== КАТАЛОГ И ТОВАРЫ ====================
async def show_catalog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ["📿 Джайнамазы", "🕋 Тасбихи"],
        ["📚 Книги", "🎁 Подарки"],
        ["👗 Для женщин", "👔 Для мужчин"],
        ["📦 Все товары", "⬅️ Главное меню"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    text = (
        "📿 *Каталог Nazif.store*\n\n"
        "Выберите категорию:\n\n"
        "*📿 Джайнамазы* — намазлыки ручной работы\n"
        "*🕋 Тасбихи* — из натуральных материалов\n"
        "*📚 Книги* — исламская литература\n"
        "*🎁 Подарки* — для мусульман\n"
        "*👗 Для женщин* — женские товары\n"
        "*👔 Для мужчин* — мужские товары"
    )

    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=reply_markup)


async def show_category_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    category = update.message.text

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    try:
        if category == "📦 Все товары":
            cursor.execute("""
                SELECT id, name, price, in_stock, photo, category, gender 
                FROM products 
                ORDER BY category, name
            """)
            rows = cursor.fetchall()
            await display_all_products(update, context, rows)
            return

        # Для джайнамаз проверяем размеры
        if category == "📿 Джайнамазы":
            keyboard = [
                ["📿 Стандартные", "📿 Большие"],
                ["📿 Детские", "📿 Люкс"],
                ["📦 Все товары", "⬅️ Назад"]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            context.user_data['selected_category'] = category
            await update.message.reply_text("Выберите размер джайнамаза:", reply_markup=reply_markup)
            return

        # Если только один гендер, показываем товары
        cursor.execute("""
            SELECT id, name, price, in_stock, photo, gender 
            FROM products 
            WHERE category=? 
            ORDER BY name
        """, (category,))
        rows = cursor.fetchall()

        await display_products(update, context, rows, category)

    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        await update.message.reply_text("Ошибка базы данных. Попробуйте позже.")
    finally:
        conn.close()


async def display_products(update: Update, context: ContextTypes.DEFAULT_TYPE, rows, category, gender=None):
    if not rows:
        await update.message.reply_text("Товаров в этой категории пока нет.", reply_markup=get_back_keyboard())
        return

    # Отправляем первый товар с фото если есть
    first_with_photo = None
    for row in rows:
        if row[4]:  # если есть фото
            first_with_photo = row
            break

    if first_with_photo:
        pid, name, price, in_stock, photo, prod_gender = first_with_photo
        caption = f"📿 *{name}*\n💰 *Цена:* {price} сом\n{'✅ В наличии' if in_stock > 0 else '❌ Нет в наличии'}"

        try:
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=photo,
                caption=caption,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Error sending photo: {e}")

    text = f"📿 *Товары* ({len(rows)} шт.):\n\n"
    buttons = []

    for pid, name, price, in_stock, photo, prod_gender in rows:
        if in_stock == 0:
            text += f"❌ {name} — {price} сом (нет в наличии)\n"
        else:
            text += f"✅ {name} — {price} сом\n"
            buttons.append([f"➕ {name} — {price} сом"])

    if not any(row[3] > 0 for row in rows):
        text += "\nВсе товары временно отсутствуют."

    # Добавляем кнопки админ-панели если пользователь админ
    if is_admin(update.effective_user.id):
        buttons.append(["✏️ Редактировать товары", "❌ Удалить товары"])

    buttons.append(["🛒 Корзина", "⬅️ Назад в меню"])

    keyboard = ReplyKeyboardMarkup(buttons, resize_keyboard=True)

    if first_with_photo:
        await update.message.reply_text(text, parse_mode='Markdown', reply_markup=keyboard)
    else:
        await update.message.reply_text(text, parse_mode='Markdown', reply_markup=keyboard)

    if is_admin(update.effective_user.id):
        context.user_data['admin_products'] = rows
        context.user_data['admin_category'] = category
        context.user_data['admin_gender'] = gender


# ==================== ОПЛАТА И ДОСТАВКА ====================
async def checkout_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT p.id, p.name, p.price, c.quantity, p.in_stock 
        FROM cart c
        JOIN products p ON c.product_id = p.id
        WHERE c.user_id = ?
    """, (user_id,))

    items = cursor.fetchall()
    conn.close()

    if not items:
        await update.message.reply_text("Ваша корзина пуста!")
        return

    # Проверяем доступность
    unavailable_items = []
    for product_id, name, price, quantity, in_stock in items:
        if quantity > in_stock:
            unavailable_items.append((name, in_stock))

    if unavailable_items:
        text = "⚠️ Некоторые товары недоступны в выбранном количестве:\n"
        for name, available in unavailable_items:
            text += f"• {name} (доступно: {available} шт.)\n"
        text += "\nПожалуйста, измените количество в корзине."
        await update.message.reply_text(text)
        return

    await update.message.reply_text(
        "💳 *Выберите способ оплаты:*",
        parse_mode='Markdown',
        reply_markup=get_payment_keyboard()
    )

    context.user_data['checkout_items'] = items
    return PAYMENT_METHOD


async def process_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment_method = update.message.text
    context.user_data['payment_method'] = payment_method

    await update.message.reply_text(
        "📱 *Введите ваш номер телефона для связи:*\n\n"
        "Пример: +996 555 123 456",
        parse_mode='Markdown',
        reply_markup=get_back_keyboard()
    )

    return PHONE_NUMBER


async def process_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text
    context.user_data['phone'] = phone

    await update.message.reply_text(
        "📍 *Введите адрес доставки:*\n\n"
        "Укажите город, улицу, дом и квартиру:\n"
        "Пример: Бишкек, ул. Токтогула, 123, кв. 45",
        parse_mode='Markdown',
        reply_markup=get_back_keyboard()
    )

    return DELIVERY_ADDRESS


async def process_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    address = update.message.text
    user_id = update.effective_user.id
    user_name = update.effective_user.full_name

    items = context.user_data.get('checkout_items', [])
    payment_method = context.user_data.get('payment_method', 'Не указан')
    phone = context.user_data.get('phone', 'Не указан')

    # Рассчитываем итог
    total = 0
    order_details = []

    for product_id, name, price, quantity, in_stock in items:
        item_total = price * quantity
        total += item_total
        order_details.append(f"{name} x{quantity} = {item_total} сом")

    # Добавляем стоимость доставки
    if "Бишкек" in address or "бишкек" in address:
        if total < 1000:
            delivery_cost = 150
            total += delivery_cost
            order_details.append(f"Доставка по Бишкеку = {delivery_cost} сом")
        else:
            order_details.append("Доставка по Бишкеку = Бесплатно")
    else:
        delivery_cost = 250
        total += delivery_cost
        order_details.append(f"Доставка по регионам = {delivery_cost} сом")

    products_text = "\n".join(order_details)

    # Сохраняем заказ в базу
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO orders (user_id, user_name, user_phone, products, total_price, payment_method, delivery_address)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (user_id, user_name, phone, products_text, total, payment_method, address))

    order_id = cursor.lastrowid

    # Очищаем корзину
    cursor.execute("DELETE FROM cart WHERE user_id=?", (user_id,))

    conn.commit()
    conn.close()

    # Отправляем подтверждение клиенту
    text = (
        f"🕌 *Заказ №{order_id} оформлен!*\n\n"
        f"*Товары:*\n{products_text}\n\n"
        f"*Итого:* {total} сом\n\n"
        f"*Способ оплаты:* {payment_method}\n"
        f"*Телефон:* {phone}\n"
        f"*Адрес доставки:* {address}\n\n"
        f"📞 *Наш менеджер свяжется с вами в течение 15 минут для подтверждения заказа.*\n\n"
        f"*Благодарим за покупку в Nazif.store!* 🤲\n"
        f"Пусть Аллах примет ваше поклонение! Амин 🌙"
    )

    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=get_main_keyboard(user_id))

    # Уведомление администратору
    admin_text = (
        f"🛒 *НОВЫЙ ЗАКАЗ №{order_id}*\n\n"
        f"*Клиент:* {user_name}\n"
        f"*ID:* {user_id}\n"
        f"*Телефон:* {phone}\n\n"
        f"*Товары:*\n{products_text}\n\n"
        f"*Адрес:* {address}\n"
        f"*Оплата:* {payment_method}\n"
        f"*Итого:* {total} сом"
    )

    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=admin_text,
                parse_mode='Markdown',
                reply_markup=get_order_status_keyboard(order_id)
            )
        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id}: {e}")

    context.user_data.clear()
    return ConversationHandler.END


# ==================== АДМИН-УПРАВЛЕНИЕ ЗАКАЗАМИ ====================
async def manage_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, user_name, total_price, status, created_at 
        FROM orders 
        ORDER BY created_at DESC 
        LIMIT 10
    """)

    orders = cursor.fetchall()
    conn.close()

    if not orders:
        await update.message.reply_text("📭 Нет заказов для отображения.")
        return

    text = "📦 *Последние заказы:*\n\n"

    for order_id, user_name, total_price, status, created_at in orders:
        status_icon = {
            'pending': '⏳',
            'confirmed': '✅',
            'shipped': '🚚',
            'completed': '🏁',
            'cancelled': '❌'
        }.get(status, '📦')

        text += f"{status_icon} *Заказ №{order_id}*\n"
        text += f"👤 {user_name}\n"
        text += f"💰 {total_price} сом\n"
        text += f"📅 {created_at[:10]}\n"
        text += f"Статус: {status}\n\n"

    await update.message.reply_text(text, parse_mode='Markdown')


async def order_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    order_id = int(data.split('_')[1])
    action = data.split('_')[0]

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Обновляем статус заказа
    status_map = {
        'confirm': 'confirmed',
        'ship': 'shipped',
        'complete': 'completed',
        'cancel': 'cancelled'
    }

    new_status = status_map.get(action)

    if new_status:
        cursor.execute("UPDATE orders SET status=? WHERE id=?", (new_status, order_id))
        conn.commit()

        # Получаем информацию о заказе для уведомления клиента
        cursor.execute("SELECT user_id, user_name FROM orders WHERE id=?", (order_id,))
        order = cursor.fetchone()

        if order:
            user_id, user_name = order

            status_messages = {
                'confirmed': "✅ Ваш заказ подтвержден!",
                'shipped': "🚚 Ваш заказ отправлен!",
                'completed': "🏁 Заказ доставлен и завершен!",
                'cancelled': "❌ Заказ отменен. Свяжитесь с поддержкой."
            }

            message = status_messages.get(new_status, "Статус заказа обновлен.")

            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"📦 *Заказ №{order_id}*\n\n{message}\n\nСпасибо, что выбрали Nazif.store! 🌙",
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Failed to notify user {user_id}: {e}")

    conn.close()

    await query.edit_message_text(
        text=f"✅ Статус заказа №{order_id} обновлен на: {new_status}",
        reply_markup=None
    )


# ==================== ОБРАБОТЧИК СООБЩЕНИЙ ====================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    # Основное меню
    if text == "⬅️ Главное меню":
        await update.message.reply_text("Главное меню:", reply_markup=get_main_keyboard(user_id))

    elif text == "📿 Каталог":
        await show_catalog(update, context)

    elif text == "🛒 Корзина":
        await show_cart(update, context)

    elif text == "🚚 Доставка":
        await show_delivery(update, context)

    elif text == "📞 Контакты":
        await show_contacts(update, context)

    elif text == "⭐ Отзывы":
        await show_reviews(update, context)

    elif text == "ℹ️ О нас":
        await show_about(update, context)

    elif text == "👑 Админ-панель":
        await admin_panel(update, context)

    # Админские функции
    elif text == "➕ Добавить товар":
        await add_product_start(update, context)

    elif text == "✏️ Редактировать товар":
        await edit_product_start(update, context)

    elif text == "❌ Удалить товар":
        await delete_product(update, context)

    elif text == "📊 Статистика":
        await show_stats(update, context)

    elif text == "📦 Управление заказами":
        await manage_orders(update, context)

    # Категории товаров
    elif text in ["📿 Джайнамазы", "🕋 Тасбихи", "📚 Книги", "🎁 Подарки", "👗 Для женщин", "👔 Для мужчин", "📦 Все товары"]:
        await show_category_products(update, context)

    # Подкатегории джайнамаз
    elif text in ["📿 Стандартные", "📿 Большие", "📿 Детские", "📿 Люкс"]:
        category = context.user_data.get('selected_category', '📿 Джайнамазы')
        size_map = {
            "📿 Стандартные": "Стандартный",
            "📿 Большие": "Большой",
            "📿 Детские": "Детский",
            "📿 Люкс": "Люкс"
        }
        size = size_map.get(text)

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name, price, in_stock, photo, gender 
            FROM products 
            WHERE category=? AND (name LIKE ? OR gender=?)
            ORDER BY name
        """, (category, f"%{size}%", size))
        rows = cursor.fetchall()
        conn.close()

        await display_products(update, context, rows, category, size)

    # Добавление в корзину
    elif text.startswith("➕ "):
        await add_to_cart(update, context)

    # Корзина
    elif text == "💳 Оформить заказ":
        await checkout_start(update, context)

    elif text == "🔄 Очистить корзину":
        await clear_cart(update, context)

    elif text == "⬅️ Продолжить покупки":
        await update.message.reply_text("Возвращаемся в каталог...")
        await show_catalog(update, context)

    # Назад
    elif text == "⬅️ Назад в меню":
        await update.message.reply_text("Главное меню:", reply_markup=get_main_keyboard(user_id))

    elif text == "⬅️ Назад":
        if is_admin(user_id):
            await admin_panel(update, context)
        else:
            await update.message.reply_text("Главное меню:", reply_markup=get_main_keyboard(user_id))

    # Обработка категорий товаров
    else:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT category FROM products WHERE category=?", (text,))
        category_exists = cursor.fetchone()
        conn.close()

        if category_exists:
            await show_category_products(update, context)


# ==================== ГЛАВНАЯ ФУНКЦИЯ ====================
def main():
    # Инициализация базы данных
    init_db()

    # Создаем приложение
    TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
    application = Application.builder().token(TOKEN).build()

    # Добавляем обработчики команд
    application.add_handler(CommandHandler("start", start))

    # Обработчик для добавления товара (оставить как есть)
    add_product_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Text("➕ Добавить товар"), add_product_start)],
        states={
            CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_category)],
            GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_gender)],
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_name)],
            PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_price)],
            STOCK: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_stock)],
            PHOTO: [MessageHandler(filters.TEXT | filters.PHOTO, add_product_photo)],
            CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_confirm)],
        },
        fallbacks=[MessageHandler(filters.Text("⬅️ Назад"), cancel)],
    )

    # Обработчик для редактирования товара (оставить как есть)
    edit_product_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Text("✏️ Редактировать товар"), edit_product_start)],
        states={
            EDIT_CHOOSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_product_choose)],
            EDIT_FIELD: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_product_field)],
            EDIT_VALUE: [MessageHandler(filters.TEXT | filters.PHOTO, edit_product_save)],
        },
        fallbacks=[MessageHandler(filters.Text("⬅️ Назад"), cancel)],
    )

    # Обработчик для удаления товара (оставить как есть)
    delete_product_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Text("❌ Удалить товар"), delete_product)],
        states={
            DELETE_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_product_confirm)],
        },
        fallbacks=[MessageHandler(filters.Text("⬅️ Отмена"), cancel)],
    )

    # Обработчик для оформления заказа (НОВЫЙ)
    checkout_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Text("💳 Оформить заказ"), checkout_start)],
        states={
            PAYMENT_METHOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_payment)],
            PHONE_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_phone)],
            DELIVERY_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_address)],
        },
        fallbacks=[MessageHandler(filters.Text("⬅️ Назад"), cancel)],
    )

    # Добавляем все ConversationHandler в приложение
    application.add_handler(add_product_conv)
    application.add_handler(edit_product_conv)
    application.add_handler(delete_product_conv)
    application.add_handler(checkout_conv)

    # Обработчик текстовых сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Обработчик callback запросов (для управления заказами)
    application.add_handler(CallbackQueryHandler(order_callback, pattern="^(confirm|ship|complete|cancel)_"))

    # Запускаем бота
    print("=" * 60)
    print("🕌 Бот Nazif.store запущен!")
    print(f"👑 Администраторы: {ADMIN_IDS}")
    print("📿 Магазин исламских товаров готов к работе...")
    print("=" * 60)

    application.run_polling()


if __name__ == '__main__':
    main()