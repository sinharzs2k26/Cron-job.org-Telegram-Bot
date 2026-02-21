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
    await update.message.reply_html(
        "🛠 <b>Cron-Job Manager Bot</b>\n\n"
        " • /login - Add your API Key.\n"
        "• /jobs - Manage your pings.\n"
        "• /createjob - Create a new Cron Job."
    )

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
    await update.message.reply_text(
        "✨ <b>Create New Job</b>\n\n<b>📝 Step 1 -</b> Enter a Title (e.g., My Bot Ping):",
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
                f"ℹ️ <b>Basic information</b>\n" + "—" * 12 + "\n"
                f"<b>📝 Title:</b> {job.get('title')}\n\n"
                f"<b>🔗 URL:</b> <code>{job.get('url')}</code>"
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
        job_id = data.split("_")[1]
        r = requests.delete(f"{CRON_URL}/jobs/{job_id}", headers=headers)
        if r.status_code == 200:
            await query.answer("⚠️ Job deleted.", show_alert=True)
            await jobs(update, context)
        else:
            await query.answer("❌ Failed to delete job.", show_alert=True)
    elif data.startswith("back"):
        await jobs(update, context)
    elif data.startswith("interval_"):
        await query.answer()
        exectype = data.split("_")[1]
        await query.message.reply_html(
            f"⏳ <b>Step 3 -</b> Enter execution interval in {exectype}.\n"
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
    elif "Step 1" in prompt:
        context.user_data["new_job_title"] = user_input
        await update.message.reply_html("🔗 <b>Step 2 -</b> Enter the URL to ping:", reply_markup=ForceReply(selective=True))
    elif "Step 2" in prompt:
        context.user_data["new_job_url"] = user_input
        text = "🕒 Select execution schedule type:"
        keyboard = [
            [InlineKeyboardButton("Minutes", callback_data="interval_minutes")],
            [InlineKeyboardButton("Hours", callback_data="interval_hours")]
        ]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        
    elif "Step 3" in prompt:
        title = context.user_data.get("new_job_title")
        url = context.user_data.get("new_job_url")
        interval = int(user_input)
        if "minutes" in prompt:
            exectype = "minutes" if interval > 1 else "minute"
            hours = [-1]
            minutes = [m for m in range(0, 60, interval)]
        if "hours" in prompt:
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
                f"📝 <b>Title:</b> {title}\n"
                f"🔗 <b>URL:</b> {url}\n"
                f"🕒 <b>Interval:</b> Every {user_input} {exectype}."
            )
        else:
            await update.message.reply_text(f"❌ Error: {r.text}")
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