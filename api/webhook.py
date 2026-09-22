import os
import sys
import subprocess
import shutil
import json
import time
import logging
from datetime import datetime
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler, ConversationHandler
from typing import Optional, Tuple, List, Dict

# ================== CONFIGURATION ==================
BOT_TOKEN = "8369362691:AAHVz6olWvXvxlWWzvV1bGDSMIK2CJVwp70"
ADMIN_CHAT_ID = ID: 8017090914
HOSTING_DIR = "/data/data/com.termux/files/home/bot_hosting"
DATA_FILE = os.path.join(HOSTING_DIR, "users_data.json")

# Conversation states
UPLOAD, BOT_NAME, CONFIRM, ADMIN_ACTION, BROADCAST, USER_MESSAGE, ADMIN_REPLY = range(7)

# ================== SETUP LOGGING ==================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ================== DATA MANAGEMENT ==================

def load_data():
    """Load users data from file"""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return {
        "users": {},
        "uploads": [],
        "messages": [],
        "settings": {
            "allow_user_upload": True,
            "max_file_size_mb": 10,
            "auto_start_bot": False
        }
    }

def save_data(data):
    """Save users data to file"""
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def add_user(user_id, username, first_name):
    """Add/Update user in database"""
    data = load_data()
    if str(user_id) not in data["users"]:
        data["users"][str(user_id)] = {
            "id": user_id,
            "username": username,
            "first_name": first_name,
            "join_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "uploads": 0,
            "is_banned": False,
            "is_premium": False,
            "last_active": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        save_data(data)
        return True
    return False

def add_upload(user_id, bot_name, file_name, file_size):
    """Add upload record"""
    data = load_data()
    data["uploads"].append({
        "user_id": user_id,
        "bot_name": bot_name,
        "file_name": file_name,
        "file_size": file_size,
        "upload_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "uploaded"
    })
    
    # Update user upload count
    if str(user_id) in data["users"]:
        data["users"][str(user_id)]["uploads"] += 1
        data["users"][str(user_id)]["last_active"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    save_data(data)

def add_message(sender_id, receiver_id, message_text, is_admin_msg=False):
    """Add message to history"""
    data = load_data()
    msg_id = len(data["messages"]) + 1
    data["messages"].append({
        "id": msg_id,
        "sender_id": sender_id,
        "receiver_id": receiver_id,
        "message": message_text,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "is_admin_msg": is_admin_msg,
        "read": False
    })
    save_data(data)
    return msg_id

def get_user_uploads(user_id):
    """Get all uploads by user"""
    data = load_data()
    return [upload for upload in data["uploads"] if upload["user_id"] == user_id]

def get_all_uploads():
    """Get all uploads"""
    data = load_data()
    return data["uploads"]

def get_all_users():
    """Get all users"""
    data = load_data()
    return data["users"]

def get_user(user_id):
    """Get specific user"""
    data = load_data()
    return data["users"].get(str(user_id))

def update_user_status(user_id, is_banned=None, is_premium=None):
    """Update user status"""
    data = load_data()
    if str(user_id) in data["users"]:
        if is_banned is not None:
            data["users"][str(user_id)]["is_banned"] = is_banned
        if is_premium is not None:
            data["users"][str(user_id)]["is_premium"] = is_premium
        save_data(data)
        return True
    return False

# ================== UTILITY FUNCTIONS ==================

def setup_hosting_directory():
    """Create hosting directory if not exists"""
    Path(HOSTING_DIR).mkdir(parents=True, exist_ok=True)
    logger.info(f"Hosting directory: {HOSTING_DIR}")

def is_admin(user_id):
    """Check if user is admin"""
    return user_id == ADMIN_CHAT_ID

def is_user_allowed(user_id):
    """Check if user is allowed (not banned)"""
    user = get_user(user_id)
    if user:
        return not user.get("is_banned", False)
    return True

async def save_file(file_id, bot, bot_name, file_name):
    """Save uploaded file"""
    try:
        bot_dir = os.path.join(HOSTING_DIR, bot_name)
        os.makedirs(bot_dir, exist_ok=True)
        
        file = await bot.get_file(file_id)
        file_path = os.path.join(bot_dir, file_name)
        
        await file.download_to_drive(file_path)
        
        logger.info(f"File saved to: {file_path}")
        return file_path, True, os.path.getsize(file_path)
        
    except Exception as e:
        logger.error(f"Error saving file: {e}")
        return None, False, 0

def install_dependencies(bot_name):
    """Install requirements for bot"""
    try:
        bot_dir = os.path.join(HOSTING_DIR, bot_name)
        req_file = os.path.join(bot_dir, "requirements.txt")
        
        if not os.path.exists(req_file):
            return True, "No requirements.txt found"
        
        result = subprocess.run(
            ["pip", "install", "-r", req_file],
            capture_output=True,
            text=True,
            cwd=bot_dir
        )
        
        if result.returncode == 0:
            return True, "Dependencies installed successfully"
        else:
            logger.error(f"Pip error: {result.stderr}")
            return False, f"Failed to install dependencies:\n{result.stderr}"
            
    except Exception as e:
        logger.error(f"Install error: {e}")
        return False, f"Error: {str(e)}"

def find_main_python_file(bot_dir):
    """Find main Python file in directory"""
    for file in os.listdir(bot_dir):
        if file.endswith('.py'):
            file_path = os.path.join(bot_dir, file)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if 'bot_token' in content or 'Updater' in content or 'Application' in content or 'import telegram' in content:
                        return file
            except Exception as e:
                logger.error(f"Error reading {file}: {e}")
                continue
    
    for file in os.listdir(bot_dir):
        if file.endswith('.py'):
            return file
    
    return None

def start_bot_process(bot_name):
    """Start bot as background process"""
    try:
        bot_dir = os.path.join(HOSTING_DIR, bot_name)
        
        if not os.path.exists(bot_dir):
            return False, f"Bot directory not found: {bot_dir}"
        
        main_file = find_main_python_file(bot_dir)
        
        if not main_file:
            return False, "No Python file found in bot directory"
        
        main_path = os.path.join(bot_dir, main_file)
        log_file = os.path.join(bot_dir, "bot.log")
        
        process = subprocess.Popen(
            [sys.executable, main_path],
            stdout=open(log_file, 'a'),
            stderr=subprocess.STDOUT,
            cwd=bot_dir
        )
        
        pid_file = os.path.join(bot_dir, "bot.pid")
        with open(pid_file, 'w') as f:
            f.write(str(process.pid))
        
        # Update upload status
        data = load_data()
        for upload in data["uploads"]:
            if upload["bot_name"] == bot_name:
                upload["status"] = "running"
                upload["pid"] = process.pid
                upload["start_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                break
        save_data(data)
        
        logger.info(f"Bot {bot_name} started with PID: {process.pid}")
        return True, f"✅ Bot started successfully!\n\n📁 Bot: `{bot_name}`\n📄 Main File: `{main_file}`\n🆔 PID: `{process.pid}`\n⏰ Started at: `{datetime.now().strftime('%H:%M:%S')}`"
        
    except Exception as e:
        logger.error(f"Error starting bot {bot_name}: {e}")
        return False, f"❌ Error starting bot: {str(e)}"

def stop_bot_process(bot_name):
    """Stop running bot"""
    try:
        bot_dir = os.path.join(HOSTING_DIR, bot_name)
        pid_file = os.path.join(bot_dir, "bot.pid")
        
        if not os.path.exists(pid_file):
            return False, "Bot is not running"
        
        with open(pid_file, 'r') as f:
            pid = int(f.read().strip())
        
        os.system(f"kill {pid} 2>/dev/null")
        
        if os.path.exists(pid_file):
            os.remove(pid_file)
        
        # Update upload status
        data = load_data()
        for upload in data["uploads"]:
            if upload["bot_name"] == bot_name:
                upload["status"] = "stopped"
                upload["stop_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                break
        save_data(data)
        
        logger.info(f"Bot {bot_name} stopped (PID: {pid})")
        return True, f"✅ Bot `{bot_name}` stopped successfully"
        
    except Exception as e:
        logger.error(f"Error stopping bot {bot_name}: {e}")
        return False, f"❌ Error stopping bot: {str(e)}"

def get_bot_status(bot_name):
    """Get bot status"""
    try:
        bot_dir = os.path.join(HOSTING_DIR, bot_name)
        pid_file = os.path.join(bot_dir, "bot.pid")
        
        if not os.path.exists(bot_dir):
            return "❌ Not found"
        
        if os.path.exists(pid_file):
            with open(pid_file, 'r') as f:
                pid = int(f.read().strip())
            
            try:
                os.kill(pid, 0)
                return "🟢 Running"
            except:
                return "🔴 Stopped (PID exists)"
        else:
            return "🔴 Stopped"
            
    except Exception as e:
        logger.error(f"Error getting status for {bot_name}: {e}")
        return "⚠️ Error"

def list_hosted_bots(user_id=None):
    """List all hosted bots"""
    bots = []
    if os.path.exists(HOSTING_DIR):
        for item in os.listdir(HOSTING_DIR):
            bot_dir = os.path.join(HOSTING_DIR, item)
            if os.path.isdir(bot_dir):
                if user_id:
                    # Check if this bot belongs to user
                    uploads = get_user_uploads(user_id)
                    user_bots = [upload["bot_name"] for upload in uploads]
                    if item in user_bots:
                        status = get_bot_status(item)
                        bots.append((item, status))
                else:
                    status = get_bot_status(item)
                    bots.append((item, status))
    return bots

def get_bot_stats():
    """Get bot statistics"""
    total_bots = len(list_hosted_bots())
    running_bots = len([b for b in list_hosted_bots() if "Running" in b[1]])
    stopped_bots = total_bots - running_bots
    
    data = load_data()
    total_users = len(data["users"])
    total_uploads = len(data["uploads"])
    
    return {
        "total_bots": total_bots,
        "running_bots": running_bots,
        "stopped_bots": stopped_bots,
        "total_users": total_users,
        "total_uploads": total_uploads
    }

# ================== KEYBOARDS ==================

def get_main_keyboard(user_id):
    """Get main menu keyboard based on user role"""
    if is_admin(user_id):
        keyboard = [
            [KeyboardButton("🤖 My Bots"), KeyboardButton("📤 Upload Bot")],
            [KeyboardButton("📊 Stats"), KeyboardButton("🛠️ Admin Panel")],
            [KeyboardButton("📝 Help"), KeyboardButton("ℹ️ About")]
        ]
    else:
        keyboard = [
            [KeyboardButton("🤖 My Bots"), KeyboardButton("📤 Upload Bot")],
            [KeyboardButton("📊 Stats"), KeyboardButton("📞 Contact Admin")],
            [KeyboardButton("📝 Help"), KeyboardButton("ℹ️ About")]
        ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_admin_keyboard():
    """Get admin panel keyboard"""
    keyboard = [
        [InlineKeyboardButton("👥 All Users", callback_data="admin_all_users")],
        [InlineKeyboardButton("📦 All Uploads", callback_data="admin_all_uploads")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="admin_settings")],
        [InlineKeyboardButton("📊 Statistics", callback_data="admin_stats")],
        [InlineKeyboardButton("❌ Close", callback_data="admin_close")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_user_management_keyboard(user_id):
    """Get user management keyboard"""
    user = get_user(user_id)
    if user:
        ban_text = "🚫 Unban User" if user.get("is_banned") else "⛔ Ban User"
        premium_text = "⭐ Remove Premium" if user.get("is_premium") else "🌟 Make Premium"
        
        keyboard = [
            [InlineKeyboardButton(ban_text, callback_data=f"admin_toggle_ban_{user_id}")],
            [InlineKeyboardButton(premium_text, callback_data=f"admin_toggle_premium_{user_id}")],
            [InlineKeyboardButton("💬 Message User", callback_data=f"admin_message_{user_id}")],
            [InlineKeyboardButton("📋 User Info", callback_data=f"admin_info_{user_id}")],
            [InlineKeyboardButton("🔙 Back", callback_data="admin_all_users")]
        ]
        return InlineKeyboardMarkup(keyboard)
    return None

def get_bots_keyboard(bots, page=0, bots_per_page=5):
    """Get paginated bots keyboard"""
    start_idx = page * bots_per_page
    end_idx = start_idx + bots_per_page
    page_bots = bots[start_idx:end_idx]
    
    keyboard = []
    for bot_name, status in page_bots:
        keyboard.append([InlineKeyboardButton(f"{bot_name} - {status}", callback_data=f"bot_{bot_name}")])
    
    # Navigation buttons
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"bots_page_{page-1}"))
    if end_idx < len(bots):
        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"bots_page_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")])
    
    return InlineKeyboardMarkup(keyboard)

def get_bot_actions_keyboard(bot_name, user_id):
    """Get bot actions keyboard"""
    keyboard = []
    
    # Check bot status
    status = get_bot_status(bot_name)
    
    if "Running" in status:
        keyboard.append([InlineKeyboardButton("🛑 Stop Bot", callback_data=f"stop_{bot_name}")])
    else:
        keyboard.append([InlineKeyboardButton("🚀 Start Bot", callback_data=f"start_{bot_name}")])
    
    keyboard.extend([
        [InlineKeyboardButton("📊 Status", callback_data=f"status_{bot_name}")],
        [InlineKeyboardButton("📋 Logs", callback_data=f"logs_{bot_name}")],
        [InlineKeyboardButton("🗑️ Delete", callback_data=f"delete_{bot_name}")],
        [InlineKeyboardButton("🔙 Back to My Bots", callback_data="my_bots")]
    ])
    
    # Admin extra buttons
    if is_admin(user_id):
        keyboard.append([InlineKeyboardButton("👁️ View Owner", callback_data=f"owner_{bot_name}")])
    
    return InlineKeyboardMarkup(keyboard)

# ================== BOT COMMAND HANDLERS ==================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user_id = update.effective_user.id
    username = update.effective_user.username
    first_name = update.effective_user.first_name
    
    # Add user to database
    is_new = add_user(user_id, username, first_name)
    
    welcome_text = f"""
{'🎉 Welcome to Bot Hosting System!' if is_new else '👋 Welcome back!'}

🤖 *Universal Bot Hosting System*

*Features:*
• Upload & Host Telegram Bots
• Start/Stop Bots Remotely
• View Bot Logs
• Auto Install Dependencies
• Admin Monitoring Panel
• User Management

📁 *Hosting Directory:* `{HOSTING_DIR}`
👤 *Your ID:* `{user_id}`
{'🎯 *Status:* ADMIN' if is_admin(user_id) else '👤 *Status:* USER'}
"""
    
    if is_admin(user_id):
        welcome_text += "\n🔐 *Admin Panel:* Available - Use Admin Panel button"
    
    await update.message.reply_text(
        welcome_text,
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(user_id)
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle help command"""
    user_id = update.effective_user.id
    
    help_text = """
🤖 *Bot Hosting System Help*

*Basic Commands:*
• 🤖 My Bots - View your hosted bots
• 📤 Upload Bot - Upload new bot file
• 📊 Stats - View system statistics
• 📝 Help - Show this help

*For Uploaded Bots:*
• 🚀 Start - Start a bot
• 🛑 Stop - Stop a bot
• 📊 Status - Check bot status
• 📋 Logs - View bot logs
• 🗑️ Delete - Delete a bot

*Admin Features:*
• 👥 User Management
• 📦 View All Uploads
• 📢 Broadcast Messages
• ⚙️ System Settings

*Upload Instructions:*
1. Click 'Upload Bot'
2. Send Python (.py) file
3. Enter bot name
4. Confirm upload
5. Bot will auto-install dependencies

*Notes:*
• Only Python files accepted
• Max file size: 10MB
• Bots run in background
• Logs available for 7 days
"""
    
    await update.message.reply_text(
        help_text,
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(user_id)
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle stats command"""
    user_id = update.effective_user.id
    
    stats = get_bot_stats()
    user_bots = list_hosted_bots(user_id)
    
    response = f"""
📊 *System Statistics*

*Global Stats:*
• 🤖 Total Bots: `{stats['total_bots']}`
• 🟢 Running: `{stats['running_bots']}`
• 🔴 Stopped: `{stats['stopped_bots']}`
• 👥 Total Users: `{stats['total_users']}`
• 📦 Total Uploads: `{stats['total_uploads']}`

*Your Stats:*
• 📁 Your Bots: `{len(user_bots)}`
"""
    
    if user_bots:
        running = len([b for b in user_bots if "Running" in b[1]])
        response += f"• 🟢 Running: `{running}`\n"
        response += f"• 🔴 Stopped: `{len(user_bots) - running}`"
    
    await update.message.reply_text(
        response,
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(user_id)
    )

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle about command"""
    about_text = """
🤖 *Universal Bot Hosting System*

*Version:* 2.0
*Developer:* @YourUsername
*Platform:* Telegram Bot API

*Features:*
• Multi-user Support
• Admin Dashboard
• Bot Management
• File Upload System
• Log Monitoring
• Auto Dependency Install

*Technical Details:*
• Language: Python 3
• Framework: python-telegram-bot
• Hosting: Termux/Linux
• Storage: Local Filesystem

*Contact:*
For support or queries, use 'Contact Admin' button.

⚡ *Powered by Python-Telegram-Bot*
"""
    
    await update.message.reply_text(
        about_text,
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(update.effective_user.id)
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages from keyboard"""
    user_id = update.effective_user.id
    text = update.message.text
    
    if not is_user_allowed(user_id):
        await update.message.reply_text(
            "⛔ Your account has been banned. Contact admin for support.",
            reply_markup=ReplyKeyboardRemove()
        )
        return
    
    if text == "🤖 My Bots":
        await show_my_bots(update, context)
    
    elif text == "📤 Upload Bot":
        await update.message.reply_text(
            "📤 *Upload Bot*\n\nPlease send me a Python (.py) file.\n"
            "I'll guide you through the upload process.\n\n"
            "Max file size: 10MB",
            parse_mode="Markdown"
        )
        return UPLOAD
    
    elif text == "📊 Stats":
        await stats_command(update, context)
    
    elif text == "🛠️ Admin Panel" and is_admin(user_id):
        await show_admin_panel(update, context)
    
    elif text == "📞 Contact Admin":
        await update.message.reply_text(
            "💬 *Contact Admin*\n\nPlease type your message to admin.\n"
            "I'll forward it immediately.\n\n"
            "Type /cancel to cancel.",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("❌ Cancel")]], resize_keyboard=True)
        )
        return USER_MESSAGE
    
    elif text == "📝 Help":
        await help_command(update, context)
    
    elif text == "ℹ️ About":
        await about_command(update, context)
    
    elif text == "❌ Cancel":
        await update.message.reply_text(
            "Operation cancelled.",
            reply_markup=get_main_keyboard(user_id)
        )
        return ConversationHandler.END

async def show_my_bots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's bots"""
    user_id = update.effective_user.id
    bots = list_hosted_bots(user_id)
    
    if not bots:
        await update.message.reply_text(
            "📭 You haven't uploaded any bots yet.\n\n"
            "Use '📤 Upload Bot' to upload your first bot!",
            reply_markup=get_main_keyboard(user_id)
        )
        return
    
    await update.message.reply_text(
        f"🤖 *Your Bots* ({len(bots)} total)\n\n"
        "Click on a bot to manage it:",
        parse_mode="Markdown",
        reply_markup=get_bots_keyboard(bots)
    )

async def show_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin panel"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Access denied.")
        return
    
    stats = get_bot_stats()
    
    admin_text = f"""
🛠️ *Admin Control Panel*

*System Status:*
• 🤖 Bots: {stats['total_bots']} ({stats['running_bots']} running)
• 👥 Users: {stats['total_users']}
• 📦 Uploads: {stats['total_uploads']}
• 💾 Storage: Checking...

*Quick Actions:*
1. View all users
2. Monitor uploads
3. Send broadcast
4. System settings

Select an option below:
"""
    
    await update.message.reply_text(
        admin_text,
        parse_mode="Markdown",
        reply_markup=get_admin_keyboard()
    )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle document uploads"""
    user_id = update.effective_user.id
    
    if not is_user_allowed(user_id):
        await update.message.reply_text("⛔ Your account has been banned.")
        return ConversationHandler.END
    
    document = update.message.document
    if not document:
        return UPLOAD
    
    file_size_mb = document.file_size / (1024 * 1024)
    
    # Check file size
    if file_size_mb > 10:
        await update.message.reply_text(
            f"❌ File too large! Max size is 10MB.\n"
            f"Your file: {file_size_mb:.1f}MB\n\n"
            "Please upload a smaller file."
        )
        return UPLOAD
    
    file_name = document.file_name
    
    # Check if it's a Python file
    if not file_name.endswith('.py'):
        await update.message.reply_text(
            "❌ Please send only Python (.py) files.\n\n"
            "Try again with a .py file:"
        )
        return UPLOAD
    
    # Store file info
    context.user_data['upload_file'] = {
        'file_id': document.file_id,
        'file_name': file_name,
        'file_size': document.file_size
    }
    
    # Suggest bot name
    bot_name = file_name.replace('.py', '').replace(' ', '_').replace('.', '_')
    
    await update.message.reply_text(
        f"📄 *File Received:* `{file_name}`\n"
        f"📦 *Size:* {file_size_mb:.1f}MB\n\n"
        f"Please enter a name for your bot:\n"
        f"(Suggested: `{bot_name}`)\n\n"
        "Type /cancel to cancel.",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton("❌ Cancel")]], resize_keyboard=True)
    )
    
    return BOT_NAME

async def handle_bot_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle bot name input"""
    user_id = update.effective_user.id
    bot_name = update.message.text.strip()
    
    # Validate bot name
    if not bot_name.replace('_', '').isalnum():
        await update.message.reply_text(
            "❌ Invalid bot name! Use only letters, numbers and underscores.\n"
            "Please enter a valid name:"
        )
        return BOT_NAME
    
    # Check if bot name exists
    bot_dir = os.path.join(HOSTING_DIR, bot_name)
    if os.path.exists(bot_dir):
        await update.message.reply_text(
            f"❌ Bot name `{bot_name}` already exists!\n"
            "Please choose a different name:"
        )
        return BOT_NAME
    
    # Store bot name
    context.user_data['upload_file']['bot_name'] = bot_name
    
    await update.message.reply_text(
        f"📝 *Bot Name:* `{bot_name}`\n"
        f"📄 *File:* `{context.user_data['upload_file']['file_name']}`\n\n"
        "Do you want to proceed with upload?\n\n"
        "✅ Yes - Upload and install\n"
        "❌ No - Cancel upload",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup([
            [KeyboardButton("✅ Yes"), KeyboardButton("❌ No")]
        ], resize_keyboard=True)
    )
    
    return CONFIRM

async def handle_upload_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle upload confirmation"""
    user_id = update.effective_user.id
    text = update.message.text
    
    if text == "❌ No":
        await update.message.reply_text(
            "Upload cancelled.",
            reply_markup=get_main_keyboard(user_id)
        )
        context.user_data.clear()
        return ConversationHandler.END
    
    if text != "✅ Yes":
        return CONFIRM
    
    file_info = context.user_data['upload_file']
    
    await update.message.reply_text(
        "⏳ Downloading file...",
        reply_markup=ReplyKeyboardRemove()
    )
    
    # Save file
    file_path, success, file_size = await save_file(
        file_info['file_id'],
        context.bot,
        file_info['bot_name'],
        file_info['file_name']
    )
    
    if not success:
        await update.message.reply_text(
            "❌ Failed to download file. Please try again.",
            reply_markup=get_main_keyboard(user_id)
        )
        context.user_data.clear()
        return ConversationHandler.END
    
    # Add to upload history
    add_upload(
        user_id,
        file_info['bot_name'],
        file_info['file_name'],
        file_size
    )
    
    # Install dependencies
    await update.message.reply_text("📦 Checking for dependencies...")
    dep_success, dep_msg = install_dependencies(file_info['bot_name'])
    
    # Auto start if admin and setting enabled
    auto_start = is_admin(user_id)  # Admin only auto-start for now
    
    if auto_start:
        await update.message.reply_text("🚀 Auto-starting bot...")
        start_success, start_msg = start_bot_process(file_info['bot_name'])
    
    response = f"""
✅ *Bot Uploaded Successfully!*

📁 *Bot Name:* `{file_info['bot_name']}`
📄 *File:* `{file_info['file_name']}`
📍 *Location:* `{file_path}`
👤 *Uploaded by:* {'Admin' if is_admin(user_id) else 'User'}

"""
    
    if dep_success:
        response += f"📦 *Dependencies:* ✅ Installed\n"
    else:
        response += f"📦 *Dependencies:* ⚠️ {dep_msg}\n"
    
    if auto_start:
        if start_success:
            response += f"🚀 *Status:* ✅ Auto-started\n"
        else:
            response += f"🚀 *Status:* ❌ Auto-start failed\n"
    
    response += f"\n📊 Use '🤖 My Bots' to manage your bot"
    
    # Notify admin about new upload
    if not is_admin(user_id):
        user = get_user(user_id)
        admin_msg = f"""
📤 *New Bot Uploaded*

👤 *User:* {user['first_name']} (@{user['username']})
🆔 *User ID:* `{user_id}`
🤖 *Bot Name:* `{file_info['bot_name']}`
📄 *File:* `{file_info['file_name']}`
📦 *Size:* {file_size/(1024*1024):.1f}MB

📊 Total user uploads: {user['uploads']}
"""
        try:
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=admin_msg,
                parse_mode="Markdown"
            )
        except:
            pass
    
    await update.message.reply_text(
        response,
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(user_id)
    )
    
    context.user_data.clear()
    return ConversationHandler.END

async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle user messages to admin"""
    user_id = update.effective_user.id
    message_text = update.message.text
    
    if message_text == "❌ Cancel":
        await update.message.reply_text(
            "Message cancelled.",
            reply_markup=get_main_keyboard(user_id)
        )
        return ConversationHandler.END
    
    # Save message
    msg_id = add_message(user_id, ADMIN_CHAT_ID, message_text, False)
    
    # Forward to admin
    user = get_user(user_id)
    admin_msg = f"""
💬 *New Message from User*

🆔 *Message ID:* `{msg_id}`
👤 *From:* {user['first_name']} (@{user['username']})
🆔 *User ID:* `{user_id}`
📅 *Time:* {datetime.now().strftime('%H:%M:%S')}

📝 *Message:*
{message_text}

💬 *Reply with:* `/reply {user_id} <your message>`
"""
    
    try:
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=admin_msg,
            parse_mode="Markdown"
        )
        
        await update.message.reply_text(
            "✅ Your message has been sent to admin!\n"
            "You will receive a reply soon.",
            reply_markup=get_main_keyboard(user_id)
        )
    except:
        await update.message.reply_text(
            "❌ Failed to send message. Please try again later.",
            reply_markup=get_main_keyboard(user_id)
        )
    
    return ConversationHandler.END

async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin reply to user"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Admin only command.")
        return
    
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "Usage: /reply <user_id> <message>\n\n"
            "Example: /reply 123456789 Hello there!"
        )
        return
    
    target_user_id = int(context.args[0])
    reply_text = ' '.join(context.args[1:])
    
    # Save message
    msg_id = add_message(user_id, target_user_id, reply_text, True)
    
    # Send to user
    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"💌 *Message from Admin*\n\n{reply_text}\n\n📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            parse_mode="Markdown"
        )
        
        await update.message.reply_text(
            f"✅ Reply sent to user {target_user_id}\n"
            f"Message ID: {msg_id}"
        )
    except Exception as e:
        await update.message.reply_text(
            f"❌ Failed to send message: {str(e)}\n"
            "User may have blocked the bot."
        )

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback queries"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    data = query.data
    
    # Admin Panel Callbacks
    if data == "admin_panel":
        await show_admin_panel_from_callback(query)
    
    elif data == "admin_all_users":
        await show_all_users(query)
    
    elif data == "admin_all_uploads":
        await show_all_uploads(query)
    
    elif data == "admin_broadcast":
        await query.edit_message_text(
            "📢 *Broadcast Message*\n\n"
            "Please send the broadcast message:\n"
            "(Supports Markdown formatting)\n\n"
            "Type /cancel to cancel.",
            parse_mode="Markdown"
        )
        # We'll handle this differently
        context.user_data['awaiting_broadcast'] = True
        await query.message.reply_text(
            "Please type your broadcast message:",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("❌ Cancel")]], resize_keyboard=True)
        )
        return
    
    elif data == "admin_stats":
        await show_admin_stats(query)
    
    elif data == "admin_settings":
        await show_admin_settings(query)
    
    elif data == "admin_close":
        await query.delete_message()
    
    # User Management
    elif data.startswith("admin_user_"):
        user_id_to_manage = int(data.split("_")[-1])
        await show_user_management(query, user_id_to_manage)
    
    elif data.startswith("admin_toggle_ban_"):
        target_user_id = int(data.split("_")[-1])
        await toggle_user_ban(query, target_user_id)
    
    elif data.startswith("admin_toggle_premium_"):
        target_user_id = int(data.split("_")[-1])
        await toggle_user_premium(query, target_user_id)
    
    elif data.startswith("admin_message_"):
        target_user_id = int(data.split("_")[-1])
        await query.edit_message_text(
            f"💬 *Message User*\n\n"
            f"User ID: `{target_user_id}`\n"
            f"Send your message:\n\n"
            f"Type /cancel to cancel.",
            parse_mode="Markdown"
        )
        context.user_data['reply_to_user'] = target_user_id
        # We'll handle the reply in handle_message function
        await query.message.reply_text(
            f"Please type your message for user {target_user_id}:",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("❌ Cancel")]], resize_keyboard=True)
        )
        return
    
    elif data.startswith("admin_info_"):
        target_user_id = int(data.split("_")[-1])
        await show_user_info(query, target_user_id)
    
    # Bot Management
    elif data == "my_bots":
        await show_my_bots_callback(query)
    
    elif data == "back_to_menu":
        await query.edit_message_text(
            "Main Menu",
            reply_markup=get_main_keyboard(user_id)
        )
    
    elif data.startswith("bots_page_"):
        page = int(data.split("_")[-1])
        bots = list_hosted_bots(user_id)
        await query.edit_message_reply_markup(get_bots_keyboard(bots, page))
    
    elif data.startswith("bot_"):
        bot_name = data[4:]
        await show_bot_actions(query, bot_name)
    
    elif data.startswith("start_"):
        bot_name = data[6:]
        await start_bot_callback(query, bot_name)
    
    elif data.startswith("stop_"):
        bot_name = data[5:]
        await stop_bot_callback(query, bot_name)
    
    elif data.startswith("status_"):
        bot_name = data[7:]
        await show_bot_status(query, bot_name)
    
    elif data.startswith("logs_"):
        bot_name = data[5:]
        await show_bot_logs(query, bot_name)
    
    elif data.startswith("delete_"):
        bot_name = data[7:]
        await delete_bot_callback(query, bot_name)
    
    elif data.startswith("owner_"):
        bot_name = data[6:]
        await show_bot_owner(query, bot_name)

async def show_admin_panel_from_callback(update: Update):
    """Show admin panel from callback"""
    query = update if hasattr(update, 'callback_query') else None
    if query:
        await query.answer()
        user_id = query.from_user.id
    else:
        return
    
    if not is_admin(user_id):
        await query.edit_message_text("❌ Access denied.")
        return
    
    stats = get_bot_stats()
    
    admin_text = f"""
🛠️ *Admin Control Panel*

*System Status:*
• 🤖 Bots: {stats['total_bots']} ({stats['running_bots']} running)
• 👥 Users: {stats['total_users']}
• 📦 Uploads: {stats['total_uploads']}
• 💾 Storage: Checking...

*Quick Actions:*
1. View all users
2. Monitor uploads
3. Send broadcast
4. System settings

Select an option below:
"""
    
    await query.edit_message_text(
        admin_text,
        parse_mode="Markdown",
        reply_markup=get_admin_keyboard()
    )

async def show_all_users(query):
    """Show all users to admin"""
    users = get_all_users()
    
    if not users:
        await query.edit_message_text("📭 No users found.")
        return
    
    response = "👥 *All Users*\n\n"
    keyboard = []
    
    for uid, user_data in list(users.items())[:50]:  # Show first 50
        status = ""
        if user_data.get("is_banned"):
            status += "⛔ "
        if user_data.get("is_premium"):
            status += "⭐ "
        
        response += f"• {status}{user_data['first_name']} (@{user_data['username']})\n"
        response += f"  🆔: `{uid}` | 📅: {user_data['join_date']}\n"
        response += f"  📦: {user_data.get('uploads', 0)} uploads\n\n"
        
        keyboard.append([InlineKeyboardButton(
            f"{user_data['first_name']} (@{user_data['username']})",
            callback_data=f"admin_user_{uid}"
        )])
    
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="admin_panel")])
    
    await query.edit_message_text(
        response,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def show_all_uploads(query):
    """Show all uploads to admin"""
    uploads = get_all_uploads()
    
    if not uploads:
        await query.edit_message_text("📭 No uploads found.")
        return
    
    response = "📦 *All Uploads*\n\n"
    
    for upload in uploads[-20:]:  # Show last 20
        user = get_user(upload["user_id"])
        username = user['username'] if user else "Unknown"
        
        response += f"• 🤖 `{upload['bot_name']}`\n"
        response += f"  📄 {upload['file_name']}\n"
        response += f"  👤 {username} | 🕒 {upload['upload_time']}\n"
        response += f"  📊 {upload['status'].upper()} | 📦 {upload['file_size']/(1024*1024):.1f}MB\n\n"
    
    response += f"Total: {len(uploads)} uploads"
    
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="admin_panel")]]
    
    await query.edit_message_text(
        response,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def show_admin_stats(query):
    """Show detailed admin statistics"""
    stats = get_bot_stats()
    users = get_all_users()
    
    active_users = sum(1 for u in users.values() if not u.get("is_banned", False))
    banned_users = sum(1 for u in users.values() if u.get("is_banned", False))
    premium_users = sum(1 for u in users.values() if u.get("is_premium", False))
    
    # Calculate storage usage
    total_size = 0
    if os.path.exists(HOSTING_DIR):
        for root, dirs, files in os.walk(HOSTING_DIR):
            for f in files:
                fp = os.path.join(root, f)
                total_size += os.path.getsize(fp)
    
    response = f"""
📊 *Admin Statistics*

🤖 *Bot Statistics:*
• Total Bots: `{stats['total_bots']}`
• Running: `{stats['running_bots']}`
• Stopped: `{stats['stopped_bots']}`

👥 *User Statistics:*
• Total Users: `{stats['total_users']}`
• Active: `{active_users}`
• Banned: `{banned_users}`
• Premium: `{premium_users}`

📦 *Upload Statistics:*
• Total Uploads: `{stats['total_uploads']}`
• Storage Used: `{total_size/(1024*1024):.1f}MB`

📈 *Recent Activity:*
• Last Hour: Checking...
• Today: Checking...
• This Week: Checking...
"""
    
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="admin_panel")]]
    
    await query.edit_message_text(
        response,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def show_admin_settings(query):
    """Show admin settings"""
    data = load_data()
    settings = data["settings"]
    
    response = f"""
⚙️ *Admin Settings*

*Current Settings:*
• Allow User Upload: `{'✅ Yes' if settings['allow_user_upload'] else '❌ No'}`
• Max File Size: `{settings['max_file_size_mb']}MB`
• Auto Start Bot: `{'✅ Yes' if settings['auto_start_bot'] else '❌ No'}`

*Quick Actions:*
1. Toggle user upload
2. Change file size limit
3. Toggle auto-start
"""
    
    keyboard = [
        [
            InlineKeyboardButton(
                "Toggle User Upload",
                callback_data="toggle_upload"
            )
        ],
        [
            InlineKeyboardButton(
                "Toggle Auto-Start",
                callback_data="toggle_autostart"
            )
        ],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_panel")]
    ]
    
    await query.edit_message_text(
        response,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def show_user_management(query, target_user_id):
    """Show user management options"""
    user = get_user(target_user_id)
    
    if not user:
        await query.answer("User not found!")
        return
    
    response = f"""
👤 *User Management*

*User Info:*
• Name: {user['first_name']}
• Username: @{user['username']}
• ID: `{target_user_id}`
• Joined: {user['join_date']}
• Uploads: {user.get('uploads', 0)}
• Status: {'⛔ Banned' if user.get('is_banned') else '✅ Active'}
• Premium: {'⭐ Yes' if user.get('is_premium') else '❌ No'}

*Actions:*
• Ban/Unban user
• Grant/Remove premium
• Send message
• View details
"""
    
    await query.edit_message_text(
        response,
        parse_mode="Markdown",
        reply_markup=get_user_management_keyboard(target_user_id)
    )

async def toggle_user_ban(query, target_user_id):
    """Toggle user ban status"""
    user = get_user(target_user_id)
    
    if not user:
        await query.answer("User not found!")
        return
    
    new_status = not user.get("is_banned", False)
    update_user_status(target_user_id, is_banned=new_status)
    
    status_text = "banned" if new_status else "unbanned"
    
    # Notify user if unbanned
    if not new_status:
        try:
            await query.bot.send_message(
                chat_id=target_user_id,
                text="✅ Your account has been unbanned. You can now use the bot again."
            )
        except:
            pass
    
    await query.answer(f"User {status_text}!")
    await show_user_management(query, target_user_id)

async def toggle_user_premium(query, target_user_id):
    """Toggle user premium status"""
    user = get_user(target_user_id)
    
    if not user:
        await query.answer("User not found!")
        return
    
    new_status = not user.get("is_premium", False)
    update_user_status(target_user_id, is_premium=new_status)
    
    status_text = "granted premium" if new_status else "removed premium from"
    
    # Notify user
    try:
        if new_status:
            await query.bot.send_message(
                chat_id=target_user_id,
                text="🎉 You have been granted premium status! Thank you for your support!"
            )
        else:
            await query.bot.send_message(
                chat_id=target_user_id,
                text="ℹ️ Your premium status has been removed."
            )
    except:
        pass
    
    await query.answer(f"User {status_text}!")
    await show_user_management(query, target_user_id)

async def show_user_info(query, target_user_id):
    """Show detailed user information"""
    user = get_user(target_user_id)
    
    if not user:
        await query.answer("User not found!")
        return
    
    uploads = get_user_uploads(target_user_id)
    user_bots = list_hosted_bots(target_user_id)
    
    response = f"""
📋 *User Information*

*Basic Info:*
• 👤 Name: {user['first_name']}
• @ Username: @{user['username']}
• 🆔 ID: `{target_user_id}`
• 📅 Joined: {user['join_date']}
• 📍 Last Active: {user.get('last_active', 'Never')}
• ⚠️ Status: {'⛔ Banned' if user.get('is_banned') else '✅ Active'}
• ⭐ Premium: {'✅ Yes' if user.get('is_premium') else '❌ No'}

*Statistics:*
• 📦 Total Uploads: {user.get('uploads', 0)}
• 🤖 Active Bots: {len([b for b in user_bots if 'Running' in b[1]])}
• 🔴 Stopped Bots: {len([b for b in user_bots if 'Stopped' in b[1]])}

*Recent Uploads:*
"""
    
    for upload in uploads[-5:]:
        response += f"• `{upload['bot_name']}` - {upload['upload_time']}\n"
    
    keyboard = [
        [InlineKeyboardButton("💬 Message User", callback_data=f"admin_message_{target_user_id}")],
        [InlineKeyboardButton("🔙 Back", callback_data=f"admin_user_{target_user_id}")]
    ]
    
    await query.edit_message_text(
        response,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def show_my_bots_callback(query):
    """Show user's bots via callback"""
    user_id = query.from_user.id
    bots = list_hosted_bots(user_id)
    
    if not bots:
        await query.edit_message_text(
            "📭 You haven't uploaded any bots yet.\n\n"
            "Use '📤 Upload Bot' to upload your first bot!"
        )
        return
    
    await query.edit_message_text(
        f"🤖 *Your Bots* ({len(bots)} total)\n\n"
        "Click on a bot to manage it:",
        parse_mode="Markdown",
        reply_markup=get_bots_keyboard(bots)
    )

async def show_bot_actions(query, bot_name):
    """Show actions for a specific bot"""
    user_id = query.from_user.id
    
    # Check if user owns this bot
    user_bots = [b[0] for b in list_hosted_bots(user_id)]
    if bot_name not in user_bots and not is_admin(user_id):
        await query.answer("❌ You don't have permission to manage this bot!")
        return
    
    status = get_bot_status(bot_name)
    bot_dir = os.path.join(HOSTING_DIR, bot_name)
    
    # Get bot info
    main_file = find_main_python_file(bot_dir)
    log_file = os.path.join(bot_dir, "bot.log")
    
    response = f"""
🤖 *Bot: {bot_name}*

*Status:* {status}
*Main File:* `{main_file}`

*Actions:*
• Start/Stop bot
• Check status
• View logs
• Delete bot
"""
    
    if is_admin(user_id):
        # Get upload info for admin
        uploads = get_all_uploads()
        for upload in uploads:
            if upload['bot_name'] == bot_name:
                user = get_user(upload['user_id'])
                response += f"\n*Owner:* {user['first_name']} (@{user['username']})"
                response += f"\n*Uploaded:* {upload['upload_time']}"
                break
    
    await query.edit_message_text(
        response,
        parse_mode="Markdown",
        reply_markup=get_bot_actions_keyboard(bot_name, user_id)
    )

async def start_bot_callback(query, bot_name):
    """Start bot via callback"""
    user_id = query.from_user.id
    
    # Check permission
    user_bots = [b[0] for b in list_hosted_bots(user_id)]
    if bot_name not in user_bots and not is_admin(user_id):
        await query.answer("❌ Permission denied!")
        return
    
    await query.answer("🚀 Starting bot...")
    
    success, message = start_bot_process(bot_name)
    
    if success:
        await query.edit_message_text(
            f"✅ Bot started successfully!\n\n{message}",
            parse_mode="Markdown",
            reply_markup=get_bot_actions_keyboard(bot_name, user_id)
        )
    else:
        await query.edit_message_text(
            f"❌ Failed to start bot:\n\n{message}",
            parse_mode="Markdown",
            reply_markup=get_bot_actions_keyboard(bot_name, user_id)
        )

async def stop_bot_callback(query, bot_name):
    """Stop bot via callback"""
    user_id = query.from_user.id
    
    # Check permission
    user_bots = [b[0] for b in list_hosted_bots(user_id)]
    if bot_name not in user_bots and not is_admin(user_id):
        await query.answer("❌ Permission denied!")
        return
    
    await query.answer("🛑 Stopping bot...")
    
    success, message = stop_bot_process(bot_name)
    
    if success:
        await query.edit_message_text(
            f"✅ Bot stopped successfully!\n\n{message}",
            parse_mode="Markdown",
            reply_markup=get_bot_actions_keyboard(bot_name, user_id)
        )
    else:
        await query.edit_message_text(
            f"❌ Failed to stop bot:\n\n{message}",
            parse_mode="Markdown",
            reply_markup=get_bot_actions_keyboard(bot_name, user_id)
        )

async def show_bot_status(query, bot_name):
    """Show detailed bot status"""
    status = get_bot_status(bot_name)
    bot_dir = os.path.join(HOSTING_DIR, bot_name)
    
    if not os.path.exists(bot_dir):
        await query.answer("❌ Bot not found!")
        return
    
    # Get detailed info
    main_file = find_main_python_file(bot_dir)
    req_file = os.path.join(bot_dir, "requirements.txt")
    log_file = os.path.join(bot_dir, "bot.log")
    pid_file = os.path.join(bot_dir, "bot.pid")
    
    response = f"""
📊 *Bot Status: {bot_name}*

*Current Status:* {status}
*Directory:* `{bot_dir}`
"""
    
    if main_file:
        response += f"*Main File:* `{main_file}`\n"
    
    if os.path.exists(req_file):
        with open(req_file, 'r') as f:
            req_count = len([l for l in f.readlines() if l.strip()])
        response += f"*Dependencies:* {req_count} packages\n"
    
    if os.path.exists(pid_file):
        with open(pid_file, 'r') as f:
            pid = f.read().strip()
        response += f"*Process ID:* `{pid}`\n"
    
    if os.path.exists(log_file):
        size_kb = os.path.getsize(log_file) / 1024
        mod_time = datetime.fromtimestamp(os.path.getmtime(log_file))
        response += f"*Log Size:* {size_kb:.1f} KB\n"
        response += f"*Log Updated:* {mod_time.strftime('%H:%M:%S')}\n"
    
    # Get upload info
    uploads = get_all_uploads()
    for upload in uploads:
        if upload['bot_name'] == bot_name:
            response += f"\n*Upload Info:*\n"
            response += f"• File: `{upload['file_name']}`\n"
            response += f"• Size: {upload['file_size']/(1024*1024):.1f}MB\n"
            response += f"• Time: {upload['upload_time']}\n"
            response += f"• Status: {upload['status']}\n"
            break
    
    await query.edit_message_text(
        response,
        parse_mode="Markdown",
        reply_markup=get_bot_actions_keyboard(bot_name, query.from_user.id)
    )

async def show_bot_logs(query, bot_name):
    """Show bot logs"""
    log_file = os.path.join(HOSTING_DIR, bot_name, "bot.log")
    
    if not os.path.exists(log_file):
        await query.edit_message_text(
            f"📭 No logs found for bot `{bot_name}`",
            parse_mode="Markdown",
            reply_markup=get_bot_actions_keyboard(bot_name, query.from_user.id)
        )
        return
    
    try:
        with open(log_file, 'r') as f:
            content = f.read()
        
        if not content:
            await query.edit_message_text(
                f"📭 Log file is empty for bot `{bot_name}`",
                parse_mode="Markdown",
                reply_markup=get_bot_actions_keyboard(bot_name, query.from_user.id)
            )
            return
        
        # Get last 100 lines
        lines = content.strip().split('\n')
        last_lines = lines[-100:] if len(lines) > 100 else lines
        content = '\n'.join(last_lines)
        
        # Truncate if still too long
        if len(content) > 3000:
            content = "...\n" + content[-3000:]
        
        response = f"""
📋 *Logs for {bot_name}*




	
*Note:* Showing last {len(last_lines)} lines
"""
        
        await query.edit_message_text(
            response,
            parse_mode="Markdown",
            reply_markup=get_bot_actions_keyboard(bot_name, query.from_user.id)
        )
    
    except Exception as e:
        await query.edit_message_text(
            f"❌ Error reading logs: {str(e)}",
            parse_mode="Markdown",
            reply_markup=get_bot_actions_keyboard(bot_name, query.from_user.id)
        )

async def delete_bot_callback(query, bot_name):
    """Delete bot via callback"""
    user_id = query.from_user.id
    
    # Check permission
    user_bots = [b[0] for b in list_hosted_bots(user_id)]
    if bot_name not in user_bots and not is_admin(user_id):
        await query.answer("❌ Permission denied!")
        return
    
    # Stop bot first
    stop_bot_process(bot_name)
    
    # Delete directory
    bot_dir = os.path.join(HOSTING_DIR, bot_name)
    if os.path.exists(bot_dir):
        shutil.rmtree(bot_dir)
        await query.edit_message_text(
            f"✅ Bot `{bot_name}` deleted successfully.\n\n"
            "All files and logs have been removed.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back to My Bots", callback_data="my_bots")]
            ])
        )
    else:
        await query.edit_message_text(
            f"❌ Bot `{bot_name}` not found.",
            parse_mode="Markdown",
            reply_markup=get_bot_actions_keyboard(bot_name, user_id)
        )

async def show_bot_owner(query, bot_name):
    """Show bot owner info (admin only)"""
    uploads = get_all_uploads()
    
    for upload in uploads:
        if upload['bot_name'] == bot_name:
            user = get_user(upload['user_id'])
            
            response = f"""
👤 *Bot Owner Information*

🤖 *Bot Name:* `{bot_name}`
📄 *File:* `{upload['file_name']}`
📦 *Size:* {upload['file_size']/(1024*1024):.1f}MB
🕒 *Uploaded:* {upload['upload_time']}
📊 *Status:* {upload['status']}

*Owner Info:*
• 👤 Name: {user['first_name']}
• @ Username: @{user['username']}
• 🆔 ID: `{upload['user_id']}`
• 📅 Joined: {user['join_date']}
• 📦 Total Uploads: {user.get('uploads', 0)}
• ⚠️ Status: {'⛔ Banned' if user.get('is_banned') else '✅ Active'}
"""
            
            keyboard = [
                [
                    InlineKeyboardButton(
                        "💬 Message User",
                        callback_data=f"admin_message_{upload['user_id']}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "👤 Manage User",
                        callback_data=f"admin_user_{upload['user_id']}"
                    )
                ],
                [InlineKeyboardButton("🔙 Back", callback_data=f"bot_{bot_name}")]
            ]
            
            await query.edit_message_text(
                response,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
    
    await query.answer("❌ Bot owner not found!")

async def handle_broadcast_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle broadcast message text"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Admin only.")
        return
    
    if 'awaiting_broadcast' not in context.user_data:
        return
    
    message_text = update.message.text
    
    if message_text == "❌ Cancel":
        await update.message.reply_text(
            "Broadcast cancelled.",
            reply_markup=get_main_keyboard(user_id)
        )
        context.user_data.clear()
        return
    
    # Get all users
    users = get_all_users()
    
    # Confirm broadcast
    keyboard = [
        [KeyboardButton("✅ Send Broadcast")],
        [KeyboardButton("❌ Cancel Broadcast")]
    ]
    
    await update.message.reply_text(
        f"📢 *Broadcast Confirmation*\n\n"
        f"Message:\n{message_text}\n\n"
        f"Recipients: {len(users)} users\n\n"
        f"Send this broadcast?",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    
    context.user_data['broadcast_message'] = message_text
    context.user_data['broadcast_confirmed'] = True

async def handle_broadcast_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle broadcast confirmation"""
    user_id = update.effective_user.id
    text = update.message.text
    
    if not is_admin(user_id):
        return
    
    if text == "❌ Cancel Broadcast":
        await update.message.reply_text(
            "Broadcast cancelled.",
            reply_markup=get_main_keyboard(user_id)
        )
        context.user_data.clear()
        return
    
    if text != "✅ Send Broadcast":
        return
    
    if 'broadcast_message' not in context.user_data:
        await update.message.reply_text("No broadcast message found.")
        return
    
    message_text = context.user_data['broadcast_message']
    users = get_all_users()
    
    await update.message.reply_text(
        f"📢 Sending broadcast to {len(users)} users...",
        reply_markup=ReplyKeyboardRemove()
    )
    
    success_count = 0
    fail_count = 0
    
    for uid, user_data in users.items():
        try:
            # Skip banned users
            if user_data.get("is_banned", False):
                continue
            
            await context.bot.send_message(
                chat_id=int(uid),
                text=f"📢 *Broadcast from Admin*\n\n{message_text}\n\n📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                parse_mode="Markdown"
            )
            success_count += 1
            
            # Small delay to avoid rate limiting
            time.sleep(0.1)
            
        except Exception as e:
            fail_count += 1
            logger.error(f"Failed to send broadcast to {uid}: {e}")
    
    # Save broadcast record
    add_message(user_id, 0, f"BROADCAST: {message_text[:50]}...", True)
    
    await update.message.reply_text(
        f"✅ Broadcast completed!\n\n"
        f"✅ Success: {success_count} users\n"
        f"❌ Failed: {fail_count} users\n"
        f"📊 Total: {len(users)} users",
        reply_markup=get_main_keyboard(user_id)
    )
    
    context.user_data.clear()

async def handle_admin_reply_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin reply to user"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Admin only.")
        return
    
    if 'reply_to_user' not in context.user_data:
        return
    
    target_user_id = context.user_data['reply_to_user']
    message_text = update.message.text
    
    if message_text == "❌ Cancel":
        await update.message.reply_text(
            "Message cancelled.",
            reply_markup=get_main_keyboard(user_id)
        )
        context.user_data.clear()
        return
    
    # Save message
    msg_id = add_message(user_id, target_user_id, message_text, True)
    
    # Send to user
    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"💌 *Message from Admin*\n\n{message_text}\n\n📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            parse_mode="Markdown"
        )
        
        await update.message.reply_text(
            f"✅ Message sent to user {target_user_id}\n"
            f"Message ID: {msg_id}",
            reply_markup=get_main_keyboard(user_id)
        )
    except Exception as e:
        await update.message.reply_text(
            f"❌ Failed to send message: {str(e)}\n"
            "User may have blocked the bot.",
            reply_markup=get_main_keyboard(user_id)
        )
    
    context.user_data.clear()

# ================== MAIN FUNCTION ==================

def main():
    """Start the bot"""
    print("🤖 Starting Universal Bot Hosting System v2.0...")
    print(f"📁 Hosting Directory: {HOSTING_DIR}")
    print(f"👤 Admin ID: {ADMIN_CHAT_ID}")
    print("⏳ Setting up...")
    
    # Setup hosting directory
    setup_hosting_directory()
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add conversation handlers
    upload_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^(📤 Upload Bot)$"), handle_message),
            CommandHandler("upload", lambda u, c: handle_message(u, c))  # Simplified
        ],
        states={
            UPLOAD: [MessageHandler(filters.Document.ALL, handle_document)],
            BOT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_bot_name)],
            CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_upload_confirm)]
        },
        fallbacks=[CommandHandler("cancel", start)],
        allow_reentry=True
    )
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("about", about_command))
    application.add_handler(CommandHandler("reply", handle_admin_reply))
    
    # Add conversation handlers
    application.add_handler(upload_conv)
    
    # Add callback query handler
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    
    # Add message handlers
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        lambda update, context: handle_general_text(update, context)
    ))
    
    print("✅ Bot is running...")
    print("📱 Send /start to begin")
    
    # Start polling
    application.run_polling(allowed_updates=Update.ALL_TYPES)

async def handle_general_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle general text messages"""
    user_id = update.effective_user.id
    text = update.message.text
    
    # Check if user is banned
    if not is_user_allowed(user_id):
        await update.message.reply_text(
            "⛔ Your account has been banned. Contact admin for support.",
            reply_markup=ReplyKeyboardRemove()
        )
        return
    
    # Handle broadcast confirmation
    if 'broadcast_confirmed' in context.user_data:
        await handle_broadcast_confirmation(update, context)
        return
    
    # Handle broadcast text
    if 'awaiting_broadcast' in context.user_data:
        await handle_broadcast_text(update, context)
        return
    
    # Handle admin reply text
    if 'reply_to_user' in context.user_data:
        await handle_admin_reply_text(update, context)
        return
    
    # Handle regular text messages
    if text == "❌ Cancel":
        await update.message.reply_text(
            "Operation cancelled.",
            reply_markup=get_main_keyboard(user_id)
        )
        return
    
    # Handle keyboard buttons
    await handle_message(update, context)

if __name__ == "__main__":
    main()
            
