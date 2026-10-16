from __future__ import annotations

import json
import logging
from google import genai
from google.genai import types

from src.domain import Category, DailyBriefing, RawArticle

logger = logging.getLogger(__name__)

SYSTEM_INSTRUCTION = """คุณคือบรรณาธิการข่าวอาวุโส มีหน้าที่คัดเลือกและสรุปข่าวประจำวัน (Daily Briefing) เป็นภาษาไทยที่กระชับ ชัดเจน เป็นกลาง และอ่านง่ายบนหน้าจอมือถือ

กฎเหล็กในการคัดเลือกและสรุปข่าว:
1. คัดเลือกข่าวที่สำคัญและมีผลกระทบสูงในแต่ละหมวดหมู่ (Category) ตามจำนวน min_stories ถึง max_stories ที่กำหนด (ปกติ 3-5 เรื่องต่อหมวดหมู่)
2. ห้ามเลือกข่าวเรื่องเดียวกันซ้ำข้ามหมวดหมู่เด็ดขาด (Cross-Category Deduplication): หากข่าวใดเข้าข่ายมากกว่า 1 หมวดหมู่ ให้เลือกใส่ในหมวดหมู่ที่ตรงประเด็นที่สุดเพียงหมวดหมู่เดียว
3. หากหลายสำนักข่าวรายงานประเด็นเดียวกัน ให้ยุบรวมเป็น 1 Curated Story และเลือก source_url จากแหล่งข่าวต้นทางที่ชัดเจนที่สุด
4. ในแต่ละ Curated Story:
   - headline: พาดหัวสรุปใจความสำคัญเป็นภาษาไทย 1 บรรทัด กระชับ ตรงประเด็น
   - bullets: สรุปประเด็นหลัก 2-3 ข้อ (ข้อละ 1 ประโยคสั้นๆ ได้ใจความ)
   - source_name และ source_url: ต้องตรงกับข้อมูลใน Raw Articles ที่ส่งให้เท่านั้น ห้ามแต่ง URL เองเด็ดขาด
"""


def build_curation_prompt(
    briefing_date: str,
    categories: list[Category],
    articles_by_category: dict[str, list[RawArticle]],
) -> str:
    payload = {
        "briefing_date": briefing_date,
        "categories": [
            {
                "category_id": cat.id,
                "category_title": cat.title,
                "min_stories": cat.min_stories,
                "max_stories": cat.max_stories,
                "raw_articles": [
                    {
                        "source_name": art.source_name,
                        "title": art.title,
                        "url": art.url,
                        "published_at": art.published_at.strftime("%Y-%m-%d %H:%M"),
                        "summary": art.summary,
                    }
                    for art in articles_by_category.get(cat.id, [])
                ],
            }
            for cat in categories
        ],
    }

    return (
        "จงคัดเลือกและสรุปข่าวประจำวันจาก Raw Articles ด้านล่างนี้ให้อยู่ในโครงสร้าง JSON ตาม Schema ที่กำหนด:\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )


def curate_daily_briefing(
    api_key: str,
    model_name: str,
    briefing_date: str,
    categories: list[Category],
    articles_by_category: dict[str, list[RawArticle]],
) -> DailyBriefing:
    """Runs a single-pass Gemini structured-output call to produce the DailyBriefing."""
    client = genai.Client(api_key=api_key)
    prompt = build_curation_prompt(briefing_date, categories, articles_by_category)

    logger.info("Requesting curation from Gemini model '%s'...", model_name)
    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=DailyBriefing,
            temperature=0.2,
        ),
    )

    if not response.text:
        raise RuntimeError("Gemini returned an empty response.")

    return DailyBriefing.model_validate_json(response.text)
