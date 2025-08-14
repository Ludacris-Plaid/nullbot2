import os
import json
import asyncio
import logging
from typing import Any, Dict, List, Optional

import aiohttp
from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

# =========================
# Setup & Config
# =========================

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
BLOCKONOMICS_API_KEY = os.getenv("BLOCKONOMICS_API_KEY")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "0"))
SPICY_MODE = os.getenv("SPICY_MODE", "true").lower() == "true"  # edgy language toggle
VIDEO_URL = os.getenv(
    "WELCOME_VIDEO",
    "https://ik.imagekit.io/myrnjevjk/game%20over.mp4?updatedAt=1754980438031",
)

CATEGORIES_FILE = os.getenv("CATEGORIES_FILE", "categories.json")
ITEMS_FILE = os.getenv("ITEMS_FILE", "items.json")

# Logging
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("shopbot")

# Conversation states
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


# =========================
# Helpers: JSON persistence
# =========================

def load_json(filepath: str, default: Any) -> Any:
    if os.path.exists(filepath):
        try:
            with open(filepath, "r") as f:
                return json.load(f)
        except Exception as e:
            log.error(f"Failed to load {filepath}: {e}")
    return default


def save_json(filepath: str, data: Any) -> None:
    try:
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        log.error(f"Failed to save {filepath}: {e}")


# initial defaults
CATEGORIES: Dict[str, List[str]] = load_json(
    CATEGORIES_FILE,
    {"cards": ["item1", "item3", "item7"], "tutorials": ["item2", "item5", "item6", "item9"], "pages": ["item4", "item8", "item10"]},
)
ITEMS: Dict[str, Dict[str, Any]] = load_json(
    ITEMS_FILE,
    {
        "item1": {"name": "Dark Secret Card", "price_btc": 0.0001, "file_path": "items/secret.pdf"},
        "item2": {"name": "Forbidden Tutorial", "price_btc": 0.0002, "file_path": "items/archive.zip"},
        "item3": {"name": "Blackout Blackjack Guide", "price_btc": 0.0003, "file_path": "items/blackjack.pdf"},
        "item4": {"name": "Cryptic Code Pages", "price_btc": 0.00015, "file_path": "items/codepages.pdf"},
        "item5": {"name": "Cybersecurity Masterclass", "price_btc": 0.0005, "file_path": "items/malware.mp4"},
        "item6": {"name": "Phantom Code Manual", "price_btc": 0.00025, "file_path": "items/phishing.pdf"},
        "item7": {"name": "Ghost Scripts Collection", "price_btc": 0.0004, "file_path": "items/ghostscripts.zip"},
        "item8": {"name": "Shadow Pages Vol.1", "price_btc": 0.00012, "file_path": "items/shadowpages.pdf"},
        "item9": {"name": "Underground Tips", "price_btc": 0.00035, "file_path": "items/hacktips.pdf"},
        "item10": {"name": "Market Blueprints", "price_btc": 0.0006, "file_path": "items/blueprints.pdf"},
    },
)


# =========================
# Flavor text
# =========================
def spicy(nice: str, spicy: str) -> str:
    return spicy if SPICY_MODE else nice


WELCOME_TEXT = spicy(
    "Welcome.",
    "Welcome to the dark side, fucker.",
)
NO_ITEMS_TEXT = spicy(
    "No items found in this category.",
    "No items found in this category, asshole.",
)
NO_PENDING_TEXT = spicy(
    "No pending payment.",
    "No pending payment, asshole. Buy something first.",
)
SEND_AFTER_PAY_TEXT = spicy(
    "Run /confirm when you’ve paid.",
    "Run /confirm when you’ve paid, or I’ll know you’re a cheap fuck.",
)
NOT_CONFIRMED_TEXT = spicy(
    "Payment not confirmed yet.",
    "Payment not confirmed yet. Don’t fuck with me.",
)
PAYMENT_CHECK_FAIL_TEXT = spicy(
    "Payment check failed. Try again later.",
    "Payment check failed. Try again, dumbass.",
)
FILE_MISSING_TEXT = spicy(
    "File not found. Please contact the admin.",
    "File’s fucked. Fix the path, moron.",
)
NOT_ADMIN_TEXT = spicy(
    "You are not authorized to use admin mode.",
    "You’re not admin, get lost.",
)


# =========================
# Utility: Context-safe message edit/reply
# =========================
async def safe_reply_or_edit(update: Update, text: str, reply_markup: Optional[InlineKeyboardMarkup] = None, parse_mode: Optional[str] = None):
    if update.callback_query:
        try:
            await update.callback_query.message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        except Exception:
            # fall back to replying
            await update.callback_query.message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)


# =========================
# Payment utils (Blockonomics)
# =========================
async def get_aiohttp_session(context: ContextTypes.DEFAULT_TYPE) -> aiohttp.ClientSession:
    """
    Reuse a single aiohttp session stored on application for efficiency.
    """
    app_data = context.application.bot_data
    if "aiohttp_session" not in app_data or app_data["aiohttp_session"].closed:
        app_data["aiohttp_session"] = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20))
    return app_data["aiohttp_session"]


def btc_link(address: str, amount: float) -> str:
    # Deep link for wallet apps
    return f"bitcoin:{address}?amount={amount}"


async def blockonomics_new_address(context: ContextTypes.DEFAULT_TYPE) -> str:
    session = await get_aiohttp_session(context)
    headers = {"Authorization": f"Bearer {BLOCKONOMICS_API_KEY}"}
    url = "https://www.blockonomics.co/api/new_address"
    async with session.post(url, headers=headers) as resp:
        if resp.status != 200:
            txt = await resp.text()
            raise RuntimeError(f"new_address failed: HTTP {resp.status} - {txt}")
        data = await resp.json()
    address = data.get("address")
    if not address:
        raise RuntimeError("No address returned")
    return address


async def blockonomics_confirmed_btc(context: ContextTypes.DEFAULT_TYPE, address: str) -> float:
    """
    Returns confirmed balance in BTC for the given address.
    """
    session = await get_aiohttp_session(context)
    headers = {"Authorization": f"Bearer {BLOCKONOMICS_API_KEY}"}

    # Primary: GET /api/address?addr=...
    url = f"https://www.blockonomics.co/api/address?addr={address}"
    async with session.get(url, headers=headers) as resp:
        if resp.status == 200:
            data = await resp.json()
            confirmed = data.get("confirmed", 0)
            return float(confirmed) / 1e8

    # Fallback: POST /api/balance {addr: [address]}
    url_fallback = "https://www.blockonomics.co/api/balance"
    async with session.post(url_fallback, json={"addr": [address]}, headers=headers) as resp:
        if resp.status != 200:
            txt = await resp.text()
            raise RuntimeError(f"balance failed: HTTP {resp.status} - {txt}")
        data = await resp.json()
    try:
        sat = data["data"][0]["confirmed"]
    except Exception as e:
        raise RuntimeError(f"bad balance payload: {e}")
    return float(sat) / 1e8


# =========================
# Bot: Public Handlers
# =========================
def is_admin(update: Update) -> bool:
    user = update.effective_user
    return bool(user and user.id == ADMIN_USER_ID)


def categories_keyboard() -> InlineKeyboardMarkup:
    keyboard = [[InlineKeyboardButton(cat.title(), callback_data=f"cat_{cat}")] for cat in CATEGORIES.keys()]
    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # welcome video (non-blocking)
    try:
        if VIDEO_URL:
            await update.message.reply_video(video=VIDEO_URL, caption=WELCOME_TEXT)
        else:
            await update.message.reply_text(WELCOME_TEXT)
    except Exception as e:
        await update.message.reply_text(f"Error sending welcome: {e}")

    await update.message.reply_text("Choose a category:", reply_markup=categories_keyboard())


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Commands:\n"
        "/start – Open shop\n"
        "/confirm – Confirm payment after sending BTC\n"
        "/help – This help\n"
        "/admin – Admin panel (restricted)\n"
        "/cancel – Cancel current action\n"
    )
    await update.message.reply_text(text)


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    log.info(f"[DEBUG] callback: {data}")

    if data.startswith("cat_"):
        cat_key = data[4:]
        items_in_cat = CATEGORIES.get(cat_key, [])
        if not items_in_cat:
            await query.message.edit_text(NO_ITEMS_TEXT)
            return

        keyboard = [
            [InlineKeyboardButton(ITEMS[key]["name"], callback_data=f"item_{key}")]
            for key in items_in_cat
            if key in ITEMS
        ]
        keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="back_to_categories")])
        await query.message.edit_text(f"Items in *{cat_key.title()}*:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

    elif data == "back_to_categories":
        await query.message.edit_text("Choose a category:", reply_markup=categories_keyboard())

    elif data.startswith("item_"):
        item_key = data[5:]
        item = ITEMS.get(item_key)
        if not item:
            await query.message.reply_text(spicy("Item no longer exists.", "Item’s gone, asshole. Pick something else."))
            return

        try:
            address = await blockonomics_new_address(context)
            log.info(f"[DEBUG] new BTC address: {address}")
        except Exception as e:
            await query.message.reply_text(spicy(f"Failed to get BTC address: {e}", f"Failed to get BTC address: {e}. Try again, dipshit."))
            return

        # Stash pending payment
        context.user_data["pending_payment"] = {
            "item_key": item_key,
            "address": address,
            "amount": float(item["price_btc"]),
        }

        kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Open in wallet", url=btc_link(address, item["price_btc"]))],
                [InlineKeyboardButton("⬅️ Back", callback_data="back_to_categories")],
            ]
        )

        msg = (
            f"Pay *{item['price_btc']} BTC* to:\n`{address}`\n\n"
            f"Item: *{item['name']}*\n\n"
            f"{SEND_AFTER_PAY_TEXT}"
        )
        await query.message.edit_text(msg, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)

        # Gentle reminder in 10 minutes
        async def taunt():
            await asyncio.sleep(600)
            if context.user_data.get("pending_payment"):
                await query.message.reply_text(
                    spicy("Still no payment?", "Still no payment? You’re pissing me off, scum.")
                )

        asyncio.create_task(taunt())

    elif data.startswith("admin_"):
        # Route to admin handler
        await admin_callback_handler(update, context)

    else:
        await query.message.reply_text("Unhandled action.")


async def confirm_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pending = context.user_data.get("pending_payment")
    if not pending:
        await update.message.reply_text(NO_PENDING_TEXT)
        return

    item_key = pending["item_key"]
    address = pending["address"]
    amount_req = float(pending["amount"])

    try:
        received_btc = await blockonomics_confirmed_btc(context, address)
    except Exception as e:
        await update.message.reply_text(f"{PAYMENT_CHECK_FAIL_TEXT}\n\nDetails: {e}")
        return

    if received_btc >= amount_req:
        item = ITEMS.get(item_key)
        if not item:
            await update.message.reply_text(spicy("Item missing.", "Item vanished. Tough luck."))
            return
        fpath = item["file_path"]
        if not os.path.exists(fpath):
            await update.message.reply_text(FILE_MISSING_TEXT)
            return

        # Send file
        try:
            with open(fpath, "rb") as fp:
                await update.message.reply_document(document=InputFile(fp), caption=spicy(f"Here's your {item['name']}.", f"Here's your {item['name']}. Enjoy, you sick fuck."))
            del context.user_data["pending_payment"]
        except Exception as e:
            await update.message.reply_text(f"Failed to deliver file: {e}")
    else:
        shortfall = amount_req - received_btc
        await update.message.reply_text(f"{NOT_CONFIRMED_TEXT}\n\nReceived: {received_btc:.8f} BTC\nNeeded: {amount_req:.8f} BTC\nShort: {shortfall:.8f} BTC")


# =========================
# Admin: Menus & Actions
# =========================

async def admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text(NOT_ADMIN_TEXT)
        return ConversationHandler.END

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📂 Manage Categories", callback_data="admin_manage_categories")],
            [InlineKeyboardButton("🧾 Manage Items", callback_data="admin_manage_items")],
            [InlineKeyboardButton("Exit Admin", callback_data="admin_exit")],
        ]
    )
    await update.message.reply_text("Admin menu:", reply_markup=keyboard)
    return ADMIN_MENU


async def admin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data or ""

    if data == "admin_manage_categories":
        return await admin_show_categories(update, context)

    if data == "admin_manage_items":
        return await admin_show_items(update, context)

    if data == "admin_exit":
        await query.message.edit_text("Exiting admin mode.")
        return ConversationHandler.END

    if data == "admin_back_to_menu":
        return await admin_start(update, context)

    # Category flows
    if data == "add_category":
        await query.message.edit_text("Send me the *name* of the new category (lowercase, letters/numbers only).", parse_mode=ParseMode.MARKDOWN)
        return CATEGORY_ADD_NAME

    if data.startswith("edit_cat_"):
        cat_key = data.replace("edit_cat_", "", 1)
        context.user_data["edit_cat_key"] = cat_key
        await query.message.edit_text(
            f"Editing category *{cat_key}*\nSend new name (lowercase, letters/numbers), or /cancel.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return CATEGORY_EDIT_NAME

    if data.startswith("delete_cat_"):
        cat_key = data.replace("delete_cat_", "", 1)
        context.user_data["del_cat_key"] = cat_key
        keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Yes, delete it", callback_data="confirm_delete_cat")],
                [InlineKeyboardButton("No, go back", callback_data="admin_manage_categories")],
            ]
        )
        await query.message.edit_text(
            f"Delete category *{cat_key}*? Items will be orphaned.",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN,
        )
        return CATEGORY_DELETE_CONFIRM

    if data == "confirm_delete_cat":
        cat_key = context.user_data.get("del_cat_key")
        if cat_key and cat_key in CATEGORIES:
            del CATEGORIES[cat_key]
            save_json(CATEGORIES_FILE, CATEGORIES)
            await query.message.edit_text(f"Category *{cat_key}* deleted.", parse_mode=ParseMode.MARKDOWN)
        else:
            await query.message.edit_text("No category selected or not found.")
        return await admin_show_categories(update, context)

    # Item flows
    if data == "add_item":
        await query.message.edit_text("Send the new item *key* (unique id, lowercase letters/numbers).", parse_mode=ParseMode.MARKDOWN)
        return ITEM_ADD_KEY

    if data.startswith("edit_item_"):
        item_key = data.replace("edit_item_", "", 1)
        if item_key not in ITEMS:
            await query.message.edit_text("Item not found.")
            return await admin_show_items(update, context)
        context.user_data["edit_item_key"] = item_key
        return await admin_edit_item_menu(update, context, item_key)

    if data.startswith("delete_item_"):
        item_key = data.replace("delete_item_", "", 1)
        context.user_data["del_item_key"] = item_key
        keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Yes, delete it", callback_data="confirm_delete_item")],
                [InlineKeyboardButton("No, go back", callback_data="admin_manage_items")],
            ]
        )
        await query.message.edit_text(f"Delete item *{item_key}*?", reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        return ITEM_DELETE_CONFIRM

    if data == "confirm_delete_item":
        item_key = context.user_data.get("del_item_key")
        if item_key and item_key in ITEMS:
            del ITEMS[item_key]
            for cat, items in CATEGORIES.items():
                if item_key in items:
                    items.remove(item_key)
            save_json(ITEMS_FILE, ITEMS)
            save_json(CATEGORIES_FILE, CATEGORIES)
            await query.message.edit_text(f"Item *{item_key}* deleted.", parse_mode=ParseMode.MARKDOWN)
        else:
            await query.message.edit_text("No item selected or not found.")
        return await admin_show_items(update, context)

    if data.startswith("edit_field_"):
        field = data.replace("edit_field_", "", 1)
        context.user_data["edit_item_field"] = field
        await query.message.edit_text(f"Send new value for *{field}*, or /cancel.", parse_mode=ParseMode.MARKDOWN)
        return ITEM_EDIT_FIELD_VALUE

    # Back buttons
    if data == "back_to_categories_admin":
        return await admin_show_categories(update, context)
    if data == "back_to_items":
        return await admin_show_items(update, context)
    if data == "back_to_admin":
        return await admin_start(update, context)

    return ADMIN_MENU


async def admin_show_categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = []
    for key in CATEGORIES.keys():
        rows.append(
            [InlineKeyboardButton(f"{key.title()} ✏️", callback_data=f"edit_cat_{key}"),
             InlineKeyboardButton("🗑️", callback_data=f"delete_cat_{key}")]
        )
    rows.append([InlineKeyboardButton("➕ Add New Category", callback_data="add_category")])
    rows.append([InlineKeyboardButton("⬅️ Back to Admin Menu", callback_data="admin_back_to_menu")])

    await safe_reply_or_edit(update, "Categories:", InlineKeyboardMarkup(rows))
    return CATEGORY_MENU


async def admin_show_items(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = []
    for key, item in ITEMS.items():
        rows.append(
            [InlineKeyboardButton(f"{item['name']} ✏️", callback_data=f"edit_item_{key}"),
             InlineKeyboardButton("🗑️", callback_data=f"delete_item_{key}")]
        )
    rows.append([InlineKeyboardButton("➕ Add New Item", callback_data="add_item")])
    rows.append([InlineKeyboardButton("⬅️ Back to Admin Menu", callback_data="admin_back_to_menu")])

    await safe_reply_or_edit(update, "Items:", InlineKeyboardMarkup(rows))
    return ITEM_MENU


async def admin_edit_item_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, item_key: Optional[str] = None):
    if not item_key:
        item_key = context.user_data.get("edit_item_key")
    item = ITEMS.get(item_key)
    if not item:
        await safe_reply_or_edit(update, "Item not found.")
        return await admin_show_items(update, context)

    # find category for item
    cat_for_item = None
    for cat, items in CATEGORIES.items():
        if item_key in items:
            cat_for_item = cat
            break

    text = (
        f"Editing item *{item_key}*:\n"
        f"Name: {item['name']}\n"
        f"Price BTC: {item['price_btc']}\n"
        f"File Path: {item['file_path']}\n"
        f"Category: {cat_for_item or 'None'}"
    )

    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Name", callback_data="edit_field_name")],
            [InlineKeyboardButton("Price BTC", callback_data="edit_field_price_btc")],
            [InlineKeyboardButton("File Path", callback_data="edit_field_file_path")],
            [InlineKeyboardButton("Category", callback_data="edit_field_category")],
            [InlineKeyboardButton("⬅️ Back to Items", callback_data="back_to_items")],
        ]
    )
    await safe_reply_or_edit(update, text, kb, parse_mode=ParseMode.MARKDOWN)
    return ITEM_EDIT_FIELD_SELECT


# -------- Category: add/edit (messages) --------

async def handle_category_add_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().lower()
    if " " in text or not text.isalnum():
        await update.message.reply_text("Invalid category name. Use only letters and numbers, no spaces. Send again or /cancel.")
        return CATEGORY_ADD_NAME
    if text in CATEGORIES:
        await update.message.reply_text("Category already exists. Send a different name or /cancel.")
        return CATEGORY_ADD_NAME

    CATEGORIES[text] = []
    save_json(CATEGORIES_FILE, CATEGORIES)
    await update.message.reply_text(f"Category *{text}* added.", parse_mode=ParseMode.MARKDOWN)
    return await admin_show_categories(update, context)


async def handle_category_edit_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_name = update.message.text.strip().lower()
    old_name = context.user_data.get("edit_cat_key")

    if " " in new_name or not new_name.isalnum():
        await update.message.reply_text("Invalid category name. Use only letters and numbers, no spaces. Send again or /cancel.")
        return CATEGORY_EDIT_NAME

    if new_name in CATEGORIES:
        await update.message.reply_text("Category name already exists. Send a different name or /cancel.")
        return CATEGORY_EDIT_NAME

    if old_name and old_name in CATEGORIES:
        CATEGORIES[new_name] = CATEGORIES.pop(old_name)
        save_json(CATEGORIES_FILE, CATEGORIES)
        await update.message.reply_text(f"Category renamed from *{old_name}* to *{new_name}*.", parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text("Old category not found.")
    return await admin_show_categories(update, context)


# -------- Items: add (messages + callback) --------

def _restrict_items_dir(path: str) -> Optional[str]:
    """
    Ensure file path resolves under ./items (prevent accidental leakage).
    Returns normalized safe path or None if invalid/missing.
    """
    base = os.path.abspath("items")
    target = os.path.abspath(path if path.startswith("items") else os.path.join("items", os.path.basename(path)))
    if os.path.commonpath([base, target]) != base:
        return None
    return target if os.path.exists(target) else None


async def handle_item_add_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = update.message.text.strip().lower()
    if " " in key or not key.isalnum():
        await update.message.reply_text("Invalid item key. Use only letters and numbers, no spaces. Send again or /cancel.")
        return ITEM_ADD_KEY
    if key in ITEMS:
        await update.message.reply_text("Item key already exists. Send another or /cancel.")
        return ITEM_ADD_KEY
    context.user_data["new_item_key"] = key
    await update.message.reply_text("Send me the item *name*.", parse_mode=ParseMode.MARKDOWN)
    return ITEM_ADD_NAME


async def handle_item_add_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    context.user_data["new_item_name"] = name
    await update.message.reply_text("Send me the item *price in BTC* (e.g. 0.0001).", parse_mode=ParseMode.MARKDOWN)
    return ITEM_ADD_PRICE


async def handle_item_add_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = float(update.message.text.strip())
        if price <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Invalid price. Enter a positive number like 0.0001. Send again or /cancel.")
        return ITEM_ADD_PRICE
    context.user_data["new_item_price"] = price
    await update.message.reply_text("Send me the item *file path* (path under ./items).", parse_mode=ParseMode.MARKDOWN)
    return ITEM_ADD_PATH


async def handle_item_add_path(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip()
    safe_path = _restrict_items_dir(raw)
    if not safe_path:
        await update.message.reply_text("File does not exist under ./items. Send a valid path or /cancel.")
        return ITEM_ADD_PATH
    context.user_data["new_item_path"] = safe_path

    keyboard = [[InlineKeyboardButton(cat.title(), callback_data=f"select_cat_{cat}")] for cat in CATEGORIES.keys()]
    keyboard.append([InlineKeyboardButton("Cancel", callback_data="admin_back_to_menu")])
    await update.message.reply_text("Select category for this item:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ITEM_ADD_CATEGORY


async def handle_item_add_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    if not data.startswith("select_cat_"):
        await query.message.edit_text("Invalid selection, cancelling.")
        return await admin_show_items(update, context)

    cat = data.replace("select_cat_", "", 1)
    if cat not in CATEGORIES:
        await query.message.edit_text("Category not found, cancelling.")
        return await admin_show_items(update, context)

    key = context.user_data["new_item_key"]
    ITEMS[key] = {
        "name": context.user_data["new_item_name"],
        "price_btc": context.user_data["new_item_price"],
        "file_path": context.user_data["new_item_path"],
    }
    CATEGORIES[cat].append(key)
    save_json(ITEMS_FILE, ITEMS)
    save_json(CATEGORIES_FILE, CATEGORIES)

    await query.message.edit_text(f"Item *{key}* added to category *{cat}*.", parse_mode=ParseMode.MARKDOWN)
    return await admin_show_items(update, context)


# -------- Item: edit field (message) --------

async def handle_item_edit_field_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    item_key = context.user_data.get("edit_item_key")
    field = context.user_data.get("edit_item_field")
    if not item_key or not field or item_key not in ITEMS:
        await update.message.reply_text("No item/field selected. /cancel")
        return ConversationHandler.END

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
        for cat, items in CATEGORIES.items():
            if item_key in items:
                items.remove(item_key)
        CATEGORIES[text].append(item_key)

    elif field == "file_path":
        safe_path = _restrict_items_dir(text)
        if not safe_path:
            await update.message.reply_text("File path invalid/missing under ./items. Send valid path or /cancel.")
            return ITEM_EDIT_FIELD_VALUE
        ITEMS[item_key][field] = safe_path

    elif field == "name":
        if not text:
            await update.message.reply_text("Name cannot be empty.")
            return ITEM_EDIT_FIELD_VALUE
        ITEMS[item_key][field] = text

    else:
        await update.message.reply_text("Unknown field.")
        return ITEM_EDIT_FIELD_VALUE

    save_json(ITEMS_FILE, ITEMS)
    save_json(CATEGORIES_FILE, CATEGORIES)
    await update.message.reply_text(f"Updated {field} for item *{item_key}*.", parse_mode=ParseMode.MARKDOWN)
    return await admin_edit_item_menu(update, context, item_key)


# -------- Cancel --------

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END


# =========================
# App bootstrap
# =========================

async def on_startup(app: Application):
    log.info("Bot starting up...")


async def on_shutdown(app: Application):
    # Close aiohttp session if exists
    sess: Optional[aiohttp.ClientSession] = app.bot_data.get("aiohttp_session")
    if sess and not sess.closed:
        await sess.close()
    log.info("Bot shut down.")


def main():
    if not TELEGRAM_TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN not set")
    if not BLOCKONOMICS_API_KEY:
        log.warning("BLOCKONOMICS_API_KEY not set. Payments will fail.")

    app = Application.builder().token(TELEGRAM_TOKEN).post_init(on_startup).post_shutdown(on_shutdown).build()

    # Public
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("confirm", confirm_payment))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CallbackQueryHandler(button_callback))

    # Admin conversation
    admin_conv = ConversationHandler(
        entry_points=[CommandHandler("admin", admin_start)],
        states={
            ADMIN_MENU: [
                CallbackQueryHandler(admin_callback_handler, pattern=r"^admin_(manage_categories|manage_items|exit|back_to_menu)$"),
            ],
            CATEGORY_MENU: [
                CallbackQueryHandler(admin_callback_handler, pattern=r"^(add_category|edit_cat_.+|delete_cat_.+|confirm_delete_cat|admin_back_to_menu)$"),
            ],
            CATEGORY_ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_category_add_name)],
            CATEGORY_EDIT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_category_edit_name)],
            CATEGORY_DELETE_CONFIRM: [
                CallbackQueryHandler(admin_callback_handler, pattern=r"^(confirm_delete_cat|admin_manage_categories)$"),
            ],

            ITEM_MENU: [
                CallbackQueryHandler(admin_callback_handler, pattern=r"^(add_item|edit_item_.+|delete_item_.+|confirm_delete_item|admin_back_to_menu)$"),
            ],
            ITEM_ADD_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_item_add_key)],
            ITEM_ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_item_add_name)],
            ITEM_ADD_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_item_add_price)],
            ITEM_ADD_PATH: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_item_add_path)],
            ITEM_ADD_CATEGORY: [CallbackQueryHandler(handle_item_add_category, pattern=r"^select_cat_.+$")],

            ITEM_EDIT_FIELD_SELECT: [
                CallbackQueryHandler(admin_callback_handler, pattern=r"^(edit_field_.+|back_to_items)$"),
            ],
            ITEM_EDIT_FIELD_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_item_edit_field_value)],
            ITEM_DELETE_CONFIRM: [
                CallbackQueryHandler(admin_callback_handler, pattern=r"^(confirm_delete_item|admin_manage_items)$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )
    app.add_handler(admin_conv)

    # Render webhook support or polling
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
        app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
