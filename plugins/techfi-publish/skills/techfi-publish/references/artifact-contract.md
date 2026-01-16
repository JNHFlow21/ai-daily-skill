# Artifact Contract: `artifacts/techfi-daily/latest.json`

Publisher reads `artifacts/techfi-daily/latest.json` and maps it to:
- Telegram 5 messages (edit-or-send upsert)
- Lark Bitable `Daily` single-table archive (upsert by date)

This document defines the minimum fields the publisher expects.

## Required fields

- `meta.publish_date_bj` (YYYY-MM-DD)
- `meta.content_date_bj` (YYYY-MM-DD)
- `highlights_zh` (array of strings; recommended 5–8)
- `sections.tech.items` (array; recommended length 5)
- `sections.finance.items` (array; recommended length 5)
- `sections.geo.items` (array; recommended length 5)
- `sections.crypto.items` (array; recommended length 5)
- `telegram.messages` (array of 5 objects, keys fixed below)

## Telegram mapping

Publisher expects exactly these message keys:
- `main`
- `tech`
- `finance`
- `geo`
- `crypto`

Each message is sent/edited with:
- `text_html` using Telegram `parse_mode=HTML`

## Bitable mapping (Daily table)

Upsert key:
- `content_date_bj`

Suggested column mapping:
- `publish_date_bj` ← `meta.publish_date_bj`
- `content_date_bj` ← `meta.content_date_bj`
- `highlights` ← join `highlights_zh` with newlines
- `tech_md` / `finance_md` / `geo_md` / `crypto_md` ← render the section items into readable text
- `tg_message_ids` ← JSON mapping from message key → `message_id`
- `status` / `error` ← based on publish outcome

Notes:
- Even if the artifact is JSON-only, it should contain enough Chinese text to render section fields without calling the LLM again.

