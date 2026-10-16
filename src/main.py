from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from src.collector import collect_qualified_articles
from src.config import AppSettings, load_categories
from src.curator import curate_daily_briefing
from src.domain import BANGKOK_TZ, PublicationWindow
from src.formatter import format_briefing_messages
from src.notifier import send_telegram_messages


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Daily News Briefing Bot - Collects RSS, curates via Gemini, sends to Telegram."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/feeds.yaml"),
        help="Path to the feeds YAML configuration file (default: config/feeds.yaml)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run collection and AI curation, then print output to stdout without sending to Telegram.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    args = parse_args(argv)
    settings = AppSettings.from_env(force_dry_run=args.dry_run)
    categories = load_categories(args.config)

    now_bkk = datetime.now(BANGKOK_TZ)
    window = PublicationWindow.for_reference_time(now=now_bkk)
    briefing_date = now_bkk.strftime("%Y-%m-%d")

    logging.info(
        "Starting Daily Briefing for %s (Primary window: %s to %s, Fallback: %s)",
        briefing_date,
        window.primary_start.strftime("%Y-%m-%d %H:%M"),
        window.end.strftime("%Y-%m-%d %H:%M"),
        window.fallback_start.strftime("%Y-%m-%d %H:%M"),
    )

    qualified_articles = collect_qualified_articles(
        categories=categories,
        window=window,
        timeout_seconds=settings.http_timeout_seconds,
    )

    briefing = curate_daily_briefing(
        api_key=settings.gemini_api_key,
        model_name=settings.gemini_model,
        briefing_date=briefing_date,
        categories=categories,
        articles_by_category=qualified_articles,
    )

    messages = format_briefing_messages(briefing=briefing, categories=categories)

    if settings.dry_run:
        print("\n" + "=" * 60)
        print(f"DRY RUN OUTPUT ({len(messages)} message(s))")
        print("=" * 60)
        for idx, msg in enumerate(messages, start=1):
            print(f"\n--- Message {idx}/{len(messages)} ({len(msg)} chars) ---")
            print(msg)
        return 0

    send_telegram_messages(
        bot_token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
        messages=messages,
    )
    logging.info("Daily Briefing completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
