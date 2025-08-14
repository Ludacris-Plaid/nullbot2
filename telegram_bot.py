import logging
import time
from functools import wraps
from telegram.error import TelegramError
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
import aiohttp

# Setup logging
logging.basicConfig(filename='darkbot.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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
                await update.message.reply_text("Slow down, you spamming fuck. Wait a bit or I’ll block your ass.")
                logging.warning(f"User {user_id} rate-limited on {func.__name__}")
                return
            context.user_data['rate_limit'][func.__name__].append(now)
            return await func(update, context, *args, **kwargs)
        return wrapper
    return decorator

# Validate CATEGORIES and ITEMS on startup
def sync_categories_items():
    for cat, items in CATEGORIES.items():
        CATEGORIES[cat] = [item for item in items if item in ITEMS]
    save_json(CATEGORIES_FILE, CATEGORIES)
    logging.info("Synced categories and items")

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

# Modified button_callback for payment
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    logging.info(f"Callback data: {data} from user {query.from_user.id}")

    if data.startswith("cat_"):
        cat_key = data[4:]
        items_in_cat = CATEGORIES.get(cat_key, [])
        if not items_in_cat:
            await query.message.edit_text(f"No items in {cat_key.title()}, asshole.")
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
        await admin_callback_handler(update, context)

    else:
        item_key = data
        item = ITEMS.get(item_key)
        if not item:
            await query.message.reply_text("Item’s gone, asshole. Pick something else.")
            return

        btc_address = await fetch_btc_address()
        if not btc_address:
            await query.message.reply_text("Can’t get BTC address, system’s fucked. Try later, dipshit.")
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

        # Background payment checker
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
                        logging.info(f"Payment confirmed for {item_key} by user {query.from_user.id}")
                        return
                    except FileNotFoundError:
                        await query.message.reply_text("File’s fucked. Tell the admin to fix their shit.")
                        logging.error(f"File not found: {item['file_path']}")
                        return
                await asyncio.sleep(60)  # Check every minute
            await query.message.reply_text("Payment timed out, you cheap fuck. Start over or I’ll leak your address.")
            del context.user_data['pending_payment']
            logging.warning(f"Payment timeout for user {query.from_user.id}")

        asyncio.create_task(check_payment())

@rate_limit(limit=5, period=60)  # 5 confirms per minute
async def confirm_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pending = context.user_data.get('pending_payment')
    if not pending:
        await update.message.reply_text("No pending payment, asshole. Buy something first.")
        return

    received_btc = await check_btc_balance(pending['address'], pending['amount'])
    if received_btc >= pending['amount']:
        item = ITEMS[pending['item_key']]
        try:
            with open(item['file_path'], 'rb') as file:
                await update.message.reply_document(
                    document=InputFile(file),
                    caption=f"Here's your {item['name']}. Enjoy, you sick fuck."
                )
            del context.user_data['pending_payment']
            logging.info(f"Payment confirmed for {pending['item_key']} by user {update.effective_user.id}")
        except FileNotFoundError:
            await update.message.reply_text("File’s fucked. Fix the path, moron.")
            logging.error(f"File not found: {item['file_path']}")
    else:
        await update.message.reply_text("Payment not confirmed yet. Don’t fuck with me.")
        logging.info(f"Payment not confirmed for {pending['item_key']} by user {update.effective_user.id}")

# Modified handle_item_add_path to validate file
async def handle_item_add_path(update: Update, context: ContextTypes.DEFAULT_TYPE):
    path = update.message.text.strip()
    if not os.path.exists(path):
        await update.message.reply_text("File does not exist. Send a valid file path or /cancel.")
        return ITEM_ADD_PATH
    if os.path.getsize(path) > 50 * 1024 * 1024:  # 50MB limit
        await update.message.reply_text("File’s too big, asshole. Keep it under 50MB or /cancel.")
        return ITEM_ADD_PATH
    context.user_data['new_item_path'] = path
    keyboard = [
        [InlineKeyboardButton(cat.title(), callback_data=f"select_cat_{cat}")]
        for cat in CATEGORIES.keys()
    ]
    keyboard.append([InlineKeyboardButton("Cancel", callback_data="admin_back_to_menu")])
    await update.message.reply_text("Select category for this item:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ITEM_ADD_CATEGORY

# Modified main to handle webhook errors and sync
def main():
    sync_categories_items()
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