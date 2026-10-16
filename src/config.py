from __future__ import annotations

import os
from pathlib import Path
import yaml
from dotenv import load_dotenv
from pydantic import BaseModel

from src.domain import Category, FeedSource

DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite"


class AppSettings(BaseModel):
    gemini_api_key: str
    gemini_model: str = DEFAULT_GEMINI_MODEL
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    dry_run: bool = False
    http_timeout_seconds: float = 10.0

    @classmethod
    def from_env(cls, force_dry_run: bool = False) -> AppSettings:
        load_dotenv()
        dry_run_env = os.getenv("DRY_RUN", "false").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        dry_run = force_dry_run or dry_run_env
        gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()
        gemini_model = (
            os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL).strip()
            or DEFAULT_GEMINI_MODEL
        )
        telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

        if not gemini_api_key:
            raise ValueError("Missing required environment variable: GEMINI_API_KEY")
        if not dry_run and (not telegram_bot_token or not telegram_chat_id):
            raise ValueError(
                "Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID (required when DRY_RUN is false)"
            )

        return cls(
            gemini_api_key=gemini_api_key,
            gemini_model=gemini_model,
            telegram_bot_token=telegram_bot_token,
            telegram_chat_id=telegram_chat_id,
            dry_run=dry_run,
        )


def load_categories(config_path: str | Path) -> list[Category]:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Feed configuration file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    categories: list[Category] = []
    for cat_data in raw.get("categories", []):
        cat_id = cat_data["id"]
        feeds = [
            FeedSource(
                name=feed["name"],
                url=feed["url"],
                category_id=cat_id,
            )
            for feed in cat_data.get("feeds", [])
        ]
        categories.append(
            Category(
                id=cat_id,
                title=cat_data["title"],
                min_stories=cat_data.get("min_stories", 3),
                max_stories=cat_data.get("max_stories", 5),
                feeds=feeds,
            )
        )
    return categories
