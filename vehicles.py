import sqlite3
import logging
import re
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Configuration
BOT_TOKEN = "8902371867:AAGRFeOkAOXTjdJHHZFDpPjBsKsZxnrykJQ"
ADMIN_ID = 8682912888
API_URL = "https://vehicleinfov1byabhigyan.vercel.app/vehicleinfov1?rc="
REFER_REWARD = 2  # Har successful refer par 2 credits milenge
INITIAL_CREDITS = 3  # New user ko start par milne wale credits

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- Database Setup ---
def init_db():
    conn = sqlite3.connect("vehicle_bot.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            credits INTEGER DEFAULT 3,
            referred_by INTEGER
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# Helper Functions
def get_user(user_id):
    conn = sqlite3.connect("vehicle_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT credits, referred_by FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def register_user(user_id, referrer_id=None):
    conn = sqlite3.connect("vehicle_bot.db")
    cursor = conn.cursor()
    
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if cursor.fetchone() is None:
        cursor.execute("INSERT INTO users (user_id, credits, referred_by) VALUES (?, ?, ?)", 
                       (user_id, INITIAL_CREDITS, referrer_id))
        
        # Referrer reward
        if referrer_id:
            cursor.execute("UPDATE users SET credits = credits + ? WHERE user_id = ?", (REFER_REWARD, referrer_id))
        
        conn.commit()
        conn.close()
        return True
    conn.close()
    return False

def update_credits(user_id, amount):
    conn = sqlite3.connect("vehicle_bot.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET credits = credits + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

# Decorator to restrict commands to Admin only
def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != ADMIN_ID:
            await update.message.reply_text("❌ Aapke paas is command ki permission nahi hai.")
            return
        return await func(update, context)
    return wrapper

# --- USER COMMANDS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    bot_username = (await context.bot.get_me()).username
    
    # Check Referral
    referrer_id = None
    if context.args and context.args[0].isdigit():
        possible_ref = int(context.args[0])
        if possible_ref != user_id:
            referrer_id = possible_ref

    is_new = register_user(user_id, referrer_id)
    
    if is_new and referrer_id:
        try:
            await context.bot.send_message(
                chat_id=referrer_id, 
                text=f"🎉 **Referral Success!**\nNaye user ne aapke link se join kiya hai. +{REFER_REWARD} credits add ho gaye hain!"
            )
        except Exception:
            pass

    refer_link = f"https://t.me/{bot_username}?start={user_id}"
    user_data = get_user(user_id)
    credits = user_data[0] if user_data else INITIAL_CREDITS

    welcome_msg = (
        f"🤖 **Welcome to Vehicle Info Bot!**\n\n"
        f"💳 **Aapke Credits:** `{credits}`\n\n"
        f"📌 **Available Commands:**\n"
        f"• `/rc <Vehicle Number>` - Details nikalne ke liye\n"
        f"• `/profile` - Apni details check karein\n"
        f"• `/refer` - Apna refer link paayein\n\n"
        f"🔗 **Apna Refer Link:**\n`{refer_link}`\n"
        f"*(Har refer par +{REFER_REWARD} credits milenge)*"
    )
    await update.message.reply_text(welcome_msg, parse_mode="Markdown")

async def refer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    bot_username = (await context.bot.get_me()).username
    refer_link = f"https://t.me/{bot_username}?start={user_id}"
    
    msg = (
        f"🎁 **Refer & Earn Program**\n\n"
        f"Apne dosto ko bot share karein aur har refer par **+{REFER_REWARD} Credits** paayein!\n\n"
        f"🔗 **Aapka Referral Link:**\n`{refer_link}`"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = get_user(user_id)
    credits = user_data[0] if user_data else 0

    msg = (
        f"👤 **User Profile:**\n\n"
        f"🆔 **User ID:** `{user_id}`\n"
        f"💳 **Available Credits:** `{credits}`"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def get_rc_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = get_user(user_id)

    if not user_data:
        register_user(user_id)
        user_data = get_user(user_id)

    credits = user_data[0]

    if credits < 1:
        await update.message.reply_text(
            "❌ **Credits Khatam Ho Gaye!**\n\nCredits earn karne ke liye `/refer` command ka use karke dosto ko share karein."
        )
        return

    if not context.args:
        await update.message.reply_text("⚠️ Kripya RC Number dein.\n**Example:** `/rc BR46V4688`", parse_mode="Markdown")
        return

    rc_number = context.args[0].upper()
    await update.message.reply_text(f"🔍 Searching details for **{rc_number}**...", parse_mode="Markdown")

    try:
        response = requests.get(f"{API_URL}{rc_number}", timeout=10)
        if response.status_code == 200:
            raw_data = response.text
            
            # API response se credit link aur unnecessary URLs ko filter (remove) karne ke liye
            cleaned_data = re.sub(r'•?\s*Credit:\s*https?://\S+', '', raw_data, flags=re.IGNORECASE)
            cleaned_data = re.sub(r'https?://t\.me/\S+', '', cleaned_data, flags=re.IGNORECASE)
            cleaned_data = cleaned_data.strip()

            update_credits(user_id, -1)  # Deduct 1 credit

            reply_text = (
                f"🚘 **VEHICLE DETAILS** 🚘\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"{cleaned_data}\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"💳 **Remaining Credits:** `{credits - 1}`"
            )
            await update.message.reply_text(reply_text, parse_mode="Markdown")
        else:
            await update.message.reply_text("❌ Vehicle detail nahi mili. Vehicle number check karein.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error fetching details: {str(e)}")

# --- ADMIN COMMANDS ---

@admin_only
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_msg = (
        f"👑 **ADMIN CONTROL PANEL**\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"• `/stats` - Total bot users check karein\n"
        f"• `/addcredit <user_id> <amount>` - User ko credit dein\n"
        f"• `/remcredit <user_id> <amount>` - Credit cut karein\n"
        f"• `/broadcast <message>` - Sabhi users ko message bhejein\n"
        f"• `/userinfo <user_id>` - Specific user ka credit dekhein"
    )
    await update.message.reply_text(admin_msg, parse_mode="Markdown")

@admin_only
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect("vehicle_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    conn.close()

    await update.message.reply_text(f"📊 **Total Registered Users:** `{total_users}`", parse_mode="Markdown")

@admin_only
async def add_credit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("⚠️ Usage: `/addcredit <user_id> <amount>`", parse_mode="Markdown")
        return
    
    target_id, amount = int(context.args[0]), int(context.args[1])
    update_credits(target_id, amount)
    
    await update.message.reply_text(f"✅ User `{target_id}` ko `{amount}` credits add kar diye gaye.")
    try:
        await context.bot.send_message(chat_id=target_id, text=f"🎉 Admin ne aapke wallet me **+{amount} Credits** add kiye hain!")
    except Exception:
        pass

@admin_only
async def remove_credit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("⚠️ Usage: `/remcredit <user_id> <amount>`", parse_mode="Markdown")
        return
    
    target_id, amount = int(context.args[0]), int(context.args[1])
    update_credits(target_id, -amount)
    await update.message.reply_text(f"✅ User `{target_id}` ke `{amount}` credits cut kar diye gaye.")

@admin_only
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Usage: `/broadcast <your_message>`", parse_mode="Markdown")
        return

    msg = " ".join(context.args)
    conn = sqlite3.connect("vehicle_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    conn.close()

    sent, failed = 0, 0
    for u in users:
        try:
            await context.bot.send_message(chat_id=u[0], text=f"📢 **ADMIN ANNOUNCEMENT:**\n\n{msg}", parse_mode="Markdown")
            sent += 1
        except Exception:
            failed += 1

    await update.message.reply_text(f"📢 **Broadcast Finished!**\n\n✅ Sent: `{sent}`\n❌ Failed: `{failed}`", parse_mode="Markdown")

# Main Function
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # User Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("rc", get_rc_info))
    app.add_handler(CommandHandler("refer", refer))
    app.add_handler(CommandHandler("profile", profile))

    # Admin Commands
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("addcredit", add_credit))
    app.add_handler(CommandHandler("remcredit", remove_credit))
    app.add_handler(CommandHandler("broadcast", broadcast))

    print("Bot Successfully Running...")
    app.run_polling()

if __name__ == "__main__":
    main()
