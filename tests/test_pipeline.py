from __future__ import annotations

from datetime import datetime, timezone

from src.collector import deduplicate_articles
from src.config import load_categories
from src.domain import (
    BANGKOK_TZ,
    Category,
    CuratedCategory,
    CuratedStory,
    DailyBriefing,
    PublicationWindow,
    RawArticle,
)
from src.formatter import TELEGRAM_MAX_MESSAGE_LENGTH, format_briefing_messages


def _make_article(
    title: str,
    url: str,
    bkk_dt: datetime,
    category_id: str = "thailand_top",
) -> RawArticle:
    return RawArticle(
        category_id=category_id,
        source_name="Test Source",
        title=title,
        url=url,
        summary="Test summary",
        published_at=bkk_dt,
    )


def test_publication_window_primary_and_fallback() -> None:
    ref_now = datetime(2026, 10, 16, 10, 0, 0, tzinfo=BANGKOK_TZ)
    window = PublicationWindow.for_reference_time(now=ref_now, min_raw_articles=3)

    assert window.primary_start == datetime(2026, 10, 16, 0, 0, 0, tzinfo=BANGKOK_TZ)
    assert window.fallback_start == datetime(2026, 10, 15, 21, 0, 0, tzinfo=BANGKOK_TZ)

    # Case 1: Only 2 articles in primary window (<3), 2 in fallback (21:30 & 22:30 yesterday) -> triggers fallback
    articles_sparse = [
        _make_article(
            "Morning 1",
            "https://example.com/1",
            datetime(2026, 10, 16, 8, 30, tzinfo=BANGKOK_TZ),
        ),
        _make_article(
            "Morning 2",
            "https://example.com/2",
            datetime(2026, 10, 16, 7, 15, tzinfo=BANGKOK_TZ),
        ),
        _make_article(
            "Late Night 1",
            "https://example.com/3",
            datetime(2026, 10, 15, 22, 30, tzinfo=BANGKOK_TZ),
        ),
        _make_article(
            "Too Old",
            "https://example.com/4",
            datetime(2026, 10, 15, 19, 0, tzinfo=BANGKOK_TZ),
        ),
    ]
    qualified, used_fallback = window.filter_category_articles(articles_sparse)
    assert used_fallback is True
    assert len(qualified) == 3

    # Case 2: 3 articles in primary window (>=3) -> stays in primary window only
    articles_enough = articles_sparse + [
        _make_article(
            "Morning 3",
            "https://example.com/5",
            datetime(2026, 10, 16, 9, 45, tzinfo=BANGKOK_TZ),
        )
    ]
    qualified_primary, used_fallback_primary = window.filter_category_articles(
        articles_enough
    )
    assert used_fallback_primary is False
    assert len(qualified_primary) == 3
    assert all(a.title.startswith("Morning") for a in qualified_primary)


def test_utc_timestamp_converts_to_bangkok_window() -> None:
    ref_now = datetime(2026, 10, 16, 10, 0, 0, tzinfo=BANGKOK_TZ)
    window = PublicationWindow.for_reference_time(now=ref_now, min_raw_articles=1)

    # 2026-10-16 01:00 UTC == 2026-10-16 08:00 Asia/Bangkok (inside primary window)
    utc_pub = datetime(2026, 10, 16, 1, 0, 0, tzinfo=timezone.utc)
    assert window.in_primary(utc_pub) is True


def test_deduplicate_articles_by_url_and_title() -> None:
    t1 = datetime(2026, 10, 16, 8, 0, tzinfo=BANGKOK_TZ)
    t2 = datetime(2026, 10, 16, 9, 0, tzinfo=BANGKOK_TZ)
    items = [
        _make_article("หุ้นไทยปิดบวก 10 จุด!", "https://example.com/a/", t1),
        _make_article("หุ้นไทยปิดบวก 10 จุด", "https://example.com/b", t2),
        _make_article("พาดหัวต่างแต่ลิงก์เดิม", "https://example.com/b/", t1),
    ]
    deduped = deduplicate_articles(items)
    assert len(deduped) == 1
    assert deduped[0].published_at == t2
    assert deduped[0].url == "https://example.com/b"


def test_format_briefing_splits_when_exceeding_telegram_limit() -> None:
    categories = [
        Category(id="thailand_top", title="🇹🇭 ข่าวเด่นในไทย"),
        Category(id="economy_business", title="📈 เศรษฐกิจ & ธุรกิจ"),
        Category(id="world_tech", title="🌍 ข่าวเด่นรอบโลก"),
    ]
    long_bullet = "ข" * 350
    briefing = DailyBriefing(
        briefing_date="2026-10-16",
        categories=[
            CuratedCategory(
                category_id=cat.id,
                stories=[
                    CuratedStory(
                        headline=f"หัวข้อข่าวที่ {i} ของหมวด {cat.id}",
                        bullets=[long_bullet, long_bullet],
                        source_name="Thai PBS",
                        source_url=f"https://example.com/{cat.id}/{i}",
                    )
                    for i in range(1, 5)
                ],
            )
            for cat in categories
        ],
    )

    messages = format_briefing_messages(briefing, categories)
    assert len(messages) == 3
    assert all(len(m) <= TELEGRAM_MAX_MESSAGE_LENGTH for m in messages)


def test_load_feeds_config() -> None:
    categories = load_categories("config/feeds.yaml")
    assert len(categories) == 3
    assert [c.id for c in categories] == [
        "thailand_top",
        "economy_business",
        "world_tech",
    ]
    assert all(len(c.feeds) >= 3 for c in categories)


def test_model_candidate_chain() -> None:
    from src.curator import build_model_candidate_chain

    chain = build_model_candidate_chain("gemini-3.8-flash")
    assert chain == [
        "gemini-3.8-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
    ]

