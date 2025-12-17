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
ADMIN_IDS = [123456789]  # Замените на ваш ID
DB_NAME = 'shop.db'

# Состояния для ConversationHandler
CATEGORY, NAME, PRICE, STOCK, PHOTO, GENDER, CONFIRM = range(7)
EDIT_CHOOSE, EDIT_FIELD, EDIT_VALUE = range(7, 10)
DELETE_CONFIRM = range(10, 11)


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

    # Таблица заказов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            products TEXT NOT NULL,
            total_price REAL NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()


# ==================== КЛАВИАТУРЫ ====================
def get_main_keyboard(user_id=None):
    keyboard = [
        ["📦 Каталог", "🛒 Корзина"],
        ["📞 Контакты", "ℹ️ О нас"]
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
        ["✅ Оформить заказ", "🔄 Очистить корзину"],
        ["⬅️ Продолжить покупки"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


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
        f"Привет, {user.first_name}! 👋\n"
        f"Добро пожаловать в наш магазин!",
        reply_markup=get_main_keyboard(user.id)
    )


async def show_contacts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📞 Наши контакты:\n\n"
        "📍 Адрес: г. Бишкек, ул. Примерная, 123\n"
        "📱 Телефон: +996 (555) 123-456\n"
        "✉️ Email: info@shop.kg\n"
        "⏰ Время работы: 9:00 - 21:00\n\n"
        "Мы всегда на связи! 😊"
    )
    await update.message.reply_text(text)


async def show_about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "ℹ️ О нашем магазине:\n\n"
        "Мы - лучший магазин в Кыргызстане!\n"
        "✅ Гарантия качества\n"
        "✅ Быстрая доставка\n"
        "✅ Приемлемые цены\n"
        "✅ Отзывчивая поддержка\n\n"
        "С нами удобно и выгодно! 🛍️"
    )
    await update.message.reply_text(text)


# ==================== КАТАЛОГ И ТОВАРЫ ====================
async def show_catalog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ["👕 Одежда", "👖 Обувь"],
        ["💻 Электроника", "🏠 Для дома"],
        ["📦 Все товары", "⬅️ Главное меню"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("Выберите категорию:", reply_markup=reply_markup)


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

        # Проверяем есть ли подкатегории по гендеру
        cursor.execute("SELECT DISTINCT gender FROM products WHERE category=?", (category,))
        genders = cursor.fetchall()

        if len(genders) > 1:
            # Если есть гендеры, показываем выбор
            keyboard = [
                ["👕 Мужское", "👚 Женское"],
                ["👶 Детское", "📦 Все товары"],
                ["⬅️ Назад"]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            context.user_data['selected_category'] = category
            await update.message.reply_text("Выберите раздел:", reply_markup=reply_markup)
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
        caption = f"📦 {name}\n💰 Цена: {price} сом\n{'✅ В наличии' if in_stock > 0 else '❌ Нет в наличии'}"

        try:
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=photo,
                caption=caption
            )
        except Exception as e:
            logger.error(f"Error sending photo: {e}")
            # Если не удалось отправить фото, просто показываем список

    text = f"📦 Товары ({len(rows)} шт.):\n\n"
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

    # Если уже отправили фото с первым товаром, отправляем только текст
    if first_with_photo:
        await update.message.reply_text(text, reply_markup=keyboard)
    else:
        await update.message.reply_text(text, reply_markup=keyboard)

    # Сохраняем данные для админских операций
    if is_admin(update.effective_user.id):
        context.user_data['admin_products'] = rows
        context.user_data['admin_category'] = category
        context.user_data['admin_gender'] = gender


async def display_all_products(update: Update, context: ContextTypes.DEFAULT_TYPE, rows):
    if not rows:
        await update.message.reply_text("В магазине пока нет товаров.", reply_markup=get_back_keyboard())
        return

    text = "📦 Все товары в магазине:\n\n"
    current_category = None

    for pid, name, price, in_stock, photo, category, gender in rows:
        if category != current_category:
            text += f"\n📂 {category}:\n"
            current_category = category

        status = "✅" if in_stock > 0 else "❌"
        text += f"{status} {name} — {price} сом\n"

    buttons = []
    if is_admin(update.effective_user.id):
        buttons.append(["✏️ Редактировать", "❌ Удалить"])

    buttons.append(["🛒 Корзина", "⬅️ Назад в меню"])

    keyboard = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    await update.message.reply_text(text, reply_markup=keyboard)


# ==================== КОРЗИНА ====================
async def show_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT c.id, p.name, p.price, c.quantity, p.in_stock 
        FROM cart c
        JOIN products p ON c.product_id = p.id
        WHERE c.user_id = ?
    """, (user_id,))

    items = cursor.fetchall()

    if not items:
        await update.message.reply_text(
            "🛒 Ваша корзина пуста!",
            reply_markup=get_main_keyboard(user_id)
        )
        conn.close()
        return

    total = 0
    text = "🛒 Ваша корзина:\n\n"

    for cart_id, name, price, quantity, in_stock in items:
        item_total = price * quantity
        total += item_total

        if quantity > in_stock:
            status = "⚠️"
        else:
            status = "✅"

        text += f"{status} {name}\n"
        text += f"   Цена: {price} сом x {quantity} = {item_total} сом\n"
        text += f"   [ID:{cart_id}]"

        if quantity > in_stock:
            text += f" (максимум {in_stock} шт.)\n"
        else:
            text += "\n"

    text += f"\n💵 Итого: {total} сом"

    # Проверяем есть ли товары с недостаточным количеством
    out_of_stock_items = [item for item in items if item[3] > item[4]]
    if out_of_stock_items:
        text += "\n\n⚠️ Некоторые товары недоступны в выбранном количестве!"

    await update.message.reply_text(text, reply_markup=get_cart_keyboard())
    conn.close()


async def add_to_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Этот обработчик будет вызываться при нажатии кнопок вида "➕ Название — цена"
    product_name = update.message.text.replace("➕ ", "").split(" — ")[0]
    user_id = update.effective_user.id

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Находим товар
    cursor.execute("SELECT id, price, in_stock FROM products WHERE name=?", (product_name,))
    product = cursor.fetchone()

    if not product:
        await update.message.reply_text("Товар не найден!")
        conn.close()
        return

    product_id, price, in_stock = product

    if in_stock == 0:
        await update.message.reply_text("Этот товар закончился!")
        conn.close()
        return

    # Проверяем есть ли уже в корзине
    cursor.execute("SELECT id, quantity FROM cart WHERE user_id=? AND product_id=?", (user_id, product_id))
    existing = cursor.fetchone()

    if existing:
        cart_id, quantity = existing
        if quantity + 1 <= in_stock:
            cursor.execute("UPDATE cart SET quantity=quantity+1 WHERE id=?", (cart_id,))
            await update.message.reply_text(f"✅ {product_name} добавлен в корзину!")
        else:
            await update.message.reply_text(f"❌ Нельзя добавить больше {in_stock} шт. этого товара!")
    else:
        cursor.execute("INSERT INTO cart (user_id, product_id, quantity) VALUES (?, ?, 1)", (user_id, product_id))
        await update.message.reply_text(f"✅ {product_name} добавлен в корзину!")

    conn.commit()

    # Показываем количество товаров в корзине
    cart_count = get_cart_count(user_id)
    if cart_count > 0:
        await update.message.reply_text(f"🛒 В корзине: {cart_count} товар(ов)")

    conn.close()


async def clear_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM cart WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

    await update.message.reply_text("✅ Корзина очищена!", reply_markup=get_main_keyboard(user_id))


async def checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Получаем товары из корзины
    cursor.execute("""
        SELECT p.id, p.name, p.price, c.quantity, p.in_stock 
        FROM cart c
        JOIN products p ON c.product_id = p.id
        WHERE c.user_id = ?
    """, (user_id,))

    items = cursor.fetchall()

    if not items:
        await update.message.reply_text("Ваша корзина пуста!")
        conn.close()
        return

    # Проверяем доступность
    unavailable_items = []
    total = 0
    order_details = []

    for product_id, name, price, quantity, in_stock in items:
        if quantity > in_stock:
            unavailable_items.append((name, in_stock))
        else:
            total += price * quantity
            order_details.append(f"{name} x{quantity} = {price * quantity} сом")

    if unavailable_items:
        text = "⚠️ Некоторые товары недоступны в выбранном количестве:\n"
        for name, available in unavailable_items:
            text += f"• {name} (доступно: {available} шт.)\n"
        text += "\nПожалуйста, измените количество в корзине."
        await update.message.reply_text(text)
        conn.close()
        return

    # Создаем заказ
    products_text = "; ".join(order_details)
    cursor.execute(
        "INSERT INTO orders (user_id, products, total_price) VALUES (?, ?, ?)",
        (user_id, products_text, total)
    )

    # Очищаем корзину
    cursor.execute("DELETE FROM cart WHERE user_id=?", (user_id,))

    conn.commit()

    # Отправляем подтверждение
    text = (
        "✅ Заказ оформлен!\n\n"
        f"Ваш заказ #{cursor.lastrowid}\n\n"
        f"Товары:\n{products_text}\n\n"
        f"💵 Общая сумма: {total} сом\n\n"
        "📞 С вами свяжется наш менеджер для подтверждения заказа.\n"
        "Спасибо за покупку! 🛍️"
    )

    await update.message.reply_text(text, reply_markup=get_main_keyboard(user_id))

    # Уведомление администраторам
    admin_text = (
        f"🛒 Новый заказ #{cursor.lastrowid}\n"
        f"👤 Пользователь: {update.effective_user.full_name} (ID: {user_id})\n"
        f"📦 Товары:\n{products_text}\n"
        f"💰 Сумма: {total} сом"
    )

    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(chat_id=admin_id, text=admin_text)
        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id}: {e}")

    conn.close()


# ==================== АДМИН-ПАНЕЛЬ ====================
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ У вас нет прав администратора.")
        return

    await update.message.reply_text(
        "👑 Админ-панель\n"
        "Выберите действие:",
        reply_markup=get_admin_keyboard()
    )


# ==================== ДОБАВЛЕНИЕ ТОВАРА ====================
async def add_product_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    await update.message.reply_text(
        "➕ ДОБАВЛЕНИЕ ТОВАРА\n\n"
        "Введите название категории (например: Одежда, Электроника):",
        reply_markup=get_back_keyboard()
    )
    return CATEGORY


async def add_product_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['new_product'] = {'category': update.message.text}

    keyboard = [
        ["👕 Мужское", "👚 Женское"],
        ["👶 Детское", "👥 Унисекс"],
        ["Пропустить ➡️"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await update.message.reply_text(
        "Выберите пол (для кого товар):",
        reply_markup=reply_markup
    )
    return GENDER


async def add_product_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "Пропустить ➡️":
        context.user_data['new_product']['gender'] = None
    else:
        gender_map = {
            "👕 Мужское": "Мужское",
            "👚 Женское": "Женское",
            "👶 Детское": "Детское",
            "👥 Унисекс": "Унисекс"
        }
        context.user_data['new_product']['gender'] = gender_map.get(update.message.text, update.message.text)

    await update.message.reply_text(
        "📝 Введите название товара:",
        reply_markup=get_back_keyboard()
    )
    return NAME


async def add_product_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['new_product']['name'] = update.message.text

    await update.message.reply_text(
        "💰 Введите цену товара (в сомах, только число):",
        reply_markup=get_back_keyboard()
    )
    return PRICE


async def add_product_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = float(update.message.text)
        if price <= 0:
            raise ValueError
        context.user_data['new_product']['price'] = price
    except ValueError:
        await update.message.reply_text(
            "❌ Неверная цена! Введите положительное число:",
            reply_markup=get_back_keyboard()
        )
        return PRICE

    await update.message.reply_text(
        "📦 Введите количество товара (только число):",
        reply_markup=get_back_keyboard()
    )
    return STOCK


async def add_product_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        stock = int(update.message.text)
        if stock < 0:
            raise ValueError
        context.user_data['new_product']['in_stock'] = stock
    except ValueError:
        await update.message.reply_text(
            "❌ Неверное количество! Введите целое неотрицательное число:",
            reply_markup=get_back_keyboard()
        )
        return STOCK

    keyboard = [["📷 Добавить фото"], ["Пропустить фото ➡️"], ["⬅️ Назад"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await update.message.reply_text(
        "📷 Хотите добавить фото товара?\n"
        "Отправьте фото или нажмите 'Пропустить фото':",
        reply_markup=reply_markup
    )
    return PHOTO


async def add_product_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "Пропустить фото ➡️":
        context.user_data['new_product']['photo'] = None
    elif update.message.photo:
        photo_file = update.message.photo[-1]
        context.user_data['new_product']['photo'] = photo_file.file_id
    elif update.message.text == "📷 Добавить фото":
        await update.message.reply_text(
            "📎 Пожалуйста, отправьте фото товара:",
            reply_markup=get_back_keyboard()
        )
        return PHOTO
    else:
        await update.message.reply_text(
            "❌ Пожалуйста, отправьте фото или выберите действие:",
            reply_markup=ReplyKeyboardMarkup([["📷 Добавить фото"], ["Пропустить фото ➡️"], ["⬅️ Назад"]],
                                             resize_keyboard=True)
        )
        return PHOTO

    # Показываем подтверждение
    product = context.user_data['new_product']
    text = (
        "✅ ПОДТВЕРЖДЕНИЕ ДОБАВЛЕНИЯ ТОВАРА\n\n"
        f"📂 Категория: {product['category']}\n"
        f"👤 Пол: {product.get('gender', 'Не указан')}\n"
        f"📝 Название: {product['name']}\n"
        f"💰 Цена: {product['price']} сом\n"
        f"📦 Количество: {product['in_stock']} шт.\n"
        f"📷 Фото: {'Есть' if product.get('photo') else 'Нет'}\n\n"
        "Всё верно?"
    )

    keyboard = [["✅ Да, добавить товар"], ["❌ Нет, отменить"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await update.message.reply_text(text, reply_markup=reply_markup)
    return CONFIRM


async def add_product_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Нет, отменить":
        await update.message.reply_text(
            "❌ Добавление товара отменено.",
            reply_markup=get_admin_keyboard()
        )
        context.user_data.clear()
        return ConversationHandler.END

    product = context.user_data['new_product']

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    try:
        cursor.execute('''
            INSERT INTO products (category, gender, name, price, in_stock, photo)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            product['category'],
            product.get('gender'),
            product['name'],
            product['price'],
            product['in_stock'],
            product.get('photo')
        ))

        conn.commit()
        product_id = cursor.lastrowid

        await update.message.reply_text(
            f"✅ Товар успешно добавлен!\n"
            f"ID товара: {product_id}",
            reply_markup=get_admin_keyboard()
        )

    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        await update.message.reply_text(
            f"❌ Ошибка при сохранении товара: {e}",
            reply_markup=get_admin_keyboard()
        )
    finally:
        conn.close()

    context.user_data.clear()
    return ConversationHandler.END


# ==================== РЕДАКТИРОВАНИЕ ТОВАРА ====================
async def edit_product_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT category FROM products ORDER BY category")
    categories = cursor.fetchall()
    conn.close()

    if not categories:
        await update.message.reply_text(
            "❌ Нет товаров для редактирования.",
            reply_markup=get_admin_keyboard()
        )
        return ConversationHandler.END

    buttons = []
    row = []
    for i, (category,) in enumerate(categories, 1):
        row.append(KeyboardButton(f"✏️ {category}"))
        if i % 2 == 0 or i == len(categories):
            buttons.append(row)
            row = []
    buttons.append(["⬅️ Назад"])

    reply_markup = ReplyKeyboardMarkup(buttons, resize_keyboard=True)

    await update.message.reply_text(
        "✏️ РЕДАКТИРОВАНИЕ ТОВАРА\n\n"
        "Выберите категорию для редактирования:",
        reply_markup=reply_markup
    )
    return EDIT_CHOOSE


async def edit_product_choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    category = update.message.text.replace("✏️ ", "")

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, price, in_stock, photo, gender 
        FROM products 
        WHERE category=? 
        ORDER BY name
    """, (category,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text(
            f"❌ В категории '{category}' нет товаров.",
            reply_markup=get_admin_keyboard()
        )
        return ConversationHandler.END

    text = f"📦 Товары в категории '{category}':\n\n"
    buttons = []

    for pid, name, price, in_stock, photo, gender in rows:
        status = "✅" if in_stock > 0 else "❌"
        text += f"{status} ID:{pid} - {name} ({price} сом)\n"
        buttons.append([f"🔄 ID:{pid} - {name}"])

    buttons.append(["⬅️ Назад"])

    reply_markup = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    context.user_data['edit_category'] = category
    context.user_data['edit_products'] = rows

    await update.message.reply_text(text, reply_markup=reply_markup)
    return EDIT_FIELD


async def edit_product_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_text = update.message.text
    if "ID:" in message_text:
        try:
            product_id = int(message_text.split("ID:")[1].split("-")[0].strip())
        except:
            await update.message.reply_text(
                "❌ Неверный формат. Выберите товар из списка.",
                reply_markup=get_admin_keyboard()
            )
            return ConversationHandler.END

        rows = context.user_data.get('edit_products', [])
        product = None
        for row in rows:
            if row[0] == product_id:
                product = row
                break

        if not product:
            await update.message.reply_text(
                "❌ Товар не найден.",
                reply_markup=get_admin_keyboard()
            )
            return ConversationHandler.END

        context.user_data['edit_product_id'] = product_id
        pid, name, price, in_stock, photo, gender = product

        keyboard = [
            ["📝 Название", "💰 Цена"],
            ["📦 Количество", "📂 Категория"],
            ["👤 Пол", "📷 Фото"],
            ["⬅️ Назад"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        text = (
            f"✏️ РЕДАКТИРОВАНИЕ ТОВАРА\n\n"
            f"ID: {pid}\n"
            f"Название: {name}\n"
            f"Цена: {price} сом\n"
            f"Количество: {in_stock} шт.\n"
            f"Категория: {context.user_data['edit_category']}\n"
            f"Пол: {gender if gender else 'Не указан'}\n"
            f"Фото: {'Есть' if photo else 'Нет'}\n\n"
            "Выберите что редактировать:"
        )

        await update.message.reply_text(text, reply_markup=reply_markup)
        return EDIT_VALUE

    elif update.message.text == "⬅️ Назад":
        await update.message.reply_text(
            "Возвращаемся в админ-панель...",
            reply_markup=get_admin_keyboard()
        )
        return ConversationHandler.END

    return EDIT_FIELD


async def edit_product_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    field = update.message.text
    product_id = context.user_data.get('edit_product_id')

    if not product_id:
        await update.message.reply_text(
            "❌ Ошибка: товар не выбран.",
            reply_markup=get_admin_keyboard()
        )
        return ConversationHandler.END

    field_map = {
        "📝 Название": "name",
        "💰 Цена": "price",
        "📦 Количество": "in_stock",
        "📂 Категория": "category",
        "👤 Пол": "gender",
        "📷 Фото": "photo"
    }

    if field not in field_map:
        await update.message.reply_text(
            "❌ Неверный выбор. Попробуйте снова.",
            reply_markup=get_admin_keyboard()
        )
        return ConversationHandler.END

    context.user_data['edit_field'] = field_map[field]

    if field == "📷 Фото":
        await update.message.reply_text(
            "📷 Отправьте новое фото товара (или отправьте 'удалить' чтобы удалить текущее фото):",
            reply_markup=get_back_keyboard()
        )
    else:
        await update.message.reply_text(
            f"Введите новое значение для '{field}':",
            reply_markup=get_back_keyboard()
        )

    return EDIT_VALUE


async def edit_product_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    product_id = context.user_data.get('edit_product_id')
    field = context.user_data.get('edit_field')
    value = update.message.text

    if field == "photo":
        if update.message.text.lower() == "удалить":
            new_value = None
        elif update.message.photo:
            photo_file = update.message.photo[-1]
            new_value = photo_file.file_id
        else:
            await update.message.reply_text(
                "❌ Пожалуйста, отправьте фото или 'удалить':",
                reply_markup=get_back_keyboard()
            )
            return EDIT_VALUE
    elif field == "price":
        try:
            new_value = float(value)
            if new_value <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text(
                "❌ Неверная цена! Введите положительное число:",
                reply_markup=get_back_keyboard()
            )
            return EDIT_VALUE
    elif field == "in_stock":
        try:
            new_value = int(value)
            if new_value < 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text(
                "❌ Неверное количество! Введите целое неотрицательное число:",
                reply_markup=get_back_keyboard()
            )
            return EDIT_VALUE
    else:
        new_value = value

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    try:
        if field == "gender" and value == "удалить":
            cursor.execute(f"UPDATE products SET {field}=NULL WHERE id=?", (product_id,))
        else:
            cursor.execute(f"UPDATE products SET {field}=? WHERE id=?", (new_value, product_id))

        conn.commit()

        await update.message.reply_text(
            f"✅ Товар ID:{product_id} успешно обновлен!\n"
            f"Изменено поле: {field}",
            reply_markup=get_admin_keyboard()
        )

    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        await update.message.reply_text(
            f"❌ Ошибка при обновлении товара: {e}",
            reply_markup=get_admin_keyboard()
        )
    finally:
        conn.close()

    context.user_data.clear()
    return ConversationHandler.END


# ==================== УДАЛЕНИЕ ТОВАРА ====================
async def delete_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, category, price FROM products ORDER BY category, name")
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text(
            "❌ Нет товаров для удаления.",
            reply_markup=get_admin_keyboard()
        )
        return

    text = "❌ УДАЛЕНИЕ ТОВАРА\n\n"
    buttons = []

    for pid, name, category, price in rows:
        text += f"ID:{pid} - {name} ({category}) - {price} сом\n"
        buttons.append([f"🗑️ ID:{pid} - {name}"])

    buttons.append(["⬅️ Отмена"])

    reply_markup = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    context.user_data['delete_products'] = rows

    await update.message.reply_text(text, reply_markup=reply_markup)

    return DELETE_CONFIRM


async def delete_product_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "⬅️ Отмена":
        await update.message.reply_text(
            "Удаление отменено.",
            reply_markup=get_admin_keyboard()
        )
        context.user_data.clear()
        return ConversationHandler.END

    try:
        product_id = int(update.message.text.split("ID:")[1].split("-")[0].strip())
    except:
        await update.message.reply_text(
            "❌ Неверный формат. Выберите товар из списка.",
            reply_markup=get_admin_keyboard()
        )
        return DELETE_CONFIRM

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT name FROM products WHERE id=?", (product_id,))
        product_name = cursor.fetchone()

        if not product_name:
            await update.message.reply_text(
                "❌ Товар не найден.",
                reply_markup=get_admin_keyboard()
            )
            return DELETE_CONFIRM

        cursor.execute("DELETE FROM products WHERE id=?", (product_id,))
        conn.commit()

        await update.message.reply_text(
            f"✅ Товар '{product_name[0]}' (ID:{product_id}) успешно удален!",
            reply_markup=get_admin_keyboard()
        )

    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        await update.message.reply_text(
            f"❌ Ошибка при удалении товара: {e}",
            reply_markup=get_admin_keyboard()
        )
    finally:
        conn.close()

    context.user_data.clear()
    return ConversationHandler.END


# ==================== СТАТИСТИКА ====================
async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ У вас нет прав администратора.")
        return

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT COUNT(*) FROM products")
        total_products = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM products WHERE in_stock > 0")
        available_products = cursor.fetchone()[0]

        cursor.execute("SELECT SUM(in_stock) FROM products")
        total_stock = cursor.fetchone()[0] or 0

        cursor.execute("SELECT SUM(price * in_stock) FROM products")
        total_value = cursor.fetchone()[0] or 0

        cursor.execute("SELECT COUNT(*) FROM orders")
        total_orders = cursor.fetchone()[0]

        cursor.execute("SELECT SUM(total_price) FROM orders")
        total_sales = cursor.fetchone()[0] or 0

        cursor.execute("""
            SELECT category, COUNT(*), SUM(in_stock), AVG(price)
            FROM products 
            GROUP BY category 
            ORDER BY COUNT(*) DESC
        """)
        categories_stats = cursor.fetchall()

        text = (
            "📊 СТАТИСТИКА МАГАЗИНА\n\n"
            f"📦 Всего товаров: {total_products}\n"
            f"✅ В наличии: {available_products}\n"
            f"📈 Общее количество: {total_stock} шт.\n"
            f"💰 Общая стоимость: {total_value:.2f} сом\n\n"
            f"🛒 Всего заказов: {total_orders}\n"
            f"💵 Общая выручка: {total_sales:.2f} сом\n\n"
            "📂 По категориям:\n"
        )

        for category, count, stock, avg_price in categories_stats:
            text += f"\n{category}:\n"
            text += f"  • Товаров: {count}\n"
            text += f"  • На складе: {stock or 0} шт.\n"
            text += f"  • Средняя цена: {avg_price or 0:.2f} сом\n"

        await update.message.reply_text(text, reply_markup=get_admin_keyboard())

    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        await update.message.reply_text(
            f"❌ Ошибка при получении статистики: {e}",
            reply_markup=get_admin_keyboard()
        )
    finally:
        conn.close()


# ==================== ОБРАБОТЧИК СООБЩЕНИЙ ====================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    # Основное меню
    if text == "⬅️ Главное меню":
        await update.message.reply_text("Главное меню:", reply_markup=get_main_keyboard(user_id))

    elif text == "📦 Каталог":
        await show_catalog(update, context)

    elif text == "🛒 Корзина":
        await show_cart(update, context)

    elif text == "📞 Контакты":
        await show_contacts(update, context)

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

    # Категории товаров
    elif text in ["👕 Одежда", "👖 Обувь", "💻 Электроника", "🏠 Для дома", "📦 Все товары"]:
        await show_category_products(update, context)

    # Подкатегории по полу
    elif text in ["👕 Мужское", "👚 Женское", "👶 Детское"]:
        category = context.user_data.get('selected_category')
        if category:
            gender_map = {
                "👕 Мужское": "Мужское",
                "👚 Женское": "Женское",
                "👶 Детское": "Детское"
            }
            gender = gender_map.get(text)

            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, name, price, in_stock, photo, gender 
                FROM products 
                WHERE category=? AND gender=?
                ORDER BY name
            """, (category, gender))
            rows = cursor.fetchall()
            conn.close()

            await display_products(update, context, rows, category, gender)

    # Добавление в корзину
    elif text.startswith("➕ "):
        await add_to_cart(update, context)

    # Корзина
    elif text == "✅ Оформить заказ":
        await checkout(update, context)

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


# ==================== ОТМЕНА ДИАЛОГА ====================
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text(
        "Операция отменена.",
        reply_markup=get_admin_keyboard() if is_admin(user_id) else get_main_keyboard(user_id)
    )
    return ConversationHandler.END


# ==================== ГЛАВНАЯ ФУНКЦИЯ ====================
def main():
    # Инициализация базы данных
    init_db()

    # Создаем приложение
    TOKEN = os.getenv("BOT_TOKEN")
    application = Application.builder().token(TOKEN).build()

    # Добавляем обработчики команд
    application.add_handler(CommandHandler("start", start))

    # Обработчик для добавления товара
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

    # Обработчик для редактирования товара
    edit_product_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Text("✏️ Редактировать товар"), edit_product_start)],
        states={
            EDIT_CHOOSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_product_choose)],
            EDIT_FIELD: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_product_field)],
            EDIT_VALUE: [MessageHandler(filters.TEXT | filters.PHOTO, edit_product_save)],
        },
        fallbacks=[MessageHandler(filters.Text("⬅️ Назад"), cancel)],
    )

    # Обработчик для удаления товара
    delete_product_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Text("❌ Удалить товар"), delete_product)],
        states={
            DELETE_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_product_confirm)],
        },
        fallbacks=[MessageHandler(filters.Text("⬅️ Отмена"), cancel)],
    )

    # Добавляем ConversationHandler в приложение
    application.add_handler(add_product_conv)
    application.add_handler(edit_product_conv)
    application.add_handler(delete_product_conv)

    # Обработчик текстовых сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Запускаем бота
    print("✅ Бот запущен!")
    print(f"👑 Администраторы: {ADMIN_IDS}")
    print("🛍️ Магазин готов к работе...")
    application.run_polling()


if __name__ == '__main__':
    main()