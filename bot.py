import os
import re
import json
import logging
from datetime import datetime

import pytz
import gspread
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Environment variables ─────────────────────────────────────────────────────
BOT_TOKEN            = os.environ["BOT_TOKEN"]
GOOGLE_SHEET_ID      = os.environ["GOOGLE_SHEET_ID"]
GOOGLE_CLIENT_ID     = os.environ["GOOGLE_CLIENT_ID"]
GOOGLE_CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]
GOOGLE_REFRESH_TOKEN = os.environ["GOOGLE_REFRESH_TOKEN"]
GROUP_CHAT_ID        = os.environ.get("GROUP_CHAT_ID", "")      # e.g. -1001234567890
GROUP_INVITE_LINK    = os.environ.get("GROUP_INVITE_LINK", "")  # e.g. https://t.me/+xxxx
NOTIFY_TIME          = os.environ.get("DAILY_NOTIFY_TIME", "09:00")  # HH:MM local
TIMEZONE             = os.environ.get("TIMEZONE", "UTC")            # e.g. Europe/Kyiv

# ── Conversation states ───────────────────────────────────────────────────────
SPORT, LEVEL, EMAIL = range(3)

# ── Google Sheets helpers ─────────────────────────────────────────────────────
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

def _sheet_client():
    creds = Credentials(
        token=None,
        refresh_token=GOOGLE_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        scopes=SCOPES,
    )
    creds.refresh(Request())   # exchange refresh_token → access_token
    return gspread.authorize(creds)


def _participants_ws(spreadsheet):
    try:
        return spreadsheet.worksheet("Participants")
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet("Participants", rows=1000, cols=60)
        ws.append_row(["Telegram ID", "Full Name", "Username",
                       "Sport", "Level", "Corporate Email", "Registered At"])
        return ws


def _daily_ws(spreadsheet, date_str: str):
    """Return (or create) a per-day worksheet named like '2026-04-06'."""
    try:
        return spreadsheet.worksheet(date_str)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(date_str, rows=500, cols=4)
        ws.append_row(["Telegram ID", "Full Name", "Photo ✅", "Time"])
        return ws


def save_participant(user_data: dict, tg_user) -> None:
    spreadsheet = _sheet_client().open_by_key(GOOGLE_SHEET_ID)
    ws = _participants_ws(spreadsheet)

    row = [
        tg_user.id,
        tg_user.full_name,
        tg_user.username or "",
        user_data["sport"],
        user_data["level"],
        user_data["email"],
        datetime.now(pytz.timezone(TIMEZONE)).strftime("%Y-%m-%d %H:%M"),
    ]

    # Update if already registered, otherwise append
    records = ws.get_all_records()
    for idx, rec in enumerate(records, start=2):        # row 1 = header
        if str(rec.get("Telegram ID")) == str(tg_user.id):
            ws.update(f"A{idx}:G{idx}", [row])
            return
    ws.append_row(row)


def mark_photo(tg_user) -> bool:
    """Add user to today's tab. Returns True if first time today, False if already marked."""
    spreadsheet = _sheet_client().open_by_key(GOOGLE_SHEET_ID)
    date_str = datetime.now(pytz.timezone(TIMEZONE)).strftime("%Y-%m-%d")
    ws = _daily_ws(spreadsheet, date_str)

    records = ws.get_all_records()
    for rec in records:
        if str(rec.get("Telegram ID")) == str(tg_user.id):
            return False   # already logged today

    ws.append_row([
        tg_user.id,
        tg_user.full_name,
        "✅",
        datetime.now(pytz.timezone(TIMEZONE)).strftime("%H:%M"),
    ])
    return True


def today_count() -> int:
    """Return how many people logged a photo today."""
    try:
        spreadsheet = _sheet_client().open_by_key(GOOGLE_SHEET_ID)
        date_str = datetime.now(pytz.timezone(TIMEZONE)).strftime("%Y-%m-%d")
        ws = _daily_ws(spreadsheet, date_str)
        return max(0, len(ws.get_all_records()))
    except Exception:
        return 0


# ── Bot handlers ──────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("🏃 Running",  callback_data="sport_Running"),
            InlineKeyboardButton("🚴 Cycling",  callback_data="sport_Cycling"),
        ],
        [
            InlineKeyboardButton("🏊 Swimming", callback_data="sport_Swimming"),
            InlineKeyboardButton("💪 Gym",       callback_data="sport_Gym"),
        ],
        [
            InlineKeyboardButton("🧘 Yoga",     callback_data="sport_Yoga"),
            InlineKeyboardButton("⭐ Other",     callback_data="sport_Other"),
        ],
    ]
    await update.message.reply_text(
        "👋 *Welcome to the Sports Challenge!*\n\n"
        "I'll register you in just 3 quick steps.\n\n"
        "First — what sport will you be doing?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return SPORT


async def sport_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    sport = query.data.replace("sport_", "")
    context.user_data["sport"] = sport

    keyboard = [
        [InlineKeyboardButton("🌱 Newbie",   callback_data="level_Newbie")],
        [InlineKeyboardButton("🔥 Regular",  callback_data="level_Regular")],
        [InlineKeyboardButton("⚡ Pro",       callback_data="level_Pro")],
    ]
    await query.edit_message_text(
        f"Great choice — *{sport}* it is! 🎯\n\n"
        "Now, how would you describe your fitness level?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return LEVEL


async def level_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    level = query.data.replace("level_", "")
    context.user_data["level"] = level

    await query.edit_message_text(
        f"Level *{level}* — respect! 💪\n\n"
        "Last step: please send your *corporate email address*.",
        parse_mode="Markdown",
    )
    return EMAIL


async def email_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    email = update.message.text.strip()

    if not re.match(r"^[\w.%+\-]+@[\w.\-]+\.[a-zA-Z]{2,}$", email):
        await update.message.reply_text(
            "⚠️ That doesn't look like a valid email address.\n"
            "Please try again (e.g. name@company.com):"
        )
        return EMAIL

    context.user_data["email"] = email

    try:
        save_participant(context.user_data, update.effective_user)
        saved_ok = True
    except Exception as e:
        logger.error("Sheet save error: %s", e)
        saved_ok = False

    link = GROUP_INVITE_LINK or "_(ask your admin for the group link)_"
    status_line = "✅ You're in the spreadsheet!" if saved_ok else "⚠️ Registration saved locally — sheet sync failed, please contact admin."

    await update.message.reply_text(
        f"🎉 *You're registered!*\n\n"
        f"🏅 Sport: *{context.user_data['sport']}*\n"
        f"📊 Level: *{context.user_data['level']}*\n"
        f"📧 Email: `{email}`\n\n"
        f"{status_line}\n\n"
        f"👇 Join the challenge group:\n{link}\n\n"
        f"Every day there will be a reminder in the group — just post a photo of your workout and I'll log it automatically. Let's go! 🚀",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Registration cancelled. Send /start whenever you're ready.")
    return ConversationHandler.END


async def handle_group_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fires when someone posts a photo in the group chat."""
    msg = update.message
    if not msg or not msg.photo:
        return

    # Ignore if not in the configured group
    if GROUP_CHAT_ID and str(msg.chat_id) != str(GROUP_CHAT_ID):
        return

    user = update.effective_user
    is_new = mark_photo(user)

    if is_new:
        count = today_count()
        await msg.reply_text(
            f"✅ *{user.first_name}*, workout logged! Great job 🔥\n"
            f"_{count} participant(s) done so far today._",
            parse_mode="Markdown",
        )
    else:
        await msg.reply_text(
            f"👏 *{user.first_name}*, you already logged one today — keep the momentum!",
            parse_mode="Markdown",
        )


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: show how many people posted today."""
    count = today_count()
    date_str = datetime.now(pytz.timezone(TIMEZONE)).strftime("%B %d, %Y")
    await update.message.reply_text(
        f"📊 *Stats for {date_str}*\n\n"
        f"✅ Workouts logged today: *{count}*",
        parse_mode="Markdown",
    )


# ── Scheduler job ─────────────────────────────────────────────────────────────

async def daily_reminder(app: Application):
    if not GROUP_CHAT_ID:
        logger.warning("GROUP_CHAT_ID not set — skipping daily reminder.")
        return

    date_str = datetime.now(pytz.timezone(TIMEZONE)).strftime("%A, %B %d")
    try:
        await app.bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=(
                f"🌅 *Good morning, Champions!*\n\n"
                f"📅 {date_str}\n\n"
                f"💪 Time to move! Post a photo of your workout here and I'll mark you as done for today.\n\n"
                f"Every rep counts. Let's go! 🚀"
            ),
            parse_mode="Markdown",
        )
        logger.info("Daily reminder sent to group %s", GROUP_CHAT_ID)
    except Exception as e:
        logger.error("Failed to send daily reminder: %s", e)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Registration conversation
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", cmd_start)],
        states={
            SPORT: [CallbackQueryHandler(sport_chosen, pattern="^sport_")],
            LEVEL: [CallbackQueryHandler(level_chosen, pattern="^level_")],
            EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, email_received)],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True,
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.GROUPS, handle_group_photo))

    # Daily scheduler
    tz = pytz.timezone(TIMEZONE)
    hour, minute = map(int, NOTIFY_TIME.split(":"))
    scheduler = AsyncIOScheduler(timezone=tz)
    scheduler.add_job(
        daily_reminder,
        trigger="cron",
        hour=hour,
        minute=minute,
        args=[app],
    )
    scheduler.start()
    logger.info("Scheduler started — daily reminder at %s %s", NOTIFY_TIME, TIMEZONE)

    logger.info("Bot is running…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
