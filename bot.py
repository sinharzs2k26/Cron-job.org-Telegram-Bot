import re
import os
import logging
import json
import requests
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ForceReply
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
# --- CONFIGURATION ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CRON_URL = "https://api.cron-job.org"

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)
# --- HELPERS ---
def get_headers(context):
    key = context.user_data.get("api_key")
    if not key: return None
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
# --- COMMANDS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    is_logged_in = "api_key" in context.user_data
    status_suffix = "✅ Connected to Cron-job.org" if is_logged_in else "❌ Not Logged In"
    welcome_text = (
        "🛠 <b>Cron-Job Manager Bot</b>\n"
        f"<i>Status: {status_suffix}</i>\n\n"
        f"<b>👋 Welcome, {user.first_name} !</b>\n"
        "This bot is your mobile control center for <b>Cron-job.org</b>. "
        "Use it to keep your web services awake, automate backups, or ping any URL on a schedule.\n\n"
        "<b>🚀 Core Features:</b>\n"
        "• <b>Quick List:</b> View all your active cron jobs and their statuses.\n"
        "• <b>Smart Wizard:</b> Create new jobs with custom intervals (Minutes or Hours).\n"
        "• <b>Easy Toggle:</b> Enable or Disable jobs with a single tap.\n"
        "• <b>Job Cleanup:</b> Delete outdated or test jobs immediately.\n\n"
        "<b>📖 How to Start:</b>\n"
        "1️⃣ Get your API Key from the <a href='https://console.cron-job.org/settings'>Cron-job.org Console</a>.\n"
        "2️⃣ Use /login to link your account.\n"
        "3️⃣ Use /jobs to see your current pings or /createjob to add a new one.\n\n"
    )
    await update.message.reply_html(welcome_text, disable_web_page_preview=True)

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "api_key" in context.user_data:
        await update.message.reply_text("You were logged in already!")
    else:
        await update.message.reply_text(
            "<b>🔑 Login to cron-job.org</b>\n"
            "Please provide your API key to use the bot.\n\n",
            reply_markup=ForceReply(selective=True),
            parse_mode="HTML"
        )

async def logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "api_key" in context.user_data:
        del context.user_data["api_key"]
        await update.message.reply_text("🔒 <b>Logged out.</b> Your API key has been cleared.", parse_mode="HTML")
    else:
        await update.message.reply_text("You weren't logged in!")

async def jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    headers = get_headers(context)
    if not headers:
        await update.message.reply_text("❌ You are not logged in.\nSend /login")
    r = requests.get(f"{CRON_URL}/jobs", headers=headers)
    if r.status_code == 200:
        jobs = r.json().get("jobs", [])
        if not jobs:
            return await update.message.reply_text("📭 No jobs found.")
        keyboard = []
        for j in jobs:
            status_icon = "🟢" if j.get("enabled") else "🔴"
            keyboard.append([InlineKeyboardButton(f"{status_icon} {j.get('title')}", callback_data=f"view_{j.get('jobId')}")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        text = "📋 <b>Your Cron Jobs:</b>\nSelect a job to manage it."
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")
        else:
            await update.message.reply_html(text, reply_markup=reply_markup)

async def create_job_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    headers = get_headers(context)
    if not headers:
        await update.message.reply_text("❌ You are not logged in.\nSend /login")
        return
    await update.message.reply_text(
        "✨ <b>Create New Cron Job</b>\n\n📝 Enter a Title (e.g., My Bot Ping):",
        reply_markup=ForceReply(selective=True),
        parse_mode="HTML"
    )
# --- INTERACTION HANDLER ---
async def handle_interaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    headers = get_headers(context)
    if data.startswith("view_"):
        await query.answer()
        job_id = data.split("_")[1]
        r = requests.get(f"{CRON_URL}/jobs/{job_id}", headers=headers)
        if r.status_code == 200:
            job = r.json().get("jobDetails", {})
            text = (
                f"<b>📝 Title:</b> <code>{job.get('title')}</code>\n\n"
                f"<b>🔗 URL:</b> <code>{job.get('url')}</code>\n\n"
                "<b>Choose an action to execute:</b>"
            )
            keyboard = [
                [
                    InlineKeyboardButton("▶️ Enable", callback_data=f"toggle_on_{job_id}"),
                    InlineKeyboardButton("⏸ Disable", callback_data=f"toggle_off_{job_id}"),
                    InlineKeyboardButton("🗑 Delete", callback_data=f"delete_{job_id}")
                ],
                [InlineKeyboardButton("⬅️ Back to List", callback_data="back")]
            ]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    elif data.startswith("toggle_"):
        _, state, job_id = data.split("_")
        enabled = True if state == "on" else False
        payload = {"job": {"enabled": enabled}}
        r = requests.patch(f"{CRON_URL}/jobs/{job_id}", data=json.dumps(payload), headers=headers)
        if r.status_code == 200:
            await query.answer(f"Job {'Enabled ▶️' if enabled else 'Disabled ⏸'}", show_alert=True)
            await jobs(update, context)
        else:
            await query.answer("❌ Failed to update job.", show_alert=True)
    elif data.startswith("delete"):
        await query.answer()
        job_id = data.split("_")[1]
        await query.message.reply_text(
            f"<b>Job ID: </b><code>{job_id}</code>\n\n"
            "⚠️ Are you sure you want to <b>PERMANENTLY DELETE</b> this Cron job?\nTo confirm, reply to this message with the word: <b>CONFIRM</b>",
            reply_markup=ForceReply(selective=True),
            parse_mode="HTML"
        )
        return
    elif data.startswith("back"):
        await query.answer()
        await jobs(update, context)
    elif data.startswith("interval_"):
        await query.answer()
        exectype = data.split("_")[1]
        await query.message.reply_html(
            f"⏳ Enter execution interval in {exectype}.\n"
            f"(e.g., enter 5 for every 5 {exectype}, or 15 for every 15 {exectype}):",
            reply_markup=ForceReply(selective=True)
        )
        return
# --- TEXT/REPLY HANDLER ---
async def handle_replies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message: return    
    prompt = update.message.reply_to_message.text
    user_input = update.message.text
    headers = get_headers(context)
    if "API" in prompt:
        test = requests.get(f"{CRON_URL}/jobs", headers={"Authorization": f"Bearer {user_input}"})
        if test.status_code == 200:
            context.user_data["api_key"] = user_input
            await update.message.reply_html(
                "✅ <b>Login successfull!</b> You can now use management commands.\n\n"
                "<i>📌 You have to re-login if the bot server gets updates and so your API key gets cleared.</i>\n\n"
                "If you want to logout, send /logout and your API key will be cleared."
            )
        else:
            await update.message.reply_text("❌ Invalid Key.")
    elif "DELETE" in prompt:
        match = re.search(r"[0-9]+", prompt)
        if not match:
            return
        job_id = match.group(0)
        r = requests.delete(f"{CRON_URL}/jobs/{job_id}", headers=headers)
        if r.status_code == 200:
            await update.message.reply_html("⚠️ <b>Job deleted.</b>")
        else:
            await update.message.reply_text("❌ Failed to delete job.")
    elif "Title" in prompt:
        context.user_data["new_job_title"] = user_input
        await update.message.reply_html("🔗 Enter the URL to ping:", reply_markup=ForceReply(selective=True))
    elif "URL" in prompt:
        context.user_data["new_job_url"] = user_input
        text = "🕒 <b>Select execution schedule type:</b>"
        keyboard = [
            [InlineKeyboardButton("Minutes (1-59)", callback_data="interval_minutes")],
            [InlineKeyboardButton("Hours (1-23)", callback_data="interval_hours")]
        ]
        await update.message.reply_html(text, reply_markup=InlineKeyboardMarkup(keyboard))
        
    elif "interval" in prompt:
        title = context.user_data.get("new_job_title")
        url = context.user_data.get("new_job_url")
        interval = int(user_input)
        if "minutes" in prompt:
            if interval < 1 or interval > 59:
                await update.message.reply_text("❌ Invalid input. Please enter minutes in range (1-59)")
            else:
                exectype = "minutes" if interval > 1 else "minute"
                hours = [-1]
                minutes = [m for m in range(0, 60, interval)]
        elif "hours" in prompt:
            if interval < 1 or interval > 23:
                await update.message.reply_text("❌ Invalid input. Please enter hours in range (1-23)")
            else:
                exectype = "hours" if interval > 1 else "hour"
                hours = [m for m in range(0, 24, interval)]
                minutes = [0]
        payload = {
            "job": {
                "title": title,
                "url": url,
                "enabled": True,
                "saveResponses": True,
                "schedule": {
                    "timezone": "UTC",
                    "hours": hours,
                    "mdays": [-1], 
                    "months": [-1], 
                    "wdays": [-1],
                    "minutes": minutes
                }
            }
        }
        r = requests.put(f"{CRON_URL}/jobs", data=json.dumps(payload), headers=headers)
        if r.status_code == 200:
            await update.message.reply_html(
                f"🚀 <b>Job Created!</b>\n"
                f"📝 <b>Title:</b> <code>{title}</code>\n"
                f"🔗 <b>URL:</b> <code>{url}</code>\n"
                f"🕒 <b>Interval:</b> Every {user_input} {exectype}."
            )
        else:
            await update.message.reply_text("❌ Error")
# --- MAIN ---
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("logout", logout))
    app.add_handler(CommandHandler("jobs", jobs))
    app.add_handler(CommandHandler("createjob", create_job_start))
    app.add_handler(CallbackQueryHandler(handle_interaction))
    app.add_handler(MessageHandler(filters.REPLY & filters.TEXT, handle_replies))
    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Bot is alive!')
        def log_message(self, format, *args):
            pass
    def run_health_server():
        httpd = HTTPServer(('0.0.0.0', 10000), HealthHandler)
        httpd.serve_forever()
    health_thread = threading.Thread(target=run_health_server, daemon=True)
    health_thread.start()
    app.run_polling()

if __name__ == "__main__":
    main()