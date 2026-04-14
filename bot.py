import os
import re
import json
import logging
import random
import html
from datetime import datetime

import pytz
import gspread
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommand,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
)
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

PENDING_CHECKIN_TTL_SECONDS = 10 * 60  # 10 minutes

PRAISE_PHRASES = [
    "Круто! Так держать 💪",
    "Отличная работа — горжусь тобой 🔥",
    "Засчитано! Ты молодец ✅",
    "Супер! Продолжаем в том же духе 🚀",
    "Вау, мощно! ✅",
]

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
        ws = spreadsheet.add_worksheet(date_str, rows=500, cols=5)
        ws.append_row(["Telegram ID", "Full Name", "Activity", "Done ✅", "Time"])
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


def _ensure_daily_header(ws) -> None:
    """Best-effort: ensure daily worksheet has expected header columns."""
    try:
        header = ws.row_values(1)
        expected = ["Telegram ID", "Full Name", "Activity", "Done ✅", "Time"]
        if header == expected:
            return
        if not header:
            ws.update("A1:E1", [expected])
            return
        # If old header is present, patch it in place (keeping any extra cols)
        padded = (header + [""] * 5)[:5]
        if padded != expected:
            ws.update("A1:E1", [expected])
    except Exception:
        # Don't block check-ins if header update fails
        return


def mark_checkin(tg_user, activity: str | None = None) -> bool:
    """Add user to today's tab. Returns True if first time today, False if already marked."""
    spreadsheet = _sheet_client().open_by_key(GOOGLE_SHEET_ID)
    date_str = datetime.now(pytz.timezone(TIMEZONE)).strftime("%Y-%m-%d")
    ws = _daily_ws(spreadsheet, date_str)
    _ensure_daily_header(ws)

    records = ws.get_all_records()
    for rec in records:
        if str(rec.get("Telegram ID")) == str(tg_user.id):
            return False   # already logged today

    ws.append_row([
        tg_user.id,
        tg_user.full_name,
        activity or "",
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


def _extract_image_kind(msg) -> str | None:
    """Return 'photo' or 'document' if message contains an image, else None."""
    if msg.photo:
        return "photo"
    doc = msg.document
    if not doc:
        return None
    mime = (doc.mime_type or "").lower()
    if mime.startswith("image/"):
        return "document"
    # Some clients may send without mime_type; fall back to extension
    name = (doc.file_name or "").lower()
    if name.endswith((".png", ".jpg", ".jpeg", ".webp")):
        return "document"
    return None


async def handle_group_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fires when someone posts a workout photo/screenshot in the group chat.

    If the user has a pending check-in prompt, the image must be a reply to it and include a caption.
    """
    msg = update.message
    if not msg:
        return

    image_kind = _extract_image_kind(msg)
    if not image_kind:
        return

    # Ignore if not in the configured group
    if GROUP_CHAT_ID and str(msg.chat_id) != str(GROUP_CHAT_ID):
        return

    user = update.effective_user

    pending_all = context.application.bot_data.get("pending_checkins") or {}
    pending = pending_all.get(str(user.id))
    now_ts = datetime.now(pytz.timezone(TIMEZONE)).timestamp()

    # If a pending prompt exists, require reply-to + caption
    if pending and pending.get("chat_id") == msg.chat_id and pending.get("expires_at", 0) >= now_ts:
        prompt_message_id = pending.get("prompt_message_id")
        if not msg.reply_to_message or msg.reply_to_message.message_id != prompt_message_id:
            return
        caption = (msg.caption or "").strip()
        if not caption:
            await msg.reply_text("⚠️ Добавь подпись к фото/скрину (одним сообщением), и отправь ещё раз.")
            return
        activity = caption
        # consume pending check-in once a valid reply arrives
        context.application.bot_data["pending_checkins"].pop(str(user.id), None)
        # delete the prompt message after successful check-in
        try:
            await context.bot.delete_message(chat_id=msg.chat_id, message_id=prompt_message_id)
        except Exception:
            pass
    else:
        # No pending prompt: still allow logging from any image, but activity is generic
        activity = "Photo" if image_kind == "photo" else "Screenshot"

    try:
        is_new = mark_checkin(user, activity=activity)
    except Exception as e:
        logger.error("Failed to mark photo in sheet: %s", e)
        await msg.reply_text(
            "⚠️ Не получилось записать отметку в Google Sheets. "
            "Проверьте `GOOGLE_*` переменные окружения и доступ к таблице, затем попробуйте ещё раз.",
        )
        return

    if is_new:
        try:
            count = today_count()
        except Exception:
            count = 0
        praise = random.choice(PRAISE_PHRASES)
        await msg.reply_text(f"{praise}\n\nСегодня отметились: {count}")
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
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("✅ /checkin", callback_data="checkin")]]
        )
        await app.bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=(
                f"🌅 *Good morning, Champions!*\n\n"
                f"📅 {date_str}\n\n"
                f"💪 Нажмите кнопку ниже, затем *ответьте на сообщение бота* фото/скрином с подписью — и я отмечу вас на сегодня.\n\n"
                f"Every rep counts. Let's go! 🚀"
            ),
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
        logger.info("Daily reminder sent to group %s", GROUP_CHAT_ID)
    except Exception as e:
        logger.error("Failed to send daily reminder: %s", e)

def _user_mention_md(user) -> str:
    name = (user.full_name or user.first_name or "user").replace("[", "(").replace("]", ")")
    return f"[{name}](tg://user?id={user.id})"


def _user_mention_html(user) -> str:
    name = html.escape(user.full_name or user.first_name or "user")
    return f'<a href="tg://user?id={user.id}">{name}</a>'


async def _start_checkin_prompt(message, user, bot, bot_data) -> None:
    """Send (and track) a per-user prompt message to reply to with image+caption."""
    now = datetime.now(pytz.timezone(TIMEZONE))

    pending = bot_data.get("pending_checkins")
    if not isinstance(pending, dict):
        pending = {}
        bot_data["pending_checkins"] = pending

    prompt_text = (
        f"{_user_mention_html(user)}, ответь на это сообщение <b>фото/скрином</b> и добавь "
        f"<b>подпись</b> — чем ты занимался(ась) сегодня."
    )
    try:
        prompt = await message.reply_text(
            prompt_text,
            parse_mode="HTML",
            allow_sending_without_reply=True,
        )
    except Exception:
        prompt = await message.reply_text(
            "Ответь на это сообщение фото/скрином и добавь подпись — чем ты занимался(ась) сегодня.",
            allow_sending_without_reply=True,
        )

    pending[str(user.id)] = {
        "chat_id": message.chat_id,
        "prompt_message_id": prompt.message_id,
        "expires_at": now.timestamp() + PENDING_CHECKIN_TTL_SECONDS,
    }


async def cmd_checkin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Group command: start check-in prompt (same as button)."""
    msg = update.message
    if not msg:
        return
    if GROUP_CHAT_ID and str(msg.chat_id) != str(GROUP_CHAT_ID):
        return
    await _start_checkin_prompt(
        message=msg,
        user=update.effective_user,
        bot=context.bot,
        bot_data=context.application.bot_data,
    )


async def handle_checkin_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inline button click: start check-in prompt (same as /checkin)."""
    query = update.callback_query
    if not query:
        return
    await query.answer()

    msg = query.message
    if not msg:
        return

    if GROUP_CHAT_ID and str(msg.chat_id) != str(GROUP_CHAT_ID):
        return

    data = (query.data or "").strip()
    # Backward-compatible: older pinned messages used "start_checkin"
    if data not in {"checkin", "start_checkin"}:
        return

    user = query.from_user

    bot_data = context.application.bot_data
    await query.answer("Ок! Ответь фото/скрином с подписью.", show_alert=False)
    await _start_checkin_prompt(
        message=msg,
        user=user,
        bot=context.bot,
        bot_data=bot_data,
    )


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    async def post_init(app: Application):
        # Register commands so Telegram shows them in UI for DMs and groups
        private_cmds = [
            BotCommand("start", "Начать регистрацию"),
            BotCommand("cancel", "Отменить регистрацию"),
        ]
        group_cmds = [
            BotCommand("checkin", "✅ Отметить тренировку"),
            BotCommand("stats", "📊 Сколько отметилось сегодня"),
        ]
        try:
            await app.bot.set_my_commands(private_cmds, scope=BotCommandScopeAllPrivateChats())
            await app.bot.set_my_commands(group_cmds, scope=BotCommandScopeAllGroupChats())
        except Exception as e:
            logger.warning("Failed to set bot commands: %s", e)

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

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
    app.add_handler(CommandHandler("checkin", cmd_checkin))
    app.add_handler(CallbackQueryHandler(handle_checkin_button, pattern="^(checkin|start_checkin)$"))
    app.add_handler(
        MessageHandler(
            (filters.PHOTO | filters.Document.ALL) & (filters.ChatType.GROUPS | filters.ChatType.SUPERGROUP),
            handle_group_image,
        )
    )

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
