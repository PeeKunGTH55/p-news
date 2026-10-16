from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pydantic import BaseModel, Field

BANGKOK_TZ = ZoneInfo("Asia/Bangkok")


class FeedSource(BaseModel):
    """An external syndication endpoint assigned to a specific Category."""

    name: str
    url: str
    category_id: str


class Category(BaseModel):
    """A thematic grouping within the Daily Briefing."""

    id: str
    title: str
    min_stories: int = 3
    max_stories: int = 5
    feeds: list[FeedSource] = Field(default_factory=list)


class RawArticle(BaseModel):
    """An unprocessed news entry retrieved from a Feed Source."""

    category_id: str
    source_name: str
    title: str
    url: str
    summary: str = ""
    published_at: datetime


class CuratedStory(BaseModel):
    """A selected news item distilled into a Thai headline, key-point bullets, and source reference."""

    headline: str = Field(description="Concise Thai headline (1 line)")
    bullets: list[str] = Field(
        default_factory=list,
        description="2 to 3 key takeaway bullet points in Thai",
    )
    source_name: str = Field(description="Name of the primary news source")
    source_url: str = Field(description="Direct URL to the original article")


class CuratedCategory(BaseModel):
    """Curated stories belonging to a single Category."""

    category_id: str
    stories: list[CuratedStory] = Field(default_factory=list)


class DailyBriefing(BaseModel):
    """The complete daily edition composed of Curated Stories across all Categories."""

    briefing_date: str = Field(description="Formatted date in Asia/Bangkok (YYYY-MM-DD)")
    categories: list[CuratedCategory] = Field(default_factory=list)


class PublicationWindow(BaseModel):
    """
    The time range in Asia/Bangkok used to qualify a Raw Article as belonging to today's edition.
    Primary window: 00:00 to reference_time (default 10:00) of the current day.
    Fallback window: expands back to 21:00 of the previous day when a Category has fewer than
    min_raw_articles in the primary window.
    """

    primary_start: datetime
    fallback_start: datetime
    end: datetime
    min_raw_articles: int = 5

    @classmethod
    def for_reference_time(
        cls,
        now: datetime | None = None,
        min_raw_articles: int = 5,
    ) -> PublicationWindow:
        bkk_now = (now or datetime.now(BANGKOK_TZ)).astimezone(BANGKOK_TZ)
        primary_start = bkk_now.replace(hour=0, minute=0, second=0, microsecond=0)
        fallback_start = (primary_start - timedelta(days=1)).replace(
            hour=21, minute=0, second=0, microsecond=0
        )
        return cls(
            primary_start=primary_start,
            fallback_start=fallback_start,
            end=bkk_now,
            min_raw_articles=min_raw_articles,
        )

    def in_primary(self, published_at: datetime) -> bool:
        bkk_pub = published_at.astimezone(BANGKOK_TZ)
        return self.primary_start <= bkk_pub <= self.end

    def in_fallback(self, published_at: datetime) -> bool:
        bkk_pub = published_at.astimezone(BANGKOK_TZ)
        return self.fallback_start <= bkk_pub <= self.end

    def filter_category_articles(
        self, articles: list[RawArticle]
    ) -> tuple[list[RawArticle], bool]:
        """
        Filters articles for a single Category.
        Returns (qualified_articles, used_fallback).
        """
        primary = [a for a in articles if self.in_primary(a.published_at)]
        if len(primary) >= self.min_raw_articles:
            return primary, False

        fallback = [a for a in articles if self.in_fallback(a.published_at)]
        if len(fallback) > len(primary):
            return fallback, True
        return primary, False
