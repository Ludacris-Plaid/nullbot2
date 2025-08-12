import os
import json
import asyncio
import requests
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
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

ADMIN_USER_ID = 7260656020  # Only this user can access admin

CATEGORIES_FILE = "categories.json"
ITEMS_FILE = "items.json"

def load_json(filepath, default):
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            return json.load(f)
    else:
        return default

def save_json(filepath, data):
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)

# Load or initialize data
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
    "item5": {"name": "Malware Masterclass", "price_btc": 0.0005, "file_path": "items/malware.mp4"},
    "item6": {"name": "Phantom Phishing Manual", "price_btc": 0.00025, "file_path": "items/phishing.pdf"},
    "item7": {"name": "Ghost Scripts Collection", "price_btc": 0.0004, "file_path": "items/ghostscripts.zip"},
    "item8": {"name": "Shadow Pages Vol.1", "price_btc": 0.00012, "file_path": "items/shadowpages.pdf"},
    "item9": {"name": "Underground Hacking Tips", "price_btc": 0.00035, "file_path": "items/hacktips.pdf"},
    "item10": {"name": "Black Market Blueprints", "price_btc": 0.0006, "file_path": "items/blueprints.pdf"},
})

# Conversation states for admin
(
    ADMIN_MENU,
    CATEGORY_MENU,
    ADD_CATEGORY,
    EDIT_CATEGORY_SELECT,
    EDIT_CATEGORY_NEW_NAME,
    ITEM_MENU,
    ADD_ITEM_WAITING_KEY,
    ADD_ITEM_WAITING_NAME,
    ADD_ITEM_WAITING_PRICE,
    ADD_ITEM_WAITING_PATH,
    ADD_ITEM_WAITING_CATEGORY,
    EDIT_ITEM_SELECT,
    EDIT_ITEM_FIELD,
    EDIT_ITEM_NEW_VALUE,
) = range(14)

def is_admin(update: Update) -> bool:
    user = update.effective_user
    return user and user.id == ADMIN_USER_ID

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
            headers = {'Authorization': BLOCKONOMICS_API_KEY}
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
        headers = {'Authorization': BLOCKONOMICS_API_KEY}
        response = requests.post(
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

# --------------- ADMIN UI -------------------

async def admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("You’re not admin, get lost.")
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("Manage Categories", callback_data="admin_manage_categories")],
        [InlineKeyboardButton("Manage Items", callback_data="admin_manage_items")],
        [InlineKeyboardButton("Exit Admin", callback_data="admin_exit")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Admin menu:", reply_markup=reply_markup)
    return ADMIN_MENU

async def admin_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "admin_manage_categories":
        # List categories with options to add or edit
        keyboard = [
            [InlineKeyboardButton(name.title(), callback_data=f"edit_cat_{key}")]
            for key, name in zip(CATEGORIES.keys(), ["Cards", "Tutorials", "Pages"])
        ]
        keyboard.append([InlineKeyboardButton("Add New Category", callback_data="add_category")])
        keyboard.append([InlineKeyboardButton("Back to Admin Menu", callback_data="admin_back")])
        await query.message.edit_text("Categories:", reply_markup=InlineKeyboardMarkup(keyboard))
        return CATEGORY_MENU

    elif data == "admin_manage_items":
        # List items with edit option
        keyboard = [
            [InlineKeyboardButton(item['name'], callback_data=f"edit_item_{key}")]
            for key, item in ITEMS.items()
        ]
        keyboard.append([InlineKeyboardButton("Add New Item", callback_data="add_item")])
        keyboard.append([InlineKeyboardButton("Back to Admin Menu", callback_data="admin_back")])
        await query.message.edit_text("Items:", reply_markup=InlineKeyboardMarkup(keyboard))
        return ITEM_MENU

    elif data == "admin_exit":
        await query.message.edit_text("Exiting admin mode.")
        return ConversationHandler.END

    elif data == "admin_back":
        return await admin_start(update, context)

    return ADMIN_MENU

# --- Category add/edit ---

async def category_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "add_category":
        await query.message.edit_text("Send me the new category key (lowercase, no spaces):")
        return ADD_CATEGORY

    elif data.startswith("edit_cat_"):
        cat_key = data[9:]
        context.user_data['edit_cat_key'] = cat_key
        await query.message.edit_text(f"Send me the new name for category '{cat_key}':")
        return EDIT_CATEGORY_NEW_NAME

    elif data == "admin_back":
        return await admin_start(update, context)

    return CATEGORY_MENU

async def add_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cat_key = update.message.text.strip().lower()
    if cat_key in CATEGORIES:
        await update.message.reply_text("Category already exists, asshole.")
        return ADD_CATEGORY

    CATEGORIES[cat_key] = []
    save_json(CATEGORIES_FILE, CATEGORIES)
    await update.message.reply_text(f"Category '{cat_key}' added.")
    return await admin_start(update, context)

async def edit_category_new_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_name = update.message.text.strip()
    cat_key = context.user_data.get('edit_cat_key')
    if not cat_key:
        await update.message.reply_text("Something went wrong, no category key.")
        return ConversationHandler.END

    # Rename category key? We'll just change display names by key for simplicity
    # (You can implement mapping for display names if needed)
    # For now, no real rename, just notify admin.
    await update.message.reply_text(f"Category '{cat_key}' name updated to '{new_name}' (not implemented rename key).")
    return await admin_start(update, context)

# --- Item add/edit ---

async def item_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "add_item":
        await query.message.edit_text("Send me the new item key (lowercase, no spaces):")
        return ADD_ITEM_WAITING_KEY

    elif data.startswith("edit_item_"):
        item_key = data[10:]
        context.user_data['edit_item_key'] = item_key

        item = ITEMS.get(item_key)
        if not item:
            await query.message.reply_text("Item not found.")
            return await admin_start(update, context)

        keyboard = [
            [InlineKeyboardButton("Edit Name", callback_data="edit_field_name")],
            [InlineKeyboardButton("Edit Price", callback_data="edit_field_price")],
            [InlineKeyboardButton("Edit File Path", callback_data="edit_field_path")],
            [InlineKeyboardButton("Edit Category", callback_data="edit_field_category")],
            [InlineKeyboardButton("Back to Items", callback_data="admin_manage_items")]
        ]
        await query.message.edit_text(
            f"Editing item '{item['name']}': Choose field to edit.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return EDIT_ITEM_FIELD

    elif data == "admin_back":
        return await admin_start(update, context)

    return ITEM_MENU

async def add_item_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = update.message.text.strip().lower()
    if key in ITEMS:
        await update.message.reply_text("Item key already exists.")
        return ADD_ITEM_WAITING_KEY
    context.user_data['new_item_key'] = key
    await update.message.reply_text("Send me the item name:")
    return ADD_ITEM_WAITING_NAME

async def add_item_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    context.user_data['new_item_name'] = name
    await update.message.reply_text("Send me the price in BTC (e.g., 0.0001):")
    return ADD_ITEM_WAITING_PRICE

async def add_item_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = float(update.message.text.strip())
        context.user_data['new_item_price'] = price
        await update.message.reply_text("Send me the file path (relative to bot root):")
        return ADD_ITEM_WAITING_PATH
    except ValueError:
        await update.message.reply_text("Invalid price, try again:")
        return ADD_ITEM_WAITING_PRICE

async def add_item_path(update: Update, context: ContextTypes.DEFAULT_TYPE):
    path = update.message.text.strip()
    context.user_data['new_item_path'] = path

    # Choose category
    keyboard = [
        [InlineKeyboardButton(name.title(), callback_data=f"catselect_{key}")]
        for key, name in zip(CATEGORIES.keys(), ["Cards", "Tutorials", "Pages"])
    ]
    await update.message.reply_text("Select a category for the item:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ADD_ITEM_WAITING_CATEGORY

async def add_item_category_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cat_key = query.data[10:]

    key = context.user_data.get('new_item_key')
    name = context.user_data.get('new_item_name')
    price = context.user_data.get('new_item_price')
    path = context.user_data.get('new_item_path')

    if not all([key, name, price, path]):
        await query.message.reply_text("Missing item data, aborting.")
        return await admin_start(update, context)

    # Save item
    ITEMS[key] = {
        "name": name,
        "price_btc": price,
        "file_path": path
    }
    if cat_key not in CATEGORIES:
        CATEGORIES[cat_key] = []
    CATEGORIES[cat_key].append(key)

    save_json(ITEMS_FILE, ITEMS)
    save_json(CATEGORIES_FILE, CATEGORIES)

    await query.message.reply_text(f"Item '{name}' added under category '{cat_key}'.")
    return await admin_start(update, context)

async def edit_item_field_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    field = query.data[11:]
    context.user_data['edit_field'] = field

    await query.message.edit_text(f"Send me the new value for {field}:")
    return EDIT_ITEM_NEW_VALUE

async def edit_item_new_value_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_val = update.message.text.strip()
    field = context.user_data.get('edit_field')
    item_key = context.user_data.get('edit_item_key')

    if not item_key or not field:
        await update.message.reply_text("Missing context info, aborting.")
        return await admin_start(update, context)

    item = ITEMS.get(item_key)
    if not item:
        await update.message.reply_text("Item not found.")
        return await admin_start(update, context)

    # Cast price to float
    if field == "price":
        try:
            new_val = float(new_val)
        except ValueError:
            await update.message.reply_text("Invalid price format.")
            return EDIT_ITEM_NEW_VALUE

    item[field] = new_val
    save_json(ITEMS_FILE, ITEMS)

    await update.message.reply_text(f"Item '{item_key}' {field} updated.")
    return await admin_start(update, context)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("confirm", confirm_payment))
    app.add_handler(CallbackQueryHandler(button_callback, pattern="^(cat_|back_to_categories|item)"))

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("admin", admin_start)],
        states={
            ADMIN_MENU: [CallbackQueryHandler(admin_menu_handler, pattern="^admin_")],
            CATEGORY_MENU: [CallbackQueryHandler(category_menu_handler, pattern="^(add_category|edit_cat_|admin_back)$")],
            ADD_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_category)],
            EDIT_CATEGORY_NEW_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_category_new_name)],
            ITEM_MENU: [CallbackQueryHandler(item_menu_handler, pattern="^(add_item|edit_item_|admin_back)$")],
            ADD_ITEM_WAITING_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_item_key)],
            ADD_ITEM_WAITING_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_item_name)],
            ADD_ITEM_WAITING_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_item_price)],
            ADD_ITEM_WAITING_PATH: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_item_path)],
            ADD_ITEM_WAITING_CATEGORY: [CallbackQueryHandler(add_item_category_handler, pattern="^catselect_")],
            EDIT_ITEM_FIELD: [CallbackQueryHandler(edit_item_field_handler, pattern="^edit_field_")],
            EDIT_ITEM_NEW_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_item_new_value_handler)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(conv_handler)

    if os.environ.get("RENDER"):
        port = int(os.environ.get("PORT", 5000))
        webhook_url = f"https://{os.environ['RENDER_EXTERNAL_HOSTNAME']}/{TELEGRAM_TOKEN}"
        app.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=TELEGRAM_TOKEN,
            webhook_url=webhook_url,
        )
    else:
        app.run_polling()

if __name__ == "__main__":
    main()
