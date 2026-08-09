from __future__ import annotations

from datetime import tzinfo
from html import escape

from .models import FormattedMessage, MessageEnvelope, Rule

TELEGRAM_TEXT_LIMIT = 4096
TRUNCATION_MARKER = "\n\n… [текст сокращён]"


def source_message_link(message: MessageEnvelope) -> str | None:
    if message.source_username:
        return f"https://t.me/{message.source_username}/{message.source_message_id}"
    raw = str(message.source_peer_id)
    if message.source_peer_type in {"channel", "supergroup"} and raw.startswith("-100"):
        return f"https://t.me/c/{raw[4:]}/{message.source_message_id}"
    return None


def format_copy(
    message: MessageEnvelope,
    matched_rules: tuple[Rule, ...],
    *,
    local_timezone: tzinfo | None = None,
    limit: int = TELEGRAM_TEXT_LIMIT,
    additional_content: str | None = None,
) -> FormattedMessage:
    labels = ", ".join(rule.pattern for rule in matched_rules)
    primary = matched_rules[0].pattern if matched_rules else "совпадение"
    if not primary.startswith("#"):
        primary = f"#{primary.replace(' ', '_')}"
    shown_time = message.source_timestamp.astimezone(local_timezone)
    author = message.author_name or "Не указан"
    link = source_message_link(message)

    header_lines = [
        f"<b>{escape(primary)}</b>",
        "",
        f"<b>Источник:</b> {escape(message.source_name)}",
        f"<b>Автор:</b> {escape(author)}",
        f"<b>Время:</b> {escape(shown_time.strftime('%d.%m.%Y, %H:%M %Z'))}",
        f"<b>Совпадение:</b> {escape(labels)}",
        "",
    ]
    footer = f'\n\n<a href="{escape(link, quote=True)}">Открыть исходное сообщение</a>' if link else ""
    prefix = "\n".join(header_lines)
    raw_body = message.text or ""
    if additional_content:
        raw_body += "\n\nДополнение ИИ:\n" + additional_content.strip()
    escaped_body = escape(raw_body)
    candidate = prefix + escaped_body + footer
    if len(candidate) <= limit:
        return FormattedMessage(candidate)

    available = max(0, limit - len(prefix) - len(footer) - len(TRUNCATION_MARKER))
    low, high = 0, len(raw_body)
    while low < high:
        middle = (low + high + 1) // 2
        if len(escape(raw_body[:middle])) <= available:
            low = middle
        else:
            high = middle - 1
    truncated = escape(raw_body[:low]) + TRUNCATION_MARKER
    return FormattedMessage(prefix + truncated + footer)


def format_ai_addition(
    content: str, *, limit: int = TELEGRAM_TEXT_LIMIT
) -> FormattedMessage:
    prefix = "<b>Дополнение ИИ:</b>\n"
    content = content.strip()
    escaped = escape(content)
    if len(prefix) + len(escaped) <= limit:
        return FormattedMessage(prefix + escaped)
    available = max(0, limit - len(prefix) - len(TRUNCATION_MARKER))
    low, high = 0, len(content)
    while low < high:
        middle = (low + high + 1) // 2
        if len(escape(content[:middle])) <= available:
            low = middle
        else:
            high = middle - 1
    return FormattedMessage(prefix + escape(content[:low]) + TRUNCATION_MARKER)
