import os
import json
import asyncio
import requests
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes,
    ConversationHandler, MessageHandler, filters
)
from dotenv import load_dotenv

load_dotenv()
TELEGRAM_TOKEN = "8306200181:AAHP56BkD6eZOcqjI6MZNrMdU7M06S0tIrs"
BLOCKONOMICS_API_KEY = os.getenv("BLOCKONOMICS_API_KEY")

VIDEO_URL = "https://ik.imagekit.io/myrnjevjk/game%20over.mp4?updatedAt=1754980438031"

ADMIN_USERNAME = "therealdysthemix"

CATEGORIES_FILE = "categories.json"
ITEMS_FILE = "items.json"

# Load or initialize categories/items with persistence
def load_json(filepath, default):
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            return json.load(f)
    else:
        return default

def save_json(filepath, data):
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)

CATEGORIES = load_json(CATEGORIES_FILE, {
    "cards": ["item1"],
    "tutorials": ["item2"],
    "pages": []
})

ITEMS = load_json(ITEMS_FILE, {
    "item1": {"name": "Dark Secret Card", "price_btc": 0.0001, "file_path": "items/secret.pdf"},
    "item2": {"name": "Forbidden Tutorial", "price_btc": 0.0002, "file_path": "items/archive.zip"},
})

# Admin conversation states
(
    ADMIN_MENU,
    CATEGORY_MENU,
    ITEM_MENU,
    ADD_CATEGORY,
    ADD_ITEM_WAITING_KEY,
    ADD_ITEM_WAITING_NAME,
    ADD_ITEM_WAITING_PRICE,
    ADD_ITEM_WAITING_PATH,
    ADD_ITEM_WAITING_CATEGORY,
    EDIT_ITEM_SELECT,
    EDIT_ITEM_FIELD,
    EDIT_ITEM_NEW_VALUE,
    EDIT_CATEGORY_SELECT,
    EDIT_CATEGORY_NEW_NAME,
) = range(14)

def is_admin(update: Update) -> bool:
    user = update.effective_user
    return user and user.username == ADMIN_USERNAME

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_video(video=VIDEO_URL, caption="Welcome to the dark side, fucker.")
    except Exception as e:
        await update.message.reply_text(f"Error sending video: {e}")

    keyboard = [
        [InlineKeyboardButton(name.title(), callback_data=f"cat_{key}")]
        for key, name in zip(CATEGORIES.keys(), ["Cards", "Tutorials", "Pages"])
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Choose a category:", reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("cat_"):
        cat_key = data[4:]
        items_in_cat = CATEGORIES.get(cat_key, [])

        if not items_in_cat:
            await query.message.edit_text(f"No items found in {cat_key.title()}, asshole.")
            return

        keyboard = [
            [InlineKeyboardButton(ITEMS[item_key]["name"], callback_data=item_key)]
            for item_key in items_in_cat
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
        await query.message.edit_text("Choose a category:", reply_markup=reply_markup)

    else:
        item_key = data
        item = ITEMS.get(item_key)

        if not item:
            await query.message.reply_text("Item’s gone, asshole. Pick something else.")
            return

        try:
            headers = {'Authorization': f'Bearer {BLOCKONOMICS_API_KEY}'}
            response = requests.post('https://www.blockonomics.co/api/new_address', headers=headers)
            response.raise_for_status()
            btc_address = response.json()['address']
        except Exception as e:
            await update.message.reply_text(f"Failed to get BTC address: {str(e)}. Try again, dipshit.")
            return

        context.user_data['pending_payment'] = {
            'item_key': item_key,
            'address': btc_address,
            'amount': item['price_btc']
        }

        await query.message.edit_text(
            f"Send {item['price_btc']} BTC to {btc_address} for {item['name']}.\n"
            "Run /confirm when you’ve paid, or I’ll know you’re a cheap fuck."
        )

        async def taunt():
            await asyncio.sleep(600)
            if context.user_data.get('pending_payment'):
                await query.message.reply_text("Still no payment? You’re pissing me off, scum.")
        asyncio.create_task(taunt())

async def confirm_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pending = context.user_data.get('pending_payment')
    if not pending:
        await update.message.reply_text("No pending payment, asshole. Buy something first.")
        return

    try:
        address = pending['address']
        headers = {'Authorization': f'Bearer {BLOCKONOMICS_API_KEY}'}
        response = requests.get(
            'https://www.blockonomics.co/api/balance',
            json={'addr': [address]},
            headers=headers
        )
        response.raise_for_status()
        balance_data = response.json()['data'][0]
        received_btc = balance_data['confirmed'] / 1e8

        if received_btc >= pending['amount']:
            item = ITEMS[pending['item_key']]
            try:
                with open(item['file_path'], 'rb') as file:
                    await update.message.reply_document(
                        document=file,
                        caption=f"Here's your {item['name']}. Enjoy, you sick fuck."
                    )
                del context.user_data['pending_payment']
            except FileNotFoundError:
                await update.message.reply_text("File’s fucked. Fix the path, moron.")
        else:
            await update.message.reply_text("Payment not confirmed yet. Don’t fuck with me.")
    except Exception as e:
        await update.message.reply_text(f"Payment check failed: {str(e)}. Try again, dumbass.")

# --------- ADMIN HANDLERS -------------

# Entry point for /admin
async def admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("Fuck off, you’re not authorized.")
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("Manage Categories", callback_data="admin_categories")],
        [InlineKeyboardButton("Manage Items", callback_data="admin_items")],
        [InlineKeyboardButton("Exit", callback_data="admin_exit")],
    ]
    await update.message.reply_text(
        "Admin Panel - Choose an option:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ADMIN_MENU

async def admin_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "admin_exit":
        await query.message.edit_text("Exiting admin panel.")
        return ConversationHandler.END

    elif data == "admin_categories":
        # Show categories with edit and add buttons
        keyboard = [
            [InlineKeyboardButton(key, callback_data=f"edit_cat_{key}")]
            for key in CATEGORIES.keys()
        ]
        keyboard.append([InlineKeyboardButton("➕ Add Category", callback_data="add_category")])
        keyboard.append([InlineKeyboardButton("⬅️ Back to Admin Menu", callback_data="back_to_admin")])
        await query.message.edit_text("Categories:", reply_markup=InlineKeyboardMarkup(keyboard))
        return CATEGORY_MENU

    elif data == "admin_items":
        # Show items with edit and add buttons
        keyboard = [
            [InlineKeyboardButton(f"{item['name']} ({key})", callback_data=f"edit_item_{key}")]
            for key, item in ITEMS.items()
        ]
        keyboard.append([InlineKeyboardButton("➕ Add Item", callback_data="add_item")])
        keyboard.append([InlineKeyboardButton("⬅️ Back to Admin Menu", callback_data="back_to_admin")])
        await query.message.edit_text("Items:", reply_markup=InlineKeyboardMarkup(keyboard))
        return ITEM_MENU

    elif data == "back_to_admin":
        return await admin_start(update, context)

    else:
        await query.message.edit_text("Unknown admin command.")
        return ADMIN_MENU

# --- CATEGORY HANDLERS ---

async def category_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "add_category":
        await query.message.edit_text("Send me the new category key (no spaces):")
        return ADD_CATEGORY

    elif data.startswith("edit_cat_"):
        cat_key = data[len("edit_cat_"):]
        context.user_data['edit_category_key'] = cat_key
        await query.message.edit_text(f"Send me the new display name for category '{cat_key}':")
        return EDIT_CATEGORY_NEW_NAME

    elif data == "back_to_admin":
        return await admin_start(update, context)

    else:
        await query.message.edit_text("Unknown category command.")
        return CATEGORY_MENU

async def add_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cat_key = update.message.text.strip()
    if " " in cat_key or not cat_key.isalnum():
        await update.message.reply_text("Invalid key! Use only letters and numbers, no spaces.")
        return ADD_CATEGORY
    if cat_key in CATEGORIES:
        await update.message.reply_text("Category key already exists. Send a different key:")
        return ADD_CATEGORY
    CATEGORIES[cat_key] = []
    save_json(CATEGORIES_FILE, CATEGORIES)
    await update.message.reply_text(f"Category '{cat_key}' added.")
    return await admin_start(update, context)

async def edit_category_new_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_name = update.message.text.strip()
    cat_key = context.user_data.get('edit_category_key')
    if not cat_key:
        await update.message.reply_text("No category selected.")
        return ConversationHandler.END
    # Note: display names are hardcoded in UI, you can extend this to store display names in JSON
    await update.message.reply_text(f"Category '{cat_key}' display name changed to '{new_name}'. (UI display names are fixed in code.)")
    return await admin_start(update, context)

# --- ITEM HANDLERS ---

async def item_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "add_item":
        await query.message.edit_text("Send me the new item key (no spaces):")
        return ADD_ITEM_WAITING_KEY

    elif data.startswith("edit_item_"):
        item_key = data[len("edit_item_"):]
        if item_key not in ITEMS:
            await query.message.edit_text("Item not found.")
            return ITEM_MENU
        context.user_data['edit_item_key'] = item_key
        keyboard = [
            [InlineKeyboardButton("Name", callback_data="edit_field_name")],
            [InlineKeyboardButton("Price BTC", callback_data="edit_field_price_btc")],
            [InlineKeyboardButton("File Path", callback_data="edit_field_file_path")],
            [InlineKeyboardButton("Category", callback_data="edit_field_category")],
            [InlineKeyboardButton("⬅️ Back to Items", callback_data="back_to_items")],
        ]
        await query.message.edit_text(f"Editing item '{item_key}'. Choose field to edit:", reply_markup=InlineKeyboardMarkup(keyboard))
        return EDIT_ITEM_FIELD

    elif data == "back_to_items":
        return await admin_start(update, context)

    else:
        await query.message.edit_text("Unknown item command.")
        return ITEM_MENU

async def add_item_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = update.message.text.strip()
    if " " in key or not key.isalnum():
        await update.message.reply_text("Invalid key! Use only letters and numbers, no spaces.")
        return ADD_ITEM_WAITING_KEY
    if key in ITEMS:
        await update.message.reply_text("Item key already exists. Send a different key:")
        return ADD_ITEM_WAITING_KEY
    context.user_data['new_item_key'] = key
    await update.message.reply_text("Send me the item display name:")
    return ADD_ITEM_WAITING_NAME

async def add_item_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['new_item_name'] = update.message.text.strip()
    await update.message.reply_text("Send me the price in BTC (e.g. 0.0001):")
    return ADD_ITEM_WAITING_PRICE

async def add_item_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = float(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("Invalid number, try again:")
        return ADD_ITEM_WAITING_PRICE
    context.user_data['new_item_price'] = price
    await update.message.reply_text("Send me the file path (relative to bot folder):")
    return ADD_ITEM_WAITING_PATH

async def add_item_path(update: Update, context: ContextTypes.DEFAULT_TYPE):
    path = update.message.text.strip()
    context.user_data['new_item_path'] = path

    # List categories for user to choose
    keyboard = [
        [InlineKeyboardButton(key, callback_data=f"select_cat_{key}")]
        for key in CATEGORIES.keys()
    ]
    await update.message.reply_text("Select category for this item:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ADD_ITEM_WAITING_CATEGORY

async def add_item_category_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cat_key = query.data[len("select_cat_"):]
    key = context.user_data.get('new_item_key')
    name = context.user_data.get('new_item_name')
    price = context.user_data.get('new_item_price')
    path = context.user_data.get('new_item_path')

    if not all([key, name, price, path]):
        await query.message.edit_text("Missing data, aborting.")
        return ConversationHandler.END

    ITEMS[key] = {
        "name": name,
        "price_btc": price,
        "file_path": path,
    }
    if cat_key not in CATEGORIES:
        CATEGORIES[cat_key] = []
    CATEGORIES[cat_key].append(key)

    save_json(ITEMS_FILE, ITEMS)
    save_json(CATEGORIES_FILE, CATEGORIES)

    await query.message.edit_text(f"Item '{name}' added to category '{cat_key}'.")
    return await admin_start(update, context)

async def edit_item_field_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    field_map = {
        "edit_field_name": "name",
        "edit_field_price_btc": "price_btc",
        "edit_field_file_path": "file_path",
        "edit_field_category": "category",
    }
    field_key = field_map.get(query.data)
    if not field_key:
        await query.message.edit_text("Unknown field.")
        return ITEM_MENU

    context.user_data['edit_field'] = field_key

    if field_key == "category":
        # Show categories to choose from
        keyboard = [
            [InlineKeyboardButton(key, callback_data=f"select_cat_{key}")]
            for key in CATEGORIES.keys()
        ]
        await query.message.edit_text("Select new category:", reply_markup=InlineKeyboardMarkup(keyboard))
        return EDIT_ITEM_NEW_VALUE
    else:
        await query.message.edit_text(f"Send new value for {field_key}:")
        return EDIT_ITEM_NEW_VALUE

async def edit_item_new_value_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    item_key = context.user_data.get('edit_item_key')
    field = context.user_data.get('edit_field')

    if not item_key or not field:
        await update.message.reply_text("Missing data, aborting.")
        return ConversationHandler.END

    if field == "price_btc":
        try:
            value = float(text)
        except ValueError:
            await update.message.reply_text("Invalid number, try again:")
            return EDIT_ITEM_NEW_VALUE
    elif field == "category":
        await update.message.reply_text("Use buttons to select category, not text.")
        return EDIT_ITEM_NEW_VALUE
    else:
        value = text

    ITEMS[item_key][field] = value
    save_json(ITEMS_FILE, ITEMS)
    await update.message.reply_text(f"Item '{item_key}' field '{field}' updated.")
    return await admin_start(update, context)

async def edit_item_new_value_category_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cat_key = query.data[len("select_cat_"):]
    item_key = context.user_data.get('edit_item_key')

    if not item_key:
        await query.message.edit_text("Missing item data, aborting.")
        return ConversationHandler.END

    # Remove from old categories
    for key, items in CATEGORIES.items():
        if item_key in items:
            items.remove(item_key)

    # Add to new category
    if cat_key not in CATEGORIES:
        CATEGORIES[cat_key] = []
    CATEGORIES[cat_key].append(item_key)

    save_json(CATEGORIES_FILE, CATEGORIES)
    await query.message.edit_text(f"Item '{item_key}' moved to category '{cat_key}'.")
    return await admin_start(update, context)

# ------------ Conversation handler setup ------------

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("confirm", confirm_payment))
    app.add_handler(CallbackQueryHandler(button_callback))

    admin_conv = ConversationHandler(
        entry_points=[CommandHandler("admin", admin_start)],
        states={
            ADMIN_MENU: [CallbackQueryHandler(admin_menu_handler)],
            CATEGORY_MENU: [CallbackQueryHandler(category_menu_handler)],
            ADD_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_category)],
            EDIT_CATEGORY_NEW_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_category_new_name)],

            ITEM_MENU: [CallbackQueryHandler(item_menu_handler)],
            ADD_ITEM_WAITING_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_item_key)],
            ADD_ITEM_WAITING_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_item_name)],
            ADD_ITEM_WAITING_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_item_price)],
            ADD_ITEM_WAITING_PATH: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_item_path)],
            ADD_ITEM_WAITING_CATEGORY: [CallbackQueryHandler(add_item_category_handler)],

            EDIT_ITEM_FIELD: [CallbackQueryHandler(edit_item_field_handler)],
            EDIT_ITEM_NEW_VALUE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_item_new_value_handler),
                CallbackQueryHandler(edit_item_new_value_category_handler)
            ],
        },
        fallbacks=[CommandHandler("cancel", lambda update, context: update.message.reply_text("Cancelled.", reply_markup=ReplyKeyboardRemove()) or ConversationHandler.END)],
        allow_reentry=True
    )

    app.add_handler(admin_conv)

    if os.environ.get("RENDER"):
        port = int(os.environ.get("PORT", 5000))
        webhook_url = f"https://{os.environ['RENDER_EXTERNAL_HOSTNAME']}/{TELEGRAM_TOKEN}"
        app.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=TELEGRAM_TOKEN,
            webhook_url=webhook_url
        )
    else:
        app.run_polling()

if __name__ == "__main__":
    main()
