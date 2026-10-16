# Daily News Briefing

A scheduled curation and delivery system that gathers news from public feeds, selects and summarizes key stories in Thai by category, and delivers a daily briefing to Telegram.

## Language

**Feed Source**:
An external syndication endpoint (such as an RSS or Atom feed) assigned to a specific Category from which news items are collected.
_Avoid_: Channel, scraper target, API endpoint

**Category**:
A thematic grouping within the Daily Briefing (Thailand Top News, Economy & Business, World & Technology).
_Avoid_: Tag, topic, section

**Raw Article**:
An unprocessed news entry retrieved from a Feed Source before time-window filtering, deduplication, or AI curation.
_Avoid_: Post, item, feed entry

**Curated Story**:
A selected news item distilled into a Thai headline, key-point bullets, and source reference for inclusion in a Category.
_Avoid_: Summary item, digested article, news snippet

**Daily Briefing**:
The complete daily edition composed of Curated Stories across all Categories, formatted and delivered to the recipient for a given day.
_Avoid_: Newsletter, digest, report, batch

**Publication Window**:
The time range in `Asia/Bangkok` used to qualify a Raw Article as belonging to today's edition (`00:00–10:00` of the current day, expanding back to `21:00` of the previous day for any Category with fewer than five Raw Articles).
_Avoid_: Scrape interval, lookback period, TTL

