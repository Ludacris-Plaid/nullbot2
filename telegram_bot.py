import os
import json
import asyncio
import requests
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
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

ADMIN_USER_ID = 7260656020  # Your admin Telegram user ID

CATEGORIES_FILE = "categories.json"
ITEMS_FILE = "items.json"

(
    ADMIN_MENU,
    CATEGORY_MENU,
    CATEGORY_ADD_NAME,
    CATEGORY_EDIT_SELECT,
    CATEGORY_EDIT_NAME,
    CATEGORY_DELETE_CONFIRM,

    ITEM_MENU,
    ITEM_ADD_KEY,
    ITEM_ADD_NAME,
    ITEM_ADD_PRICE,
    ITEM_ADD_PATH,
    ITEM_ADD_CATEGORY,
    ITEM_EDIT_SELECT,
    ITEM_EDIT_FIELD_SELECT,
    ITEM_EDIT_FIELD_VALUE,
    ITEM_DELETE_CONFIRM,
) = range(17)

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

def is_admin(update: Update):
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

    print(f"[DEBUG] Callback data received: {data}")

    if data.startswith("cat_"):
        cat_key = data[4:]
        items_in_cat = CATEGORIES.get(cat_key, [])

        if not items_in_cat:
            await query.message.edit_text(f"No items found in {cat_key.title()}, asshole.")
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
        await query.message.edit_text("Choose a category:", reply_markup=reply_markup)

    elif data.startswith("admin_"):
        # Pass to admin handler
        await admin_callback_handler(update, context)

    else:
        # Assume item key
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
            print(f"[DEBUG] BTC Address generated: {btc_address}")
        except Exception as e:
            await query.message.reply_text(f"Failed to get BTC address: {str(e)}. Try again, dipshit.")
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
                        document=InputFile(file),
                        caption=f"Here's your {item['name']}. Enjoy, you sick fuck."
                    )
                del context.user_data['pending_payment']
            except FileNotFoundError:
                await update.message.reply_text("File’s fucked. Fix the path, moron.")
        else:
            await update.message.reply_text("Payment not confirmed yet. Don’t fuck with me.")
    except Exception as e:
        await update.message.reply_text(f"Payment check failed: {str(e)}. Try again, dumbass.")

# -------------- Admin handlers --------------

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

async def admin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "admin_manage_categories":
        return await admin_show_categories(update, context)

    elif data == "admin_manage_items":
        return await admin_show_items(update, context)

    elif data == "admin_exit":
        await query.message.edit_text("Exiting admin mode.")
        return ConversationHandler.END

    elif data == "admin_back_to_menu":
        return await admin_start(update, context)

    # CATEGORY management
    elif data == "add_category":
        await query.message.edit_text("Send me the *name* of the new category (lowercase, no spaces).", parse_mode="Markdown")
        return CATEGORY_ADD_NAME

    elif data.startswith("edit_cat_"):
        cat_key = data[len("edit_cat_"):]
        context.user_data['edit_cat_key'] = cat_key
        await query.message.edit_text(
            f"Editing category *{cat_key}*\n"
            "Send me the new name (lowercase, no spaces), or /cancel.",
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
        await query.message.edit_text(f"Are you sure you want to delete category *{cat_key}*? All items in it will be orphaned.", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return CATEGORY_DELETE_CONFIRM

    elif data == "confirm_delete_cat":
        cat_key = context.user_data.get('del_cat_key')
        if cat_key and cat_key in CATEGORIES:
            del CATEGORIES[cat_key]
            save_json(CATEGORIES_FILE, CATEGORIES)
            # Orphan items remain, you may want to clean them manually or prompt admin later
            await query.message.edit_text(f"Category *{cat_key}* deleted.", parse_mode="Markdown")
        else:
            await query.message.edit_text("No category selected or category does not exist.")
        return await admin_show_categories(update, context)

    # ITEM management
    elif data == "add_item":
        await query.message.edit_text("Send me the new item *key* (unique id, no spaces).", parse_mode="Markdown")
        return ITEM_ADD_KEY

    elif data.startswith("edit_item_"):
        item_key = data[len("edit_item_"):]
        if item_key not in ITEMS:
            await query.message.edit_text("Item not found.")
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
        await query.message.edit_text(f"Are you sure you want to delete item *{item_key}*?", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return ITEM_DELETE_CONFIRM

    elif data == "confirm_delete_item":
        item_key = context.user_data.get('del_item_key')
        if item_key and item_key in ITEMS:
            del ITEMS[item_key]
            # Also remove from categories
            for cat, items in CATEGORIES.items():
                if item_key in items:
                    items.remove(item_key)
            save_json(ITEMS_FILE, ITEMS)
            save_json(CATEGORIES_FILE, CATEGORIES)
            await query.message.edit_text(f"Item *{item_key}* deleted.", parse_mode="Markdown")
        else:
            await query.message.edit_text("No item selected or item does not exist.")
        return await admin_show_items(update, context)

    # ITEM EDIT FIELDS
    elif data.startswith("edit_field_"):
        field = data[len("edit_field_"):]
        context.user_data['edit_item_field'] = field
        await query.message.edit_text(f"Send me the new value for *{field}*, or /cancel.", parse_mode="Markdown")
        return ITEM_EDIT_FIELD_VALUE

    # BACK buttons
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
    await query.message.edit_text("Categories:", reply_markup=InlineKeyboardMarkup(keyboard))
    return CATEGORY_MENU

async def admin_show_items(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    keyboard = []
    for key, item in ITEMS.items():
        keyboard.append([InlineKeyboardButton(f"{item['name']} ✏️", callback_data=f"edit_item_{key}"),
                         InlineKeyboardButton("🗑️", callback_data=f"delete_item_{key}")])
    keyboard.append([InlineKeyboardButton("➕ Add New Item", callback_data="add_item")])
    keyboard.append([InlineKeyboardButton("⬅️ Back to Admin Menu", callback_data="admin_back_to_menu")])
    await query.message.edit_text("Items:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ITEM_MENU

async def admin_edit_item_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, item_key=None):
    query = update.callback_query
    if not item_key:
        item_key = context.user_data.get('edit_item_key')
    item = ITEMS.get(item_key)
    if not item:
        await query.message.edit_text("Item not found.")
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
    # Find category
    cat_for_item = None
    for cat, items in CATEGORIES.items():
        if item_key in items:
            cat_for_item = cat
            break
    text += f"Category: {cat_for_item if cat_for_item else 'None'}"

    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return ITEM_EDIT_FIELD_SELECT

async def handle_category_add_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().lower()
    if ' ' in text or not text.isalnum():
        await update.message.reply_text("Invalid category name. Use only letters and numbers, no spaces. Send again or /cancel.")
        return CATEGORY_ADD_NAME
    if text in CATEGORIES:
        await update.message.reply_text("Category already exists. Send a different name or /cancel.")
        return CATEGORY_ADD_NAME

    CATEGORIES[text] = []
    save_json(CATEGORIES_FILE, CATEGORIES)
    await update.message.reply_text(f"Category *{text}* added.", parse_mode="Markdown")
    # Return to categories menu (simulate callback)
    fake_update = update
    fake_update.callback_query = None
    return await admin_show_categories(fake_update, context)

async def handle_category_edit_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_name = update.message.text.strip().lower()
    old_name = context.user_data.get('edit_cat_key')

    if ' ' in new_name or not new_name.isalnum():
        await update.message.reply_text("Invalid category name. Use only letters and numbers, no spaces. Send again or /cancel.")
        return CATEGORY_EDIT_NAME

    if new_name in CATEGORIES:
        await update.message.reply_text("Category name already exists. Send a different name or /cancel.")
        return CATEGORY_EDIT_NAME

    if old_name and old_name in CATEGORIES:
        CATEGORIES[new_name] = CATEGORIES.pop(old_name)

        # Update category names in items if stored elsewhere (we store in keys, so this is enough)
        save_json(CATEGORIES_FILE, CATEGORIES)
        await update.message.reply_text(f"Category renamed from *{old_name}* to *{new_name}*.", parse_mode="Markdown")
    else:
        await update.message.reply_text("Old category not found.")
    return await admin_show_categories(update, context)

async def handle_item_add_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = update.message.text.strip().lower()
    if ' ' in key or not key.isalnum():
        await update.message.reply_text("Invalid item key. Use only letters and numbers, no spaces. Send again or /cancel.")
        return ITEM_ADD_KEY
    if key in ITEMS:
        await update.message.reply_text("Item key already exists. Send another or /cancel.")
        return ITEM_ADD_KEY
    context.user_data['new_item_key'] = key
    await update.message.reply_text("Send me the item *name*.", parse_mode="Markdown")
    return ITEM_ADD_NAME

async def handle_item_add_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    context.user_data['new_item_name'] = name
    await update.message.reply_text("Send me the item *price in BTC* (e.g. 0.0001).", parse_mode="Markdown")
    return ITEM_ADD_PRICE

async def handle_item_add_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = float(update.message.text.strip())
        if price <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Invalid price. Enter a positive number like 0.0001. Send again or /cancel.")
        return ITEM_ADD_PRICE
    context.user_data['new_item_price'] = price
    await update.message.reply_text("Send me the item *file path* (relative to the bot script).", parse_mode="Markdown")
    return ITEM_ADD_PATH

async def handle_item_add_path(update: Update, context: ContextTypes.DEFAULT_TYPE):
    path = update.message.text.strip()
    if not os.path.exists(path):
        await update.message.reply_text("File does not exist. Send a valid file path or /cancel.")
        return ITEM_ADD_PATH
    context.user_data['new_item_path'] = path

    # Show categories to choose from
    keyboard = [
        [InlineKeyboardButton(cat.title(), callback_data=f"select_cat_{cat}")]
        for cat in CATEGORIES.keys()
    ]
    keyboard.append([InlineKeyboardButton("Cancel", callback_data="admin_back_to_menu")])
    await update.message.reply_text("Select category for this item:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ITEM_ADD_CATEGORY

async def handle_item_add_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if not data.startswith("select_cat_"):
        await query.message.edit_text("Invalid selection, cancelling.")
        return await admin_show_items(update, context)

    cat = data[len("select_cat_"):]
    if cat not in CATEGORIES:
        await query.message.edit_text("Category not found, cancelling.")
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

    await query.message.edit_text(f"Item *{key}* added to category *{cat}*.", parse_mode="Markdown")
    return await admin_show_items(update, context)

async def handle_item_edit_field_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    item_key = context.user_data.get('edit_item_key')
    field = context.user_data.get('edit_item_field')
    if not item_key or not field:
        await update.message.reply_text("No item or field selected. /cancel")
        return ConversationHandler.END

    if item_key not in ITEMS:
        await update.message.reply_text("Item not found. /cancel")
        return ConversationHandler.END

    # Handle price field specially (validate float)
    if field == "price_btc":
        try:
            val = float(text)
            if val <= 0:
                raise ValueError
            ITEMS[item_key][field] = val
        except ValueError:
            await update.message.reply_text("Invalid price. Send a positive number or /cancel.")
            return ITEM_EDIT_FIELD_VALUE
    elif field == "category":
        if text not in CATEGORIES:
            await update.message.reply_text(f"Category '{text}' does not exist. Send an existing category or /cancel.")
            return ITEM_EDIT_FIELD_VALUE
        # Remove item from old category and add to new one
        for cat, items in CATEGORIES.items():
            if item_key in items:
                items.remove(item_key)
        CATEGORIES[text].append(item_key)
    else:
        # name or file_path
        if field == "file_path" and not os.path.exists(text):
            await update.message.reply_text("File path does not exist. Send valid path or /cancel.")
            return ITEM_EDIT_FIELD_VALUE
        ITEMS[item_key][field] = text

    save_json(ITEMS_FILE, ITEMS)
    save_json(CATEGORIES_FILE, CATEGORIES)

    await update.message.reply_text(f"Updated {field} for item *{item_key}*.", parse_mode="Markdown")
    return await admin_edit_item_menu(update, context, item_key)

# Cancel handler
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END

def main():
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
            ITEM_EDIT_SELECT: [CallbackQueryHandler(admin_callback_handler, pattern="^(edit_field_|back_to_items)$")],
            ITEM_EDIT_FIELD_SELECT: [CallbackQueryHandler(admin_callback_handler, pattern="^(edit_field_|back_to_items)$")],
            ITEM_EDIT_FIELD_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_item_edit_field_value)],
            ITEM_DELETE_CONFIRM: [CallbackQueryHandler(admin_callback_handler, pattern="^(confirm_delete_item|admin_manage_items)$")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )
    app.add_handler(admin_conv)

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
