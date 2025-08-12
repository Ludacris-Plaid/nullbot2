import os
import asyncio
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
TELEGRAM_TOKEN = "8306200181:AAHP56BkD6eZOcqjI6MZNrMdU7M06S0tIrs"
BLOCKONOMICS_API_KEY = os.getenv("BLOCKONOMICS_API_KEY")  # Your Blockonomics API key from .env

# Sample digital items (replace paths with your actual files)
ITEMS = {
    "item1": {"name": "Dark Secret File", "price_btc": 0.0001, "file_path": "/Users/anon/Documents/tele_bot/items/secret.pdf"},
    "item2": {"name": "Forbidden Archive", "price_btc": 0.0002, "file_path": "/Users/anon/Documents/tele_bot/items/archive.zip"}
}

# Path to your .mp4 file (replace with your actual video)
VIDEO_PATH = "/Users/anon/Desktop/game over.mp4"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Send the .mp4 video when /start is triggered
    try:
        with open(VIDEO_PATH, 'rb') as video:
            await update.message.reply_video(video=video, caption="Welcome to the dark side, fucker.")
    except FileNotFoundError:
        await update.message.reply_text("Video’s fucked. Fix the path, idiot.")
    
    # Show product menu
    keyboard = [
        [InlineKeyboardButton(item["name"], callback_data=key) for key, item in ITEMS.items()]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Pick your poison:", reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    item_key = query.data
    item = ITEMS.get(item_key)
    
    if not item:
        await query.message.reply_text("Item’s gone, asshole. Pick something else.")
        return
    
    # Generate Bitcoin payment address
    try:
        headers = {'Authorization': f'Bearer {BLOCKONOMICS_API_KEY}'}
        response = requests.post('https://www.blockonomics.co/api/new_address', headers=headers)
        response.raise_for_status()
        btc_address = response.json()['address']
    except Exception as e:
        await query.message.reply_text(f"Failed to get BTC address: {str(e)}. Try again, dipshit.")
        return
    
    # Store payment details for /confirm
    context.user_data['pending_payment'] = {
        'item_key': item_key,
        'address': btc_address,
        'amount': item['price_btc']
    }
    
    await query.message.reply_text(
        f"Send {item['price_btc']} BTC to {btc_address} for {item['name']}.\n"
        "Run /confirm when you’ve paid, or I’ll know you’re a cheap fuck."
    )
    
    # Taunt after 10 minutes if no payment
    async def taunt():
        await asyncio.sleep(600)  # 10 minutes
        if context.user_data.get('pending_payment'):
            await query.message.reply_text("Still no payment? You’re pissing me off, scum.")
    asyncio.create_task(taunt())

async def confirm_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pending = context.user_data.get('pending_payment')
    if not pending:
        await update.message.reply_text("No pending payment, asshole. Buy something first.")
        return
    
    # Check payment status with Blockonomics
    try:
        address = pending['address']
        headers = {'Authorization': f'Bearer {BLOCKONOMICS_API_KEY}'}
        response = requests.get(f'https://www.blockonomics.co/api/balance', json={'addr': [address]}, headers=headers)
        response.raise_for_status()
        balance_data = response.json()['data'][0]
        received_btc = balance_data['confirmed'] / 100000000  # Convert satoshis to BTC
        
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

def main():
    # Initialize Telegram bot
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("confirm", confirm_payment))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    # Start the bot
    app.run_polling()

if __name__ == "__main__":
    main()