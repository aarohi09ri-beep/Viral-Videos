import telebot
from telebot import types
import sqlite3
from datetime import datetime, timedelta, timezone
import time
import threading
from urllib.parse import quote
from urllib.request import urlopen
import io
import os
from flask import Flask

# ================= RENDER KEEP-ALIVE WEB SERVER =================
app = Flask('')

@app.route('/')
def home():
    return "Bot is active and running 24/7!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()

# ================= CONFIGURATION =================
TOKEN = "9287947046:AAENaDicg5ob9SQEcEg6-V5qqMLeo-IpZFM"
ADMIN_ID = 8307202156  #[span_0](start_span)[span_0](end_span)
PRIVATE_CHANNEL_ID = -1004448221220  # Apne Private Channel ka numeric ID yahan dalein
PRIVATE_CHANNEL_LINK = "https://t.me/+ZyFqqV6cgUhjYzE1"  #[span_1](start_span)[span_1](end_span)
UPI_ID = "Paytm.s2b9rko@pty"  #[span_2](start_span)[span_2](end_span)
MERCHANT_NAME = "VIP Access"

bot = telebot.TeleBot(TOKEN)
IST = timezone(timedelta(hours=5, minutes=30))
# Naya DB naam taaki purane locked users fresh start kar sakein
DB_NAME = 'bot_users_v3.db'

def safe_answer(call_id, text=None, show_alert=False):
    try:
        bot.answer_callback_query(call_id, text=text, show_alert=show_alert)
    except Exception:
        pass

def unban_and_get_link(user_id):
    try:
        bot.unban_chat_member(PRIVATE_CHANNEL_ID, user_id, only_if_banned=True)
    except Exception as e:
        print(f"Unban info: {e}")

    try:
        invite = bot.create_chat_invite_link(
            PRIVATE_CHANNEL_ID,
            member_limit=1,
            name=f"User_{user_id}"
        )
        return invite.invite_link
    except Exception:
        return PRIVATE_CHANNEL_LINK

# ================= QR CODE GENERATOR HELPER =================
def send_upi_qr(chat_id, amount, plan_title):
    upi_uri = f"upi://pay?pa={UPI_ID}&pn={quote(MERCHANT_NAME)}&am={amount}&cu=INR"
    qr_image_url = f"https://api.qrserver.com/v1/create-qr-code/?size=400x400&margin=10&data={quote(upi_uri)}"

    caption = (
        f"💳 *{plan_title}*\n\n"
        f"💰 *Amount to Pay:* ₹{amount}\n"
        f"🏦 *UPI ID:* `{UPI_ID}`\n\n"
        "📲 *How to Pay:*\n"
        "1. Upar diye gaye QR Code ko kisi bhi UPI App (PhonePe, GPay, Paytm) se scan karein.\n"
        "2. Payment complete hone ke baad niche *📸 Send Payment Screenshot* button dabayein aur apna **Screenshot** bhej dein."
    )

    markup = types.InlineKeyboardMarkup(row_width=1)
    btn_ss = types.InlineKeyboardButton("📸 Send Payment Screenshot", callback_data=f"send_ss_{amount}")
    btn_back = types.InlineKeyboardButton("🔙 Back to Plans", callback_data="view_plans")
    markup.add(btn_ss, btn_back)

    try:
        img_bytes = io.BytesIO(urlopen(qr_image_url, timeout=10).read())
        img_bytes.name = 'qr.png'
        bot.send_photo(chat_id, img_bytes, caption=caption, reply_markup=markup, parse_mode="Markdown")
    except Exception as e:
        print(f"QR Send Error: {e}")
        bot.send_message(chat_id, caption, reply_markup=markup, parse_mode="Markdown")

# ================= DATABASE SETUP =================
def init_db():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            name TEXT,
            plan TEXT,
            status TEXT,
            expiry_date TEXT,
            raw_expiry REAL DEFAULT 0,
            trial_used INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def get_user(user_id):
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, username, name, plan, status, expiry_date, raw_expiry, trial_used FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def update_user(user_id, username, name, plan, status, expiry_date, raw_expiry=0.0, trial_used=0):
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO users (user_id, username, name, plan, status, expiry_date, raw_expiry, trial_used)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, username, name, plan, status, expiry_date, float(raw_expiry), int(trial_used)))
    conn.commit()
    conn.close()

# ================= AUTO-BAN BACKGROUND WORKER =================
def expiry_checker():
    while True:
        try:
            now_ts = datetime.now(IST).timestamp()
            conn = sqlite3.connect(DB_NAME, check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM users WHERE raw_expiry > 0 AND raw_expiry <= ? AND status != '❌ Expired (Banned)'", (now_ts,))
            expired_users = cursor.fetchall()

            for row in expired_users:
                u_id = row[0]
                cursor.execute("UPDATE users SET status = '❌ Expired (Banned)', plan = 'Expired' WHERE user_id = ?", (u_id,))
                conn.commit()

                try:
                    bot.ban_chat_member(PRIVATE_CHANNEL_ID, u_id)
                except Exception as e:
                    print(f"Channel Ban error: {e}")

                try:
                    markup = types.InlineKeyboardMarkup()
                    markup.add(types.InlineKeyboardButton("💳 Buy Paid Plan to Rejoin", callback_data="view_plans"))
                    bot.send_message(
                        u_id,
                        "🚫 *Access Expired & Locked!*\n\n"
                        "Aapka free trial/plan samapt ho chuka hai aur aapko channel se remove/ban kar diya gaya hai.\n\n"
                        "Dobara unban hone aur channel rejoin karne ke liye Paid Plan purchase karein!",
                        reply_markup=markup,
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    print(f"DM error for user {u_id}: {e}")

            conn.close()
        except Exception as err:
            print(f"Background worker error: {err}")
        
        time.sleep(20)

threading.Thread(target=expiry_checker, daemon=True).start()

# ================= ADMIN COMMAND: RESET TRIAL FOR TESTING =================
# Usage: /reset (khud ka trial reset karne ke liye) ya /reset USER_ID
@bot.message_handler(commands=['reset'])
def reset_trial_cmd(message):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.split()
    target_id = int(parts[1]) if len(parts) > 1 else message.from_user.id

    try:
        bot.unban_chat_member(PRIVATE_CHANNEL_ID, target_id, only_if_banned=True)
    except Exception:
        pass

    update_user(target_id, "User", "User", "None", "Inactive", "N/A", 0.0, 0)
    bot.reply_to(message, f"✅ User `{target_id}` ka Free Trial reset ho gaya hai! Ab wo dobara Demo button use kar sakta hai.", parse_mode="Markdown")

# ================= START COMMAND =================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    username = f"@{message.from_user.username}" if message.from_user.username else "No Username"
    name = message.from_user.first_name or "User"

    user = get_user(user_id)
    # Agar bilkul naya user hai toh trial_used = 0 ke saath save karo
    if not user:
        update_user(user_id, username, name, "None", "Inactive", "N/A", 0.0, 0)

    markup = types.InlineKeyboardMarkup(row_width=1)
    btn_demo = types.InlineKeyboardButton("Demo", callback_data="demo")
    btn_plans = types.InlineKeyboardButton("💳 View Paid Plans", callback_data="view_plans")
    btn_account = types.InlineKeyboardButton("📊 My Account", callback_data="my_account")
    btn_support = types.InlineKeyboardButton("🆘 Contact Support", callback_data="support")
    markup.add(btn_demo, btn_plans, btn_account, btn_support)

    text = (
        "1 Lakh+ Viral Videos\n\n"
        "🔥 FREE ACCESS 🔥\n\n"
        "Get free access to our collection of 1 Lakh+ viral videos during the trial period. "
        "After the trial ends, choose a paid plan to continue your access.\n\n"
        "💳 PAID PLANS\n"
        "• 30 Days – ₹299\n"
        "• Lifetime – ₹499\n\n"
        "👇 Choose your plan below to continue!"
    )

    bot.send_message(message.chat.id, text, reply_markup=markup)

# ================= CALLBACK HANDLERS =================
@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    user_id = call.from_user.id
    username = f"@{call.from_user.username}" if call.from_user.username else "No Username"
    name = call.from_user.first_name or "User"
    user = get_user(user_id)

    # 1. DEMO / FREE TRIAL BUTTON (Fixed for First-Time Users!)
    if call.data == "demo":
        # Check if user has genuinely used trial before (trial_used == 1)
        already_used = False
        if user is not None:
            try:
                if int(user[7]) == 1:
                    already_used = True
            except (ValueError, TypeError, IndexError):
                already_used = False

        if already_used:
            safe_answer(call.id, "⚠️ Aap apna Free Trial pehle hi le chuke hain! Kripya Paid Plan chunein.", show_alert=True)
            return

        # First time user: Give Demo Link Immediately!
        safe_answer(call.id, "🎉 Free Trial Activated!")
        now = datetime.now(IST)
        expiry_dt = now + timedelta(minutes=2)
        raw_expiry = expiry_dt.timestamp()
        expiry_str = expiry_dt.strftime("%d %b %Y, %I:%M %p IST")

        # Save user with trial_used = 1 so they can't take it a second time
        update_user(user_id, username, name, "Free Trial", "🆕 Free trial", expiry_str, raw_expiry, 1)

        markup = types.InlineKeyboardMarkup(row_width=1)
        btn_join = types.InlineKeyboardButton("🎬 Join Private Channel", url=PRIVATE_CHANNEL_LINK)
        btn_account = types.InlineKeyboardButton("📊 My Account", callback_data="my_account")
        btn_renew = types.InlineKeyboardButton("💳 Renew Plan", callback_data="view_plans")
        btn_support = types.InlineKeyboardButton("🆘 Contact Support", callback_data="support")
        markup.add(btn_join, btn_account, btn_renew, btn_support)

        text = (
            f"✅ Your free access is active until: {expiry_str}\n\n"
            "Tap the button below to enter the private channel."
        )
        bot.send_message(call.message.chat.id, text, reply_markup=markup)

    # 2. VIEW PAID PLANS
    elif call.data == "view_plans":
        safe_answer(call.id)
        markup = types.InlineKeyboardMarkup(row_width=1)
        btn_30 = types.InlineKeyboardButton("30 Days – ₹299 (Get QR)", callback_data="plan_299")
        btn_life = types.InlineKeyboardButton("Lifetime – ₹499 (Get QR)", callback_data="plan_499")
        btn_support = types.InlineKeyboardButton("🆘 Contact Support", callback_data="support")
        markup.add(btn_30, btn_life, btn_support)

        text = (
            "💳 *Paid Plans*\n\n"
            "Apna plan select karein, aapko turant Scan & Pay QR Code mil jayega:"
        )
        bot.send_message(call.message.chat.id, text, reply_markup=markup, parse_mode="Markdown")

    # 3. PLAN 299 QR
    elif call.data == "plan_299":
        safe_answer(call.id, "Generating ₹299 QR Code...")
        send_upi_qr(call.message.chat.id, 299, "30 Days Plan – ₹299")

    # 4. PLAN 499 QR
    elif call.data == "plan_499":
        safe_answer(call.id, "Generating ₹499 QR Code...")
        send_upi_qr(call.message.chat.id, 499, "Lifetime Plan – ₹499")

    # 5. MY ACCOUNT
    elif call.data == "my_account":
        safe_answer(call.id)
        if user and user[3] != "None":
            plan = user[3]
            status = user[4]
            expiry = user[5]
        else:
            plan = "No Active Plan"
            status = "❌ Inactive"
            expiry = "N/A"

        text = (
            "📊 *My Account*\n\n"
            f"Name: {name}\n"
            f"Username: {username}\n"
            f"Telegram ID: `{user_id}`\n"
            f"Current plan: {plan}\n"
            f"Status: {status}\n"
            f"Expiry date: {expiry}"
        )

        markup = types.InlineKeyboardMarkup(row_width=1)
        btn_renew = types.InlineKeyboardButton("💳 Renew Plan", callback_data="view_plans")
        btn_support = types.InlineKeyboardButton("🆘 Contact Support", callback_data="support")
        markup.add(btn_renew, btn_support)

        bot.send_message(call.message.chat.id, text, reply_markup=markup, parse_mode="Markdown")

    # 6. CONTACT SUPPORT
    elif call.data == "support":
        safe_answer(call.id)
        markup = types.InlineKeyboardMarkup(row_width=1)
        btn_send_msg = types.InlineKeyboardButton("📸 Send Payment Screenshot / Support", callback_data="send_support")
        btn_account = types.InlineKeyboardButton("📊 My Account", callback_data="my_account")
        btn_plans = types.InlineKeyboardButton("💳 View Paid Plans", callback_data="view_plans")
        markup.add(btn_send_msg, btn_account, btn_plans)

        text = (
            "🆘 *Support & Payment Verification*\n\n"
            "Payment screenshot ya apna message bhejne ke liye niche button par click karein."
        )
        bot.send_message(call.message.chat.id, text, reply_markup=markup, parse_mode="Markdown")

    # 7. SEND SCREENSHOT / SUPPORT
    elif call.data == "send_support" or call.data.startswith("send_ss_"):
        safe_answer(call.id)
        selected_amt = call.data.split("_")[-1] if call.data.startswith("send_ss_") else "Support"
        msg = bot.send_message(
            call.message.chat.id,
            "📸 *Send your Payment Screenshot now* (or send your support message). Use /cancel to exit.",
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, process_support_message, selected_amt)

    # 8. ADMIN APPROVE / REJECT
    elif call.data.startswith("adm_"):
        if user_id != ADMIN_ID:
            safe_answer(call.id, "⛔ Only Admin can use this button!", show_alert=True)
            return

        parts = call.data.split("_")
        action = parts[1]
        target_id = int(parts[2])

        u_data = get_user(target_id)
        u_name = u_data[1] if u_data else "No Username"
        f_name = u_data[2] if u_data else "User"

        if action in ["app30", "applife"]:
            now = datetime.now(IST)
            if action == "app30":
                expiry_dt = now + timedelta(days=30)
                raw_exp = expiry_dt.timestamp()
                exp_str = expiry_dt.strftime("%d %b %Y, %I:%M %p IST")
                p_name = "30 Days – ₹299"
            else:
                expiry_dt = now + timedelta(days=36500)
                raw_exp = expiry_dt.timestamp()
                exp_str = "Lifetime"
                p_name = "Lifetime – ₹499"

            rejoin_link = unban_and_get_link(target_id)
            update_user(target_id, u_name, f_name, p_name, "✅ Active", exp_str, raw_exp, 1)

            user_markup = types.InlineKeyboardMarkup(row_width=1)
            user_markup.add(
                types.InlineKeyboardButton("🎬 Rejoin Private Channel Now", url=rejoin_link),
                types.InlineKeyboardButton("📊 My Account", callback_data="my_account")
            )
            try:
                bot.send_message(
                    target_id,
                    f"🎉 *Payment Approved!*\n\n"
                    f"✅ *Plan Activated:* {p_name}\n"
                    f"⏳ *Valid Until:* {exp_str}\n\n"
                    "Aapko channel se unban kar diya gaya hai! Niche diye gaye button par click karke channel rejoin karein:",
                    reply_markup=user_markup,
                    parse_mode="Markdown"
                )
            except Exception as e:
                print(f"Error sending approval to user: {e}")

            safe_answer(call.id, f"✅ Approved {p_name}!")
            bot.edit_message_text(
                f"{call.message.text}\n\n✅ *STATUS: APPROVED ({p_name})*",
                call.message.chat.id,
                call.message.message_id,
                parse_mode="Markdown"
            )

        elif action == "reject":
            user_markup = types.InlineKeyboardMarkup(row_width=1)
            user_markup.add(
                types.InlineKeyboardButton("💳 View Paid Plans & Try Again", callback_data="view_plans"),
                types.InlineKeyboardButton("📸 Resend Valid Screenshot", callback_data="send_support")
            )
            try:
                bot.send_message(
                    target_id,
                    "❌ *Payment Screenshot Rejected!*\n\n"
                    "Admin ne aapka payment verify nahi paaya. Kripya sahi payment screenshot dobara bhejein.",
                    reply_markup=user_markup,
                    parse_mode="Markdown"
                )
            except Exception as e:
                print(f"Error sending rejection to user: {e}")

            safe_answer(call.id, "❌ Request Rejected!")
            bot.edit_message_text(
                f"{call.message.text}\n\n❌ *STATUS: REJECTED BY ADMIN*",
                call.message.chat.id,
                call.message.message_id,
                parse_mode="Markdown"
            )

def process_support_message(message, selected_amt="Support"):
    if message.text and message.text.strip() == "/cancel":
        bot.send_message(message.chat.id, "❌ Request cancelled.")
        return

    uid = message.from_user.id
    uname = f"@{message.from_user.username}" if message.from_user.username else "No Username"
    fname = message.from_user.first_name or "User"

    plan_hint = f"₹{selected_amt} Plan" if selected_amt in ["299", "499"] else "Support / Payment Proof"

    admin_markup = types.InlineKeyboardMarkup(row_width=2)
    btn_app30 = types.InlineKeyboardButton("✅ Approve 30d (₹299)", callback_data=f"adm_app30_{uid}")
    btn_applife = types.InlineKeyboardButton("✅ Approve Life (₹499)", callback_data=f"adm_applife_{uid}")
    btn_reject = types.InlineKeyboardButton("❌ Reject Screenshot", callback_data=f"adm_reject_{uid}")
    admin_markup.add(btn_app30, btn_applife)
    admin_markup.add(btn_reject)

    user_info = (
        f"📩 *New {plan_hint} Received*\n"
        f"👤 *From:* {fname} ({uname})\n"
        f"🆔 *User ID:* `{uid}`\n\n"
        "👇 *Niche screenshot check karke Approve ya Reject dabayein:*"
    )

    try:
        bot.forward_message(ADMIN_ID, message.chat.id, message.message_id)
        bot.send_message(ADMIN_ID, user_info, reply_markup=admin_markup, parse_mode="Markdown")
    except Exception as e:
        print(f"Error forwarding to admin: {e}")

    bot.send_message(
        message.chat.id,
        "⏳ *Screenshot Submitted!*\n\nAapka payment screenshot Admin ko verification ke liye bhej diya gaya hai. Approve hote hi aapko yahan **Channel Rejoin Link** mil jayega!",
        parse_mode="Markdown"
    )

# ================= RUN BOT & KEEP-ALIVE =================
if __name__ == "__main__":
    keep_alive()
    print("Bot is running with Fixed First-Time Demo Link...")
    bot.infinity_polling(skip_pending=True, timeout=20, long_polling_timeout=10)
