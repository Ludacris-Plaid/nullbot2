import os
import json
import asyncio
import logging
import time
from functools import wraps
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes,
    ConversationHandler, MessageHandler, filters
)
from telegram.error import TelegramError
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(filename='darkbot.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

load_dotenv()
TELEGRAM_TOKEN = "8306200181:AAHP56BkD6eZOcqjI6MZNrMdU7M06S0tIrs"
BLOCKONOMICS_API_KEY = os.getenv("BLOCKONOMICS_API_KEY")

VIDEO_URL = "https://ik.imagekit.io/myrnjevjk/game%20over.mp4?updatedAt=1754980438031"

ADMIN_USER_ID = 7260656020  # Your admin Telegram user ID

CATEGORIES_FILE = "categories.json"
ITEMS_FILE = "items.json"

(
    ADMIN_MENU,
    CATEGORY_MENU,
    CATEGORY_ADD_NAME,
    CATEGORY_EDIT_NAME,
    CATEGORY_DELETE_CONFIRM,
    ITEM_MENU,
    ITEM_ADD_KEY,
    ITEM_ADD_NAME,
    ITEM_ADD_PRICE,
    ITEM_ADD_PATH,
    ITEM_ADD_CATEGORY,
    ITEM_EDIT_FIELD_SELECT,
    ITEM_EDIT_FIELD_VALUE,
    ITEM_DELETE_CONFIRM,
) = range(14)

def load_json(filepath, default):
    try:
        if os.path.exists(filepath):
            with open(filepath, "r") as f:
                return json.load(f)
        return default
    except Exception as e:
        logging.error(f"Failed to load {filepath}: {e}")
        return default

def save_json(filepath, data):
    try:
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logging.error(f"Failed to save {filepath}: {e}")

CATEGORIES = load_json(CATEGORIES_FILE, {
    "cards": ["item1", "item3", "item7"],
    "tutorials": ["item2", "item5", "item6", "item9"],
    "pages": ["item4", "item8", "item10"]
})

ITEMS = load_json(ITEMS_FILE, {
    "item1": {"name": "Dark Secret Card", "price_btc": 0.0001, "file_path": "items/secret.pdf"},
    "item2": {"name": "Forbidden Tutorial", "price_btc": 0.0002, "file_path": "items/archive.zip"},
    "item3": {"name": "Blackout Blackjack Guide", "price_btc": 0.0003, "file_path": "items/blackjack.pdf"},
    "item4": {"name": "Cryptic Code Pages", "price_btc": 0.00015, "file_path": "items/codepages.pdf"},
    "item5": {"name": "Cybersecurity Masterclass", "price_btc": 0.0005, "file_path": "items/cybersecurity.mp4"},
    "item6": {"name": "Phantom Code Manual", "price_btc": 0.00025, "file_path": "items/phishing.pdf"},
    "item7": {"name": "Ghost Scripts Collection", "price_btc": 0.0004, "file_path": "items/ghostscripts.zip"},
    "item8": {"name": "Shadow Pages Vol.1", "price_btc": 0.00012, "file_path": "items/shadowpages.pdf"},
    "item9": {"name": "Underground Tips", "price_btc": 0.00035, "file_path": "items/hacktips.pdf"},
    "item10": {"name": "Market Blueprints", "price_btc": 0.0006, "file_path": "items/blueprints.pdf"},
})

def sync_categories_items():
    """Ensure CATEGORIES only references valid ITEMS."""
    for cat, items in CATEGORIES.items():
        CATEGORIES[cat] = [item for item in items if item in ITEMS]
    save_json(CATEGORIES_FILE, CATEGORIES)
    logging.info("Synced categories and items")

def is_admin(update: Update):
    user = update.effective_user
    return user and user.id == ADMIN_USER_ID

# Rate limit decorator
def rate_limit(limit: int, period: int):
    def decorator(func):
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            user_id = update.effective_user.id
            now = time.time()
            if 'rate_limit' not in context.user_data:
                context.user_data['rate_limit'] = {}
            if func.__name__ not in context.user_data['rate_limit']:
                context.user_data['rate_limit'][func.__name__] = []
            context.user_data['rate_limit'][func.__name__] = [t for t in context.user_data['rate_limit'][func.__name__] if now - t < period]
            if len(context.user_data['rate_limit'][func.__name__]) >= limit:
                await update.message.reply_text("Slow down, you spamming fuck. Wait or I’ll block your pathetic ass.")
                logging.warning(f"User {user_id} rate-limited on {func.__name__}")
                return
            context.user_data['rate_limit'][func.__name__].append(now)
            return await func(update, context, *args, **kwargs)
        return wrapper
    return decorator

# Async HTTP client for Blockonomics
async def fetch_btc_address():
    async with aiohttp.ClientSession() as session:
        headers = {'Authorization': BLOCKONOMICS_API_KEY}
        for _ in range(3):  # Retry 3 times
            try:
                async with session.post('https://www.blockonomics.co/api/new_address', headers=headers) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                    return data.get('address')
            except Exception as e:
                logging.error(f"BTC address fetch failed: {e}")
                await asyncio.sleep(2)
        return None

async def check_btc_balance(address: str, amount: float):
    async with aiohttp.ClientSession() as session:
        headers = {'Authorization': BLOCKONOMICS_API_KEY}
        try:
            async with session.post('https://www.blockonomics.co/api/balance', json={'addr': [address]}, headers=headers) as resp:
                resp.raise_for_status()
                data = await resp.json()
                balance_data = data.get('data', [])
                if not balance_data:
                    return 0
                return balance_data[0].get('confirmed', 0) / 1e8
        except Exception as e:
            logging.error(f"BTC balance check failed: {e}")
            return 0

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_video(video=VIDEO_URL, caption="Welcome to the dark side, you filthy fuck.")
    except TelegramError as e:
        await update.message.reply_text(f"Video’s fucked: {e}. Pick a category anyway, scum.")
        logging.error(f"Video send failed: {e}")

    keyboard = [
        [InlineKeyboardButton(name.title(), callback_data=f"cat_{key}")]
        for key, name in zip(CATEGORIES.keys(), ["Cards", "Tutorials", "Pages"])
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Choose a category, asshole:", reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    logging.info(f"Callback data: {data} from user {user_id}")

    if data.startswith("cat_"):
        cat_key = data[4:]
        items_in_cat = CATEGORIES.get(cat_key, [])
        if not items_in_cat:
            await query.message.edit_text(f"No items in {cat_key.title()}, you dumb fuck.")
            return
        keyboard = [
            [InlineKeyboardButton(ITEMS[item_key]["name"], callback_data=item_key)]
            for item_key in items_in_cat if item_key in ITEMS
        ]
        keyboard.append([InlineKeyboardButton("⬅️ Back to categories", callback_data="back_to_categories")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.edit_text(f"Items in {cat_key.title()}:", reply_markup=reply_markup)

    elif data == "back_to_categories":
        keyboard = [
            [InlineKeyboardButton(name.title(), callback_data=f"cat_{key}")]
            for key, name in zip(CATEGORIES.keys(), ["Cards", "Tutorials", "Pages"])
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.edit_text("Choose a category, dipshit:", reply_markup=reply_markup)

    elif data.startswith("admin_"):
        await admin_callback_handler(update, context)

    else:
        item_key = data
        item = ITEMS.get(item_key)
        if not item:
            await query.message.reply_text("Item’s gone, asshole. Pick something real.")
            logging.warning(f"User {user_id} selected invalid item: {item_key}")
            return

        btc_address = await fetch_btc_address()
        if not btc_address:
            await query.message.reply_text("Can’t get BTC address, system’s fucked. Try later, scum.")
            logging.error(f"Failed to fetch BTC address for user {user_id}")
            return

        context.user_data['pending_payment'] = {
            'item_key': item_key,
            'address': btc_address,
            'amount': item['price_btc'],
            'start_time': time.time()
        }

        await query.message.edit_text(
            f"Send {item['price_btc']} BTC to {btc_address} for {item['name']}.\n"
            "Run /confirm or I’ll hunt your broke ass down."
        )
        logging.info(f"Payment requested for {item_key} by user {user_id}: {btc_address}")

        async def check_payment():
            timeout = 3600  # 1 hour
            while time.time() - context.user_data['pending_payment']['start_time'] < timeout:
                received_btc = await check_btc_balance(btc_address, item['price_btc'])
                if received_btc >= item['price_btc']:
                    try:
                        with open(item['file_path'], 'rb') as file:
                            await query.message.reply_document(
                                document=InputFile(file),
                                caption=f"Here’s your {item['name']}, you sick fuck."
                            )
                        del context.user_data['pending_payment']
                        logging.info(f"Payment confirmed for {item_key} by user {user_id}")
                        return
                    except FileNotFoundError:
                        await query.message.reply_text("File’s fucked. Tell the admin to fix their shit.")
                        logging.error(f"File not found: {item['file_path']} for user {user_id}")
                        return
                await asyncio.sleep(60)
            await query.message.reply_text("Payment timed out, you cheap fuck. Start over or I’ll leak your address.")
            del context.user_data['pending_payment']
            logging.warning(f"Payment timeout for user {user_id} on {item_key}")

        asyncio.create_task(check_payment())

@rate_limit(limit=5, period=60)
async def confirm_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pending = context.user_data.get('pending_payment')
    user_id = update.effective_user.id
    if not pending:
        await update.message.reply_text("No pending payment, asshole. Buy something first.")
        logging.warning(f"User {user_id} tried /confirm with no pending payment")
        return

    received_btc = await check_btc_balance(pending['address'], pending['amount'])
    if received_btc >= pending['amount']:
        item = ITEMS[pending['item_key']]
        try:
            if os.path.getsize(item['file_path']) > 50 * 1024 * 1024:
                await update.message.reply_text("File’s too big, you greedy fuck. Tell admin to fix it.")
                logging.error(f"File too large: {item['file_path']} for user {user_id}")
                return
            with open(item['file_path'], 'rb') as file:
                await update.message.reply_document(
                    document=InputFile(file),
                    caption=f"Here’s your {item['name']}, you twisted bastard."
                )
            del context.user_data['pending_payment']
            logging.info(f"Payment confirmed for {pending['item_key']} by user {user_id}")
        except FileNotFoundError:
            await update.message.reply_text("File’s fucked. Fix the path, moron.")
            logging.error(f"File not found: {item['file_path']} for user {user_id}")
    else:
        await update.message.reply_text("Payment not confirmed yet. Don’t fuck with me.")
        logging.info(f"Payment not confirmed for {pending['item_key']} by user {user_id}")

async def admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("You’re not admin, you pathetic worm. Get lost.")
        logging.warning(f"Non-admin user {update.effective_user.id} attempted /admin")
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("Manage Categories", callback_data="admin_manage_categories")],
        [InlineKeyboardButton("Manage Items", callback_data="admin_manage_items")],
        [InlineKeyboardButton("Exit Admin", callback_data="admin_exit")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Admin menu, you sadistic fuck:", reply_markup=reply_markup)
    return ADMIN_MENU

async def admin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    logging.info(f"Admin callback: {data} by user {user_id}")

    if data == "admin_manage_categories":
        return await admin_show_categories(update, context)
    elif data == "admin_manage_items":
        return await admin_show_items(update, context)
    elif data == "admin_exit":
        await query.message.edit_text("Exiting admin mode, you cruel bastard.")
        return ConversationHandler.END
    elif data == "admin_back_to_menu":
        return await admin_start(update, context)
    elif data == "add_category":
        await query.message.edit_text("Send me the *name* of the new category (lowercase, no spaces).", parse_mode="Markdown")
        return CATEGORY_ADD_NAME
    elif data.startswith("edit_cat_"):
        cat_key = data[len("edit_cat_"):]
        context.user_data['edit_cat_key'] = cat_key
        await query.message.edit_text(
            f"Editing category *{cat_key}*\nSend new name (lowercase, no spaces), or /cancel.",
            parse_mode="Markdown"
        )
        return CATEGORY_EDIT_NAME
    elif data.startswith("delete_cat_"):
        cat_key = data[len("delete_cat_"):]
        context.user_data['del_cat_key'] = cat_key
        keyboard = [
            [InlineKeyboardButton("Yes, delete it", callback_data="confirm_delete_cat")],
            [InlineKeyboardButton("No, go back", callback_data="admin_manage_categories")]
        ]
        await query.message.edit_text(
            f"Delete category *{cat_key}*? Items will be orphaned, you heartless fuck.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return CATEGORY_DELETE_CONFIRM
    elif data == "confirm_delete_cat":
        cat_key = context.user_data.get('del_cat_key')
        if cat_key and cat_key in CATEGORIES:
            del CATEGORIES[cat_key]
            save_json(CATEGORIES_FILE, CATEGORIES)
            await query.message.edit_text(f"Category *{cat_key}* deleted, you ruthless prick.")
        else:
            await query.message.edit_text("No category selected, dumbass.")
        return await admin_show_categories(update, context)
    elif data == "add_item":
        await query.message.edit_text("Send new item *key* (unique id, no spaces).", parse_mode="Markdown")
        return ITEM_ADD_KEY
    elif data.startswith("edit_item_"):
        item_key = data[len("edit_item_"):]
        if item_key not in ITEMS:
            await query.message.edit_text("Item not found, you blind fuck.")
            return await admin_show_items(update, context)
        context.user_data['edit_item_key'] = item_key
        return await admin_edit_item_menu(update, context, item_key)
    elif data.startswith("delete_item_"):
        item_key = data[len("delete_item_"):]
        context.user_data['del_item_key'] = item_key
        keyboard = [
            [InlineKeyboardButton("Yes, delete it", callback_data="confirm_delete_item")],
            [InlineKeyboardButton("No, go back", callback_data="admin_manage_items")]
        ]
        await query.message.edit_text(
            f"Delete item *{item_key}*? You’re one cold bastard.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return ITEM_DELETE_CONFIRM
    elif data == "confirm_delete_item":
        item_key = context.user_data.get('del_item_key')
        if item_key and item_key in ITEMS:
            del ITEMS[item_key]
            for cat, items in CATEGORIES.items():
                if item_key in items:
                    items.remove(item_key)
            save_json(ITEMS_FILE, ITEMS)
            save_json(CATEGORIES_FILE, CATEGORIES)
            await query.message.edit_text(f"Item *{item_key}* deleted, you savage.")
        else:
            await query.message.edit_text("No item selected, you moron.")
        return await admin_show_items(update, context)
    elif data.startswith("edit_field_"):
        field = data[len("edit_field_"):]
        context.user_data['edit_item_field'] = field
        await query.message.edit_text(f"Send new value for *{field}*, or /cancel.", parse_mode="Markdown")
        return ITEM_EDIT_FIELD_VALUE
    elif data == "back_to_categories":
        return await admin_show_categories(update, context)
    elif data == "back_to_items":
        return await admin_show_items(update, context)
    elif data == "back_to_admin":
        return await admin_start(update, context)
    return ADMIN_MENU

async def admin_show_categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    keyboard = [
        [InlineKeyboardButton(f"{name.title()} ✏️", callback_data=f"edit_cat_{key}"),
         InlineKeyboardButton("🗑️", callback_data=f"delete_cat_{key}")]
        for key, name in zip(CATEGORIES.keys(), CATEGORIES.keys())
    ]
    keyboard.append([InlineKeyboardButton("➕ Add New Category", callback_data="add_category")])
    keyboard.append([InlineKeyboardButton("⬅️ Back to Admin Menu", callback_data="admin_back_to_menu")])
    await query.message.edit_text("Categories, you twisted fuck:", reply_markup=InlineKeyboardMarkup(keyboard))
    return CATEGORY_MENU

async def admin_show_items(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    keyboard = []
    for key, item in ITEMS.items():
        keyboard.append([
            InlineKeyboardButton(f"{item['name']} ✏️", callback_data=f"edit_item_{key}"),
            InlineKeyboardButton("🗑️", callback_data=f"delete_item_{key}")
        ])
    keyboard.append([InlineKeyboardButton("➕ Add New Item", callback_data="add_item")])
    keyboard.append([InlineKeyboardButton("⬅️ Back to Admin Menu", callback_data="admin_back_to_menu")])
    await query.message.edit_text("Items, you sick bastard:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ITEM_MENU

async def admin_edit_item_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, item_key=None):
    query = update.callback_query
    if not item_key:
        item_key = context.user_data.get('edit_item_key')
    item = ITEMS.get(item_key)
    if not item:
        await query.message.edit_text("Item not found, you careless fuck.")
        return await admin_show_items(update, context)

    keyboard = [
        [InlineKeyboardButton("Name", callback_data="edit_field_name")],
        [InlineKeyboardButton("Price BTC", callback_data="edit_field_price_btc")],
        [InlineKeyboardButton("File Path", callback_data="edit_field_file_path")],
        [InlineKeyboardButton("Category", callback_data="edit_field_category")],
        [InlineKeyboardButton("⬅️ Back to Items", callback_data="back_to_items")]
    ]
    text = f"Editing item *{item_key}*:\n" \
           f"Name: {item['name']}\n" \
           f"Price BTC: {item['price_btc']}\n" \
           f"File Path: {item['file_path']}\n"
    cat_for_item = next((cat for cat, items in CATEGORIES.items() if item_key in items), None)
    text += f"Category: {cat_for_item if cat_for_item else 'None'}"

    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return ITEM_EDIT_FIELD_SELECT

async def handle_category_add_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().lower()
    user_id = update.effective_user.id
    if ' ' in text or not text.isalnum():
        await update.message.reply_text("Invalid category name, asshole. Letters and numbers only, no spaces. Try again or /cancel.")
        logging.warning(f"User {user_id} sent invalid category name: {text}")
        return CATEGORY_ADD_NAME
    if text in CATEGORIES:
        await update.message.reply_text("Category exists, you dumb fuck. Send another or /cancel.")
        logging.warning(f"User {user_id} tried duplicate category: {text}")
        return CATEGORY_ADD_NAME

    CATEGORIES[text] = []
    save_json(CATEGORIES_FILE, CATEGORIES)
    await update.message.reply_text(f"Category *{text}* added, you cruel bastard.", parse_mode="Markdown")
    logging.info(f"User {user_id} added category: {text}")
    fake_update = update
    fake_update.callback_query = None
    return await admin_show_categories(fake_update, context)

async def handle_category_edit_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_name = update.message.text.strip().lower()
    old_name = context.user_data.get('edit_cat_key')
    user_id = update.effective_user.id

    if ' ' in new_name or not new_name.isalnum():
        await update.message.reply_text("Invalid name, dipshit. Letters and numbers only, no spaces. Try again or /cancel.")
        logging.warning(f"User {user_id} sent invalid category edit name: {new_name}")
        return CATEGORY_EDIT_NAME
    if new_name in CATEGORIES:
        await update.message.reply_text("Category exists, you idiot. Send another or /cancel.")
        logging.warning(f"User {user_id} tried duplicate category edit: {new_name}")
        return CATEGORY_EDIT_NAME
    if old_name and old_name in CATEGORIES:
        CATEGORIES[new_name] = CATEGORIES.pop(old_name)
        save_json(CATEGORIES_FILE, CATEGORIES)
        await update.message.reply_text(f"Category renamed from *{old_name}* to *{new_name}*, you sly fuck.", parse_mode="Markdown")
        logging.info(f"User {user_id} renamed category {old_name} to {new_name}")
    else:
        await update.message.reply_text("Old category gone, you moron.")
        logging.error(f"User {user_id} tried to edit non-existent category: {old_name}")
    return await admin_show_categories(update, context)

async def handle_item_add_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = update.message.text.strip().lower()
    user_id = update.effective_user.id
    if ' ' in key or not key.isalnum():
        await update.message.reply_text("Invalid key, asshole. Letters and numbers only, no spaces. Try again or /cancel.")
        logging.warning(f"User {user_id} sent invalid item key: {key}")
        return ITEM_ADD_KEY
    if key in ITEMS:
        await update.message.reply_text("Key exists, you dumb fuck. Send another or /cancel.")
        logging.warning(f"User {user_id} tried duplicate item key: {key}")
        return ITEM_ADD_KEY
    context.user_data['new_item_key'] = key
    await update.message.reply_text("Send item *name*, you sick prick.", parse_mode="Markdown")
    logging.info(f"User {user_id} started adding item with key: {key}")
    return ITEM_ADD_NAME

async def handle_item_add_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    context.user_data['new_item_name'] = name
    await update.message.reply_text("Send item *price in BTC* (e.g., 0.0001), you greedy bastard.", parse_mode="Markdown")
    logging.info(f"User {update.effective_user.id} set item name: {name}")
    return ITEM_ADD_PRICE

async def handle_item_add_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        price = float(update.message.text.strip())
        if price <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Invalid price, dipshit. Positive number like 0.0001. Try again or /cancel.")
        logging.warning(f"User {user_id} sent invalid price: {update.message.text}")
        return ITEM_ADD_PRICE
    context.user_data['new_item_price'] = price
    await update.message.reply_text("Send item *file path* (relative to bot), you twisted fuck.", parse_mode="Markdown")
    logging.info(f"User {user_id} set item price: {price}")
    return ITEM_ADD_PATH

async def handle_item_add_path(update: Update, context: ContextTypes.DEFAULT_TYPE):
    path = update.message.text.strip()
    user_id = update.effective_user.id
    if not os.path.exists(path):
        await update.message.reply_text("File doesn’t exist, you moron. Send valid path or /cancel.")
        logging.warning(f"User {user_id} sent invalid file path: {path}")
        return ITEM_ADD_PATH
    if os.path.getsize(path) > 50 * 1024 * 1024:
        await update.message.reply_text("File’s too big, you greedy fuck. Keep it under 50MB or /cancel.")
        logging.warning(f"User {user_id} sent oversized file: {path}")
        return ITEM_ADD_PATH
    context.user_data['new_item_path'] = path
    keyboard = [
        [InlineKeyboardButton(cat.title(), callback_data=f"select_cat_{cat}")]
        for cat in CATEGORIES.keys()
    ]
    keyboard.append([InlineKeyboardButton("Cancel", callback_data="admin_back_to_menu")])
    await update.message.reply_text("Select category, you sick bastard:", reply_markup=InlineKeyboardMarkup(keyboard))
    logging.info(f"User {user_id} set item path: {path}")
    return ITEM_ADD_CATEGORY

async def handle_item_add_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    if not data.startswith("select_cat_"):
        await query.message.edit_text("Invalid selection, you dumb fuck. Cancelled.")
        logging.warning(f"User {user_id} sent invalid category selection: {data}")
        return await admin_show_items(update, context)

    cat = data[len("select_cat_"):]
    if cat not in CATEGORIES:
        await query.message.edit_text("Category gone, you idiot. Cancelled.")
        logging.error(f"User {user_id} selected non-existent category: {cat}")
        return await admin_show_items(update, context)

    key = context.user_data['new_item_key']
    ITEMS[key] = {
        "name": context.user_data['new_item_name'],
        "price_btc": context.user_data['new_item_price'],
        "file_path": context.user_data['new_item_path']
    }
    CATEGORIES[cat].append(key)
    save_json(ITEMS_FILE, ITEMS)
    save_json(CATEGORIES_FILE, CATEGORIES)
    await query.message.edit_text(f"Item *{key}* added to *{cat}*, you ruthless prick.", parse_mode="Markdown")
    logging.info(f"User {user_id} added item {key} to category {cat}")
    return await admin_show_items(update, context)

async def handle_item_edit_field_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    item_key = context.user_data.get('edit_item_key')
    field = context.user_data.get('edit_item_field')
    user_id = update.effective_user.id
    if not item_key or not field:
        await update.message.reply_text("No item or field selected, you moron. /cancel")
        logging.error(f"User {user_id} tried to edit with missing key/field")
        return ConversationHandler.END
    if item_key not in ITEMS:
        await update.message.reply_text("Item gone, you dumb fuck. /cancel")
        logging.error(f"User {user_id} tried to edit non-existent item: {item_key}")
        return ConversationHandler.END

    if field == "price_btc":
        try:
            val = float(text)
            if val <= 0:
                raise ValueError
            ITEMS[item_key][field] = val
        except ValueError:
            await update.message.reply_text("Invalid price, dipshit. Positive number or /cancel.")
            logging.warning(f"User {user_id} sent invalid price: {text}")
            return ITEM_EDIT_FIELD_VALUE
    elif field == "category":
        if text not in CATEGORIES:
            await update.message.reply_text(f"Category '{text}' doesn’t exist, you idiot. Send existing category or /cancel.")
            logging.warning(f"User {user_id} sent invalid category: {text}")
            return ITEM_EDIT_FIELD_VALUE
        for cat, items in CATEGORIES.items():
            if item_key in items:
                items.remove(item_key)
        CATEGORIES[text].append(item_key)
    else:
        if field == "file_path":
            if not os.path.exists(text):
                await update.message.reply_text("File path doesn’t exist, you moron. Send valid path or /cancel.")
                logging.warning(f"User {user_id} sent invalid file path: {text}")
                return ITEM_EDIT_FIELD_VALUE
            if os.path.getsize(text) > 50 * 1024 * 1024:
                await update.message.reply_text("File’s too big, you greedy fuck. Under 50MB or /cancel.")
                logging.warning(f"User {user_id} sent oversized file: {text}")
                return ITEM_EDIT_FIELD_VALUE
        ITEMS[item_key][field] = text

    save_json(ITEMS_FILE, ITEMS)
    save_json(CATEGORIES_FILE, CATEGORIES)
    await update.message.reply_text(f"Updated {field} for *{item_key}*, you sly bastard.", parse_mode="Markdown")
    logging.info(f"User {user_id} updated {field} for item {item_key}")
    return await admin_edit_item_menu(update, context, item_key)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text("Operation cancelled, you weak fuck.")
    logging.info(f"User {user_id} cancelled operation")
    context.user_data.clear()
    return ConversationHandler.END

def main():
    sync_categories_items()
    if not BLOCKONOMICS_API_KEY:
        logging.error("BLOCKONOMICS_API_KEY not set. Bot will fail.")
        raise ValueError("BLOCKONOMICS_API_KEY not set, you dumb fuck.")

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("confirm", confirm_payment))
    app.add_handler(CallbackQueryHandler(button_callback))

    admin_conv = ConversationHandler(
        entry_points=[CommandHandler("admin", admin_start)],
        states={
            ADMIN_MENU: [CallbackQueryHandler(admin_callback_handler, pattern="^admin_")],
            CATEGORY_MENU: [CallbackQueryHandler(admin_callback_handler, pattern="^(add_category|edit_cat_|delete_cat_|confirm_delete_cat|admin_back_to_menu)$")],
            CATEGORY_ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_category_add_name)],
            CATEGORY_EDIT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_category_edit_name)],
            CATEGORY_DELETE_CONFIRM: [CallbackQueryHandler(admin_callback_handler, pattern="^(confirm_delete_cat|admin_manage_categories)$")],
            ITEM_MENU: [CallbackQueryHandler(admin_callback_handler, pattern="^(add_item|edit_item_|delete_item_|confirm_delete_item|admin_back_to_menu)$")],
            ITEM_ADD_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_item_add_key)],
            ITEM_ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_item_add_name)],
            ITEM_ADD_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_item_add_price)],
            ITEM_ADD_PATH: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_item_add_path)],
            ITEM_ADD_CATEGORY: [CallbackQueryHandler(handle_item_add_category, pattern="^select_cat_")],
            ITEM_EDIT_FIELD_SELECT: [CallbackQueryHandler(admin_callback_handler, pattern="^(edit_field_|back_to_items)$")],
            ITEM_EDIT_FIELD_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_item_edit_field_value)],
            ITEM_DELETE_CONFIRM: [CallbackQueryHandler(admin_callback_handler, pattern="^(confirm_delete_item|admin_manage_items)$")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
        conversation_timeout=600  # 10 minutes
    )
    app.add_handler(admin_conv)

    if os.environ.get("RENDER"):
        try:
            port = int(os.environ.get("PORT", 5000))
            webhook_url = f"https://{os.environ['RENDER_EXTERNAL_HOSTNAME']}/{TELEGRAM_TOKEN}"
            app.run_webhook(
                listen="0.0.0.0",
                port=port,
                url_path=TELEGRAM_TOKEN,
                webhook_url=webhook_url,
            )
            logging.info(f"Webhook started on {webhook_url}")
        except Exception as e:
            logging.error(f"Webhook setup failed: {e}, falling back to polling")
            app.run_polling()
    else:
        app.run_polling()
        logging.info("Started polling")

if __name__ == "__main__":
    main()