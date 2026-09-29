import html
import logging
import re

from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import ContextTypes

import ollama_client
from prompts import Answer, build_system_prompt, build_user_message, parse_answer

logger = logging.getLogger(__name__)

SEPARATOR = "---"

HELP_TEXT = (
    "<b>Как пользоваться ботом</b>\n\n"
    "1. Просто пришлите обращение клиента — получите ответ клиенту и подсказку менеджеру.\n"
    "2. Чтобы подсказка опиралась на ваш диалог в AmoCRM, вставьте его в то же сообщение "
    "через разделитель <code>---</code>:\n\n"
    "<code>клиент: Сколько стоит доставка?\n"
    "менеджер: По Москве бесплатно от 5000\n"
    "---\n"
    "а если до 5000?</code>\n\n"
    "3. Команда <code>/kb</code> — показать базу знаний.\n"
    "4. Команда <code>/status</code> — проверить связь с моделью."
)


def split_message(text: str) -> tuple[str, str]:
    """Разделяет сообщение на контекст AmoCRM и обращение клиента."""
    if SEPARATOR not in text:
        return "", text.strip()
    context, _, client = text.partition(SEPARATOR)
    return context.strip(), client.strip()


def format_answer(answer: Answer) -> str:
    hint = answer.manager_hint or "—"
    section = f"\n\n📚 <b>Раздел БЗ:</b> {html.escape(answer.kb_section)}" if answer.kb_section else ""
    return (
        "💬 <b>Ответ клиенту</b>\n"
        f"{html.escape(answer.client_response)}\n\n"
        "🎯 <b>Подсказка менеджеру</b>\n"
        f"{html.escape(hint)}"
        f"{section}"
    )


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Привет! Я AI-ассистент продаж.\n\n"
        "Пришлите обращение клиента — я сверюсь с базой знаний и отдам два блока: "
        "ответ клиенту и подсказку по допродажам.\n\n" + HELP_TEXT,
        parse_mode=ParseMode.HTML,
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT, parse_mode=ParseMode.HTML)


async def cmd_kb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from prompts import load_kb

    kb = load_kb()
    for chunk_start in range(0, len(kb), 4000):
        await update.message.reply_text(kb[chunk_start : chunk_start + 4000])


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ok, message = await ollama_client.ping()
    await update.message.reply_text(("✅ " if ok else "⚠️ ") + html.escape(message), parse_mode=ParseMode.HTML)


async def cmd_crm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = re.sub(r"^/\w+(?:@\w+)?", "", update.message.text or "").strip()
    if SEPARATOR not in text:
        await update.message.reply_text(
            "Формат команды <code>/crm</code>: контекст диалога из AmoCRM, затем разделитель "
            "<code>---</code>, затем обращение клиента.\n\n"
            "<code>/crm клиент просил скидку\n---\nа если возьму два комплекта?</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    crm_context, client_message = split_message(text)
    await generate_and_reply(update, crm_context, client_message)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    crm_context, client_message = split_message(update.message.text or "")
    await generate_and_reply(update, crm_context, client_message)


async def generate_and_reply(update: Update, crm_context: str, client_message: str) -> None:
    if not client_message:
        await update.message.reply_text("Пустое обращение клиента. Пришлите текст после разделителя `---`.")
        return
    await update.message.chat.send_action(ChatAction.TYPING)
    try:
        raw = await ollama_client.chat_json(build_system_prompt(), build_user_message(client_message, crm_context))
        answer = parse_answer(raw)
    except (ollama_client.OllamaError, ValueError) as exc:
        logger.exception("Ошибка генерации ответа")
        await update.message.reply_text(
            "⚠️ Не удалось получить ответ модели: " + html.escape(str(exc)),
            parse_mode=ParseMode.HTML,
        )
        return

    await update.message.reply_text(format_answer(answer), parse_mode=ParseMode.HTML)
