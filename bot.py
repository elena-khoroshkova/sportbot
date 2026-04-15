import os
import logging
import random

from telegram import Update, BotCommand, BotCommandScopeAllGroupChats, BotCommandScopeAllPrivateChats
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import re
import asyncio
from telegram import Bot

# ── Logging ──────────────────────────────────────────────────────────────────
class _RedactTokenFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            token = os.environ.get("BOT_TOKEN", "")
            if token:
                record.msg = str(record.msg).replace(token, "<BOT_TOKEN_REDACTED>")
            # Also redact common Telegram bot token patterns if present in formatted message
            if isinstance(record.args, tuple):
                record.args = tuple(
                    "<BOT_TOKEN_REDACTED>" if (isinstance(a, str) and re.search(r"\b\d{6,}:[A-Za-z0-9_-]{20,}\b", a)) else a
                    for a in record.args
                )
        except Exception:
            pass
        return True


logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Avoid leaking BOT_TOKEN via noisy HTTP client logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.WARNING)

# Redact tokens in our logs (apply to root + existing handlers)
_root = logging.getLogger()
_root.addFilter(_RedactTokenFilter())
for _h in _root.handlers:
    _h.addFilter(_RedactTokenFilter())

# Bump this string when debugging deployments.
APP_VERSION = "2026-04-15-praise-only-v1"

# ── Environment variables ─────────────────────────────────────────────────────
BOT_TOKEN = os.environ["BOT_TOKEN"]
GROUP_CHAT_ID = os.environ.get("GROUP_CHAT_ID", "")  # optional: restrict to a single group

PRAISE_PHRASES = [
    "Круто! Так держать 💪",
    "Отличная работа — горжусь тобой 🔥",
    "Засчитано! Ты молодец ✅",
    "Супер! Продолжаем в том же духе 🚀",
    "Вау, мощно! ✅",
    "Мощный старт — продолжай!",
    "Вот это темп!",
    "Сильно. Очень сильно.",
    "Отличная тренировка!",
    "Классная работа сегодня.",
    "Так держать — стабильность решает.",
    "Ты красавчик(ца) — зачёт!",
    "Пушка! Продолжаем.",
    "Прогресс видно — молодец!",
    "Супер дисциплина!",
    "Уважение за регулярность.",
    "Это было уверенно.",
    "Топ! Отличный день.",
    "Здорово! Ещё один шаг к цели.",
    "Ты на правильном пути.",
    "Вот это настрой!",
    "Стабильно и качественно.",
    "Сильный чек-ин!",
    "Отличный выбор активности!",
    "Красиво сделано!",
    "Ты вдохновляешь.",
    "Уровень! Так держать.",
    "Фантастика — продолжай!",
    "Молодец! Не сбавляй.",
    "Отличная энергия!",
    "Класс! Засчитано.",
    "Супер! Ты в игре.",
    "Это прям огонь!",
    "Чётко. По делу.",
    "Отлично поработал(а)!",
    "Горжусь твоей дисциплиной.",
    "Сильно! Так держать.",
    "Браво! Продолжаем.",
    "Отличный вклад в себя.",
    "Ты сегодня молодчина.",
    "Очень круто!",
    "Вот это мощь!",
    "Потрясающе!",
    "Супер форма!",
    "Классная работа над собой.",
    "Уверенный шаг вперёд.",
    "Плюс в карму здоровья.",
    "Отлично идёшь!",
    "Зачётный день!",
    "Ты сделал(а) это!",
    "Супер! Респект.",
    "Красава! Едем дальше.",
    "Так держать. Ты можешь больше!",
    "Сильная привычка формируется.",
    "Шикарно! Продолжай.",
    "Это было достойно.",
    "Огонь-огонь!",
    "Уровень дисциплины — топ.",
    "Очень хорошо!",
    "Стабильность — твоё оружие.",
    "Ты в отличном ритме.",
    "Это победа над ленью ✅",
    "Прекрасно отработано.",
    "Молодец! Ты растёшь.",
    "Сильный ход!",
    "Отличный результат.",
    "Супер, что отметился(ась)!",
    "Топовый чек-ин ✅",
    "Круто, что не пропускаешь.",
    "Прекрасная работа!",
    "Так и строится форма.",
    "Уважение. Продолжай!",
    "Пойдёт в копилку прогресса.",
    "Отличная привычка.",
    "Бомбически!",
    "Очень достойно.",
    "Потрясающий настрой.",
    "Красиво и стабильно.",
    "Хорошая работа, чемпион(ка)!",
    "Супер! Ты молодец-молодец.",
    "Сильный день!",
    "Уверенно закрываешь чек-ин.",
    "Класс! Продолжай в том же духе.",
    "Это точно засчитано ✅",
    "Супер-пупер!",
    "Ты двигаешься к цели.",
    "Отличная работа над базой.",
    "Так держать — шаг за шагом.",
    "Классная дисциплина ✅",
    "Круто! Ты реально стараешься.",
    "Сильная тренировка — респект.",
    "Вот это упорство!",
    "Отличный баланс и темп.",
    "Ты прокачиваешься.",
    "Уровень мотивации — огонь.",
    "Так и надо!",
    "Респект за усилия.",
    "Ты сделал(а) день!",
    "Качественно!",
    "Прям красавчик(ца)!",
    "Супер! Ещё один чек-ин в копилку.",
    "Топ. Так держать.",
    "Это уже серия — продолжай!",
    "Надёжно. Стабильно.",
    "Круто видеть твою регулярность.",
    "Сильная работа — молодец.",
    "Шаг к лучшей версии себя ✅",
    "Отлично! Держим ритм.",
    "Супер! Не останавливайся.",
    "Это было круто, правда.",
    "Ты молодец — продолжай жать!",
    "Восхитительно!",
    "Очень круто отработал(а).",
    "Красота! Засчитано ✅",
    "Ты в топе сегодня.",
    "Супер. Снимаю шляпу.",
    "Респект и уважуха.",
    "Вот это сила воли!",
    "Кайф! Так держать.",
    "Чёткий чек-ин ✅",
    "Отличный вклад в здоровье.",
    "Мощно! Продолжаем качать.",
    "Стабильная работа — топ.",
    "Ты всё ближе к цели.",
    "Супер! Отличный прогресс.",
    "Вот так и делается результат.",
    "Сильно и красиво.",
    "Отличный темп — держи!",
    "Ты красавчик(ца), без вопросов.",
    "Круто! Сегодня ты победил(а) ✅",
    "Шикарно. Продолжай.",
    "Отличная тренировка — зачёт!",
    "Супер. Ещё один кирпичик в форму.",
    "Уверенная отметка ✅",
    "Это достойно похвалы!",
    "Класс! Ты не сдаёшься.",
    "Молодец! Вижу старание.",
    "Отличная работа — продолжай.",
    "Ты реально молодчина.",
    "Огонь! Отличный день.",
    "Сильный прогресс. Так держать.",
    "Очень хорошо — продолжай в том же духе.",
    "Зачёт. Продолжаем.",
    "Классная тренировка — супер!",
    "Ты на волне ✅",
    "Отличный чек-ин! Молодец.",
    "Мощь. Дисциплина. Результат.",
    "Так и надо — уверенно.",
    "Супер! Ты делаешь себя сильнее.",
    "Хорош! Отличная работа.",
]


def _next_praise(bot_data: dict) -> str:
    """
    Return a praise phrase without repeating until all are used.
    Uses a shuffled "bag" stored in bot_data.
    """
    bag = bot_data.get("_praise_bag")
    if not isinstance(bag, list) or not bag:
        bag = list(PRAISE_PHRASES)
        random.shuffle(bag)
        bot_data["_praise_bag"] = bag
    return bag.pop()


def _is_image_document(msg) -> bool:
    doc = msg.document
    if not doc:
        return False
    mime = (doc.mime_type or "").lower()
    if mime.startswith("image/"):
        return True
    name = (doc.file_name or "").lower()
    return name.endswith((".png", ".jpg", ".jpeg", ".webp"))


# ── Bot handlers ──────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Пришли в группу фото/скрин *с подписью* — я отвечу похвалой.\n"
        "Если подписи нет — попрошу добавить."
    )
    if update.message:
        await update.message.reply_text(text, parse_mode="Markdown")


async def handle_group_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return

    # Ignore if not in the configured group
    if GROUP_CHAT_ID and str(msg.chat_id) != str(GROUP_CHAT_ID):
        return

    has_image = bool(msg.photo) or _is_image_document(msg)
    if not has_image:
        return

    caption = (msg.caption or "").strip()
    if not caption:
        await msg.reply_text("⚠️ Добавь подпись к фото/скрину (caption одним сообщением).")
        return

    await msg.reply_text(_next_praise(context.application.bot_data))


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    # If something (e.g. Albato) enabled webhook, polling will fail with Conflict.
    # Delete webhook *before* starting the application/updater.
    try:
        asyncio.run(Bot(BOT_TOKEN).delete_webhook(drop_pending_updates=True))
    except Exception as e:
        logger.warning("Preflight delete_webhook failed: %s", e)

    async def post_init(app: Application):
        logger.info("App version: %s", APP_VERSION)

        # Register commands so Telegram shows them in UI for DMs and groups
        private_cmds = [
            BotCommand("start", "Как пользоваться ботом"),
        ]
        group_cmds = [
            BotCommand("start", "Как пользоваться ботом"),
        ]
        try:
            await app.bot.set_my_commands(private_cmds, scope=BotCommandScopeAllPrivateChats())
            await app.bot.set_my_commands(group_cmds, scope=BotCommandScopeAllGroupChats())
        except Exception as e:
            logger.warning("Failed to set bot commands: %s", e)

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    async def _on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        # PTB can call error handlers with update=None.
        err = getattr(context, "error", None)
        if err is None:
            return
        logger.error("Unhandled error while processing update: %r", update, exc_info=err)

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(
        MessageHandler(
            (filters.PHOTO | filters.Document.ALL) & (filters.ChatType.GROUPS | filters.ChatType.SUPERGROUP),
            handle_group_image,
        )
    )
    app.add_error_handler(_on_error)

    logger.info("Bot is running…")
    app.run_polling(
        drop_pending_updates=True,
        close_loop=False,
    )


if __name__ == "__main__":
    main()
