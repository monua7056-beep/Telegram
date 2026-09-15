import os
import json
import logging
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ================== CONFIG ==================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8853339410:AAEdVTPwN4UDVcR1r2C2n2pI7VnaGP-bnFw")
ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "7226188227"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================== STORAGE ==================
USERS = {}
MESSAGES = []

# ================== HELPERS ==================
def is_admin(user_id):
    return user_id == ADMIN_CHAT_ID

def add_user(user_id, username, first_name):
    if str(user_id) not in USERS:
        USERS[str(user_id)] = {
            "id": user_id,
            "username": username,
            "first_name": first_name,
            "join_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "is_banned": False,
            "is_premium": False
        }
        return True
    return False

# ================== KEYBOARDS ==================
def get_main_keyboard(user_id):
    if is_admin(user_id):
        keyboard = [
            [KeyboardButton("📊 Stats"), KeyboardButton("👥 Users")],
            [KeyboardButton("📢 Broadcast"), KeyboardButton("📝 Help")],
            [KeyboardButton("ℹ️ About")]
        ]
    else:
        keyboard = [
            [KeyboardButton("📊 Stats"), KeyboardButton("📞 Contact Admin")],
            [KeyboardButton("📝 Help"), KeyboardButton("ℹ️ About")]
        ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ================== COMMANDS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    is_new = add_user(user.id, user.username, user.first_name)
    
    text = f"""
{'🎉 Welcome!' if is_new else '👋 Welcome back!'}

🤖 *Telegram Bot (Vercel Hosted)*

👤 Your ID: `{user.id}`
{'🔐 Status: ADMIN' if is_admin(user.id) else '👤 Status: USER'}

⚡ Bot Vercel पर 24/7 online है!
"""
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=get_main_keyboard(user.id))

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """
📝 *Help Menu*

*Commands:*
/start - Start bot
/stats - Show statistics
/help - This message
/about - About bot

*Buttons:*
• 📊 Stats - Statistics देखें
• 📞 Contact Admin - Admin से बात करें
• ℹ️ About - Bot की जानकारी
"""
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=get_main_keyboard(update.effective_user.id))

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = f"""
📊 *Bot Statistics*

• 👥 Total Users: `{len(USERS)}`
• 💬 Total Messages: `{len(MESSAGES)}`
• 🟢 Status: Online
• ⚡ Platform: Vercel
• 🕐 Time: `{datetime.now().strftime('%H:%M:%S')}`
"""
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=get_main_keyboard(update.effective_user.id))

async def about_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """
🤖 *About This Bot*

*Version:* 1.0
*Platform:* Vercel Serverless
*Framework:* python-telegram-bot
*Hosting:* Free (Vercel)

⚡ Powered by Python
"""
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=get_main_keyboard(update.effective_user.id))

async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Admin only command!")
        return
    
    if not USERS:
        await update.message.reply_text("कोई user नहीं है अभी।")
        return
    
    text = f"👥 *Total Users: {len(USERS)}*\n\n"
    for uid, u in list(USERS.items())[:20]:
        text += f"• `{uid}` - {u.get('first_name', 'N/A')}\n"
    
    await update.message.reply_text(text, parse_mode="Markdown")

async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Admin only!")
        return
    
    if not context.args:
        await update.message.reply_text("Usage: `/broadcast Your message here`", parse_mode="Markdown")
        return
    
    msg = " ".join(context.args)
    count = 0
    for uid in USERS.keys():
        try:
            await context.bot.send_message(chat_id=int(uid), text=f"📢 *Broadcast:*\n\n{msg}", parse_mode="Markdown")
            count += 1
        except:
            pass
    
    await update.message.reply_text(f"✅ Broadcast sent to {count} users")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    
    if text == "📊 Stats":
        await stats_cmd(update, context)
    elif text == "📝 Help":
        await help_cmd(update, context)
    elif text == "ℹ️ About":
        await about_cmd(update, context)
    elif text == "👥 Users":
        await users_cmd(update, context)
    elif text == "📢 Broadcast":
        await update.message.reply_text("Usage: `/broadcast Your message`", parse_mode="Markdown")
    elif text == "📞 Contact Admin":
        MESSAGES.append({
            "user_id": user_id,
            "text": text,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        await update.message.reply_text("✍️ अपना message लिखें, admin तक पहुंचा दूंगा।")
    else:
        # Forward to admin
        if not is_admin(user_id):
            try:
                await context.bot.send_message(
                    chat_id=ADMIN_CHAT_ID,
                    text=f"📩 *Message from* `{user_id}`:\n\n{text}",
                    parse_mode="Markdown"
                )
            except:
                pass
        
        MESSAGES.append({
            "user_id": user_id,
            "text": text,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        await update.message.reply_text("✅ Message received!")

# ================== WEBHOOK PROCESS ==================
async def process_update(update_data):
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_cmd))
    application.add_handler(CommandHandler("stats", stats_cmd))
    application.add_handler(CommandHandler("about", about_cmd))
    application.add_handler(CommandHandler("users", users_cmd))
    application.add_handler(CommandHandler("broadcast", broadcast_cmd))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    await application.initialize()
    update = Update.de_json(update_data, application.bot)
    await application.process_update(update)
    await application.shutdown()

# ================== VERCEL HANDLER ==================
class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Bot is running!")
    
    def do_POST(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            update_data = json.loads(body)
            
            import asyncio
            asyncio.run(process_update(update_data))
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"ok": true}')
        except Exception as e:
            logger.error(f"Error: {e}")
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b'{"ok": false}')
