from __future__ import annotations

import html
from src.domain import Category, CuratedCategory, CuratedStory, DailyBriefing

TELEGRAM_MAX_MESSAGE_LENGTH = 4096


def _escape_url(url: str) -> str:
    return html.escape(url.strip(), quote=True)


def format_story_html(index: int, story: CuratedStory) -> str:
    headline = html.escape(story.headline.strip())
    source_name = html.escape(story.source_name.strip() or "ที่มา")
    source_url = _escape_url(story.source_url)

    lines = [f"<b>{index}. {headline}</b>"]
    for bullet in story.bullets:
        cleaned_bullet = html.escape(bullet.strip().lstrip("•-* "))
        if cleaned_bullet:
            lines.append(f"  • {cleaned_bullet}")
    lines.append(f'  🔗 <a href="{source_url}">{source_name}</a>')
    return "\n".join(lines)


def format_category_block(
    category: Category,
    curated: CuratedCategory | None,
) -> str:
    cat_title = html.escape(category.title)
    header = f"<b>{cat_title}</b>"

    if not curated or not curated.stories:
        return f"{header}\n<i>ไม่มีข่าวเด่นในหมวดหมู่นี้</i>"

    story_blocks = [
        format_story_html(idx, story)
        for idx, story in enumerate(curated.stories, start=1)
    ]
    return header + "\n\n" + "\n\n".join(story_blocks)


def _split_oversized_block(
    block: str,
    max_length: int = TELEGRAM_MAX_MESSAGE_LENGTH,
) -> list[str]:
    """Splits a single category block by double-newline boundaries if it exceeds max_length."""
    if len(block) <= max_length:
        return [block]

    parts = block.split("\n\n")
    chunks: list[str] = []
    current = ""

    for part in parts:
        candidate = part if not current else f"{current}\n\n{part}"
        if len(candidate) <= max_length:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = part[:max_length]

    if current:
        chunks.append(current)
    return chunks


def format_briefing_messages(
    briefing: DailyBriefing,
    categories: list[Category],
    max_length: int = TELEGRAM_MAX_MESSAGE_LENGTH,
) -> list[str]:
    """
    Formats a DailyBriefing into Telegram HTML message(s).
    Returns a single message if total length <= max_length; otherwise splits by Category.
    """
    curated_map: dict[str, CuratedCategory] = {
        c.category_id: c for c in briefing.categories
    }

    header = f"🗞 <b>สรุปข่าวประจำวัน ({html.escape(briefing.briefing_date)})</b>"
    category_blocks = [
        format_category_block(cat, curated_map.get(cat.id))
        for cat in categories
    ]

    single_message = header + "\n\n" + "\n\n━━━━━━━━━━━━━━\n\n".join(category_blocks)
    if len(single_message) <= max_length:
        return [single_message]

    messages: list[str] = []
    for idx, block in enumerate(category_blocks):
        if idx == 0:
            block_with_header = f"{header}\n\n{block}"
            messages.extend(_split_oversized_block(block_with_header, max_length))
        else:
            messages.extend(_split_oversized_block(block, max_length))

    return messages
