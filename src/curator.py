from __future__ import annotations

import json
import logging
import re
import time
from google import genai
from google.genai import errors, types

from src.domain import Category, DailyBriefing, RawArticle

logger = logging.getLogger(__name__)

FALLBACK_MODELS: tuple[str, ...] = (
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.8-flash",
)

SYSTEM_INSTRUCTION = """คุณคือบรรณาธิการข่าวอาวุโส มีหน้าที่คัดเลือกและสรุปข่าวประจำวัน (Daily Briefing) เป็นภาษาไทยที่กระชับ ชัดเจน เป็นกลาง และอ่านง่ายบนหน้าจอมือถือ

กฎเหล็กในการคัดเลือกและสรุปข่าว:
1. คัดเลือกข่าวที่สำคัญและมีผลกระทบสูงในแต่ละหมวดหมู่ (Category) ตามจำนวน min_stories ถึง max_stories ที่กำหนด (ปกติ 3-5 เรื่องต่อหมวดหมู่)
2. ห้ามเลือกข่าวเรื่องเดียวกันซ้ำข้ามหมวดหมู่เด็ดขาด (Cross-Category Deduplication): หากข่าวใดเข้าข่ายมากกว่า 1 หมวดหมู่ ให้เลือกใส่ในหมวดหมู่ที่ตรงประเด็นที่สุดเพียงหมวดหมู่เดียว
3. หากหลายสำนักข่าวรายงานประเด็นเดียวกัน ให้ยุบรวมเป็น 1 Curated Story และเลือก source_url จากแหล่งข่าวต้นทางที่ชัดเจนที่สุด
4. ในแต่ละ Curated Story:
   - headline: พาดหัวสรุปใจความสำคัญเป็นภาษาไทย 1 บรรทัด กระชับ ตรงประเด็น
   - bullets: สรุปประเด็นหลัก 2-3 ข้อ (ข้อละ 1 ประโยคสั้นๆ ได้ใจความ)
   - source_name และ source_url: ต้องตรงกับข้อมูลใน Raw Articles ที่ส่งให้เท่านั้น ห้ามแต่ง URL เองเด็ดขาด

ตอบกลับเป็น JSON Object เท่านั้น ตามโครงสร้างดังนี้:
{
  "briefing_date": "YYYY-MM-DD",
  "categories": [
    {
      "category_id": "string (ต้องตรงกับ category_id ที่ส่งให้)",
      "stories": [
        {
          "headline": "พาดหัวสรุปภาษาไทย 1 บรรทัด",
          "bullets": ["ประเด็นหลักข้อ 1", "ประเด็นหลักข้อ 2"],
          "source_name": "ชื่อสำนักข่าว",
          "source_url": "https://..."
        }
      ]
    }
  ]
}
"""


def _extract_json_text(raw_text: str) -> str:
    text = raw_text.strip()
    fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence_match:
        return fence_match.group(1).strip()
    return text


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
                        "summary": art.summary[:200],
                    }
                    for art in articles_by_category.get(cat.id, [])
                ],
            }
            for cat in categories
        ],
    }

    return (
        "จงคัดเลือกและสรุปข่าวประจำวันจาก Raw Articles ด้านล่างนี้ให้อยู่ในโครงสร้าง JSON ที่กำหนด:\n\n"
        + json.dumps(payload, ensure_ascii=False)
    )


def build_model_candidate_chain(primary_model: str) -> list[str]:
    """Returns an ordered, deduplicated list of models starting with primary_model."""
    chain: list[str] = [primary_model]
    for candidate in FALLBACK_MODELS:
        if candidate not in chain:
            chain.append(candidate)
    return chain


def curate_daily_briefing(
    api_key: str,
    model_name: str,
    briefing_date: str,
    categories: list[Category],
    articles_by_category: dict[str, list[RawArticle]],
) -> DailyBriefing:
    """
    Runs a single-pass Gemini JSON-mode call to produce the DailyBriefing.
    Automatically falls back across FALLBACK_MODELS when a model returns 503/429/404.
    """
    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(
            retry_options=types.HttpRetryOptions(attempts=2)
        ),
    )
    prompt = build_curation_prompt(briefing_date, categories, articles_by_category)
    candidate_models = build_model_candidate_chain(model_name)
    last_error: Exception | None = None

    for candidate in candidate_models:
        try:
            logger.info("Requesting curation from Gemini model '%s'...", candidate)
            response = client.models.generate_content(
                model=candidate,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    response_mime_type="application/json",
                    temperature=0.2,
                ),
            )

            if not response.text:
                raise RuntimeError(
                    f"Gemini model '{candidate}' returned an empty response."
                )

            json_str = _extract_json_text(response.text)
            briefing = DailyBriefing.model_validate_json(json_str)
            logger.info("Successfully curated Daily Briefing using '%s'", candidate)
            return briefing

        except errors.APIError as exc:
            last_error = exc
            status_code = getattr(exc, "code", None)
            if status_code in (404, 429, 500, 502, 503, 504):
                logger.warning(
                    "Model '%s' unavailable (HTTP %s). Switching to next fallback model...",
                    candidate,
                    status_code,
                )
                time.sleep(1)
                continue
            raise
        except Exception as exc:
            last_error = exc
            logger.warning(
                "Error calling model '%s': %s. Switching to next fallback model...",
                candidate,
                exc,
            )
            time.sleep(1)

    raise RuntimeError(
        f"All Gemini models failed ({', '.join(candidate_models)}). Last error: {last_error}"
    ) from last_error
