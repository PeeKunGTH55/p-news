from __future__ import annotations

import logging
import httpx

logger = logging.getLogger(__name__)


def send_telegram_messages(
    bot_token: str,
    chat_id: str,
    messages: list[str],
    timeout_seconds: float = 15.0,
) -> None:
    """Sends one or more HTML-formatted messages to the target Telegram Chat ID."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    with httpx.Client(timeout=timeout_seconds) as client:
        for idx, text in enumerate(messages, start=1):
            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }
            response = client.post(url, json=payload)
            if response.status_code != 200:
                raise RuntimeError(
                    f"Telegram API error on message {idx}/{len(messages)} "
                    f"(HTTP {response.status_code}): {response.text}"
                )
            logger.info(
                "Delivered Telegram message %d/%d (%d chars)",
                idx,
                len(messages),
                len(text),
            )
