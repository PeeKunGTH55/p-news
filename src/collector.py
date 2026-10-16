from __future__ import annotations

import html
import logging
import re
from calendar import timegm
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import feedparser
import httpx

from src.domain import (
    BANGKOK_TZ,
    Category,
    FeedSource,
    PublicationWindow,
    RawArticle,
)

logger = logging.getLogger(__name__)

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
_USER_AGENT = (
    "Mozilla/5.0 (compatible; DailyNewsBriefingBot/1.0; +https://github.com)"
)


def clean_html_text(raw: str, max_len: int = 350) -> str:
    """Strips HTML tags, unescapes entities, and normalizes whitespace."""
    if not raw:
        return ""
    text = html.unescape(_HTML_TAG_RE.sub(" ", raw))
    text = _WHITESPACE_RE.sub(" ", text).strip()
    if len(text) > max_len:
        return text[: max_len - 1].rstrip() + "…"
    return text


def normalize_title_key(title: str) -> str:
    """Normalizes a headline for fast near-duplicate detection."""
    cleaned = re.sub(r"[^\w\u0E00-\u0E7F]+", "", title.lower())
    return cleaned[:80]


def parse_entry_datetime(entry: dict[str, Any]) -> datetime | None:
    """Extracts and converts an RSS/Atom entry timestamp into Asia/Bangkok."""
    for date_str_key in ("published", "updated", "created"):
        raw_val = entry.get(date_str_key)
        if isinstance(raw_val, str) and raw_val.strip():
            try:
                dt = parsedate_to_datetime(raw_val.strip())
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(BANGKOK_TZ)
            except Exception:
                try:
                    iso_dt = datetime.fromisoformat(
                        raw_val.strip().replace("Z", "+00:00")
                    )
                    if iso_dt.tzinfo is None:
                        iso_dt = iso_dt.replace(tzinfo=timezone.utc)
                    return iso_dt.astimezone(BANGKOK_TZ)
                except Exception:
                    pass

    for parsed_key in ("published_parsed", "updated_parsed", "created_parsed"):
        struct_time = entry.get(parsed_key)
        if struct_time is not None:
            try:
                ts = timegm(struct_time)
                return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(
                    BANGKOK_TZ
                )
            except Exception:
                continue

    return None


def fetch_feed_articles(
    client: httpx.Client,
    feed: FeedSource,
) -> list[RawArticle]:
    """Fetches and parses a single FeedSource, returning RawArticles with valid timestamps."""
    try:
        response = client.get(feed.url, follow_redirects=True)
        response.raise_for_status()
    except Exception as exc:
        logger.warning(
            "Skipping unavailable Feed Source '%s' (%s): %s",
            feed.name,
            feed.url,
            exc,
        )
        return []

    parsed = feedparser.parse(response.content)
    articles: list[RawArticle] = []

    for entry in getattr(parsed, "entries", []):
        title = clean_html_text(entry.get("title", ""), max_len=220)
        url = (entry.get("link") or "").strip()
        if not title or not url:
            continue

        published_at = parse_entry_datetime(entry)
        if published_at is None:
            continue

        raw_summary = entry.get("summary") or entry.get("description") or ""
        summary = clean_html_text(raw_summary, max_len=350)

        articles.append(
            RawArticle(
                category_id=feed.category_id,
                source_name=feed.name,
                title=title,
                url=url,
                summary=summary,
                published_at=published_at,
            )
        )

    logger.info("Fetched %d entries from '%s'", len(articles), feed.name)
    return articles


def deduplicate_articles(articles: list[RawArticle]) -> list[RawArticle]:
    """Removes duplicate RawArticles by URL or normalized title, keeping newest first."""
    sorted_articles = sorted(
        articles, key=lambda a: a.published_at, reverse=True
    )
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    unique: list[RawArticle] = []

    for article in sorted_articles:
        url_key = article.url.split("#")[0].rstrip("/")
        title_key = normalize_title_key(article.title)
        if not title_key or url_key in seen_urls or title_key in seen_titles:
            continue
        seen_urls.add(url_key)
        seen_titles.add(title_key)
        unique.append(article)

    return unique


def collect_qualified_articles(
    categories: list[Category],
    window: PublicationWindow,
    timeout_seconds: float = 10.0,
    max_per_category: int = 20,
) -> dict[str, list[RawArticle]]:
    """
    Collects, filters via PublicationWindow (with per-category fallback), and deduplicates
    RawArticles across all configured Categories.
    """
    qualified_by_category: dict[str, list[RawArticle]] = {}

    with httpx.Client(
        timeout=timeout_seconds,
        headers={"User-Agent": _USER_AGENT},
    ) as client:
        for category in categories:
            raw_for_cat: list[RawArticle] = []
            for feed in category.feeds:
                raw_for_cat.extend(fetch_feed_articles(client, feed))

            deduped = deduplicate_articles(raw_for_cat)
            filtered, used_fallback = window.filter_category_articles(deduped)
            qualified_by_category[category.id] = filtered[:max_per_category]

            logger.info(
                "Category '%s': %d raw -> %d unique -> %d in PublicationWindow (fallback=%s)",
                category.id,
                len(raw_for_cat),
                len(deduped),
                len(qualified_by_category[category.id]),
                used_fallback,
            )

    total_collected = sum(len(v) for v in qualified_by_category.values())
    if total_collected == 0:
        raise RuntimeError(
            "No Raw Articles qualified across any Category within the Publication Window."
        )

    return qualified_by_category
