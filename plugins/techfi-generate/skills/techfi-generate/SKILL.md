---
name: techfi-generate
description: Generates TechFiDaily content only (no publishing). Fetches English hot news via stable RSS sources across 4 sections (Tech, Finance, Geopolitics, Crypto), dedupes and selects Top 5 per section, then uses LLM to produce easy-to-read Chinese explanations +点评 and optional image_url. Outputs a single JSON artifact at artifacts/techfi-daily/latest.json. Trigger when user asks to generate TechFiDaily / daily news content.
---

# TechFiDaily Generate

Only generates the daily content and writes one reusable artifact JSON. Does **not** publish to Telegram or write to Lark.

## Quick Start

```text
生成TechFiDaily
生成每日新闻
```

## Defaults (fixed by design)

- **Date scope**: yesterday in Beijing time (北京时间自然日 00:00–23:59), no date override.
- **Sections**: Tech / Finance / Geopolitics / Crypto.
- **Output size**: Top 5 items per section (热点资讯).
- **Sources**: English only; no exchange announcements; no blogs.
- **Output**: a single JSON file at `artifacts/techfi-daily/latest.json`.

## Workflow

Copy this checklist:

```text
Progress:
- [ ] Step 1: Determine content_date_bj (yesterday)
- [ ] Step 2: Fetch RSS feeds per section (English-only)
- [ ] Step 3: Normalize items (title/url/source/published_at)
- [ ] Step 4: Deduplicate & cluster similar stories
- [ ] Step 5: Score hotness and pick Top 5 per section
- [ ] Step 6: Generate Chinese plain-language explanations (fixed structure +点评)
- [ ] Step 7: Resolve optional image_url per item (RSS image -> og:image)
- [ ] Step 8: Build Telegram message payloads (5 messages, update-friendly)
- [ ] Step 9: Write artifacts/techfi-daily/latest.json
```

## Step 1: Determine target day (Beijing)

- `publish_date_bj`: today's date (Beijing).
- `content_date_bj`: yesterday's date (Beijing).

## Step 2: Fetch RSS sources

Use the curated list in `references/sources.md` (English, stable, news/official only).

Rules:
- Prefer RSS feeds that are stable and public (no login).
- If a feed is down, continue with partial results and record the error in the output JSON.

## Step 3: Normalize items

For each RSS entry, extract:
- `title_en` (raw title)
- `url` (canonical link)
- `source` (feed/source name)
- `published_at` (ISO string if possible; keep original if not)

## Step 4: Deduplicate & cluster

Goal: avoid repeating the same story across multiple outlets.

Minimum viable rules:
- Exact same `url` ⇒ same item.
- Highly similar titles ⇒ same cluster (see `references/scoring-and-dedup.md`).

Pick one “primary link” per cluster (highest score / most authoritative).

## Step 5: Score hotness and pick Top 5

Use a simple, stable scoring recipe (see `references/scoring-and-dedup.md`):
- Recency
- Source tier weight
- Keyword weight (e.g., sanctions / CPI / ETF / lawsuit / rate hike / hack)

Select Top 5 clusters per section.

## Step 6: Generate Chinese explanations (fixed structure)

For each selected item, generate Chinese content that is **easy to understand** and not hype:

Format (fixed):
- **发生了什么**：一句话讲清事实
- **为什么重要**：1–2句讲清影响（市场/政策/行业/风险）
- **点评**：1–2句观点/看法（基于标题与来源，不臆测新事实）
- **接下来关注什么**：一句话讲清可验证的后续

Keep it concise; avoid long paragraphs.

## Step 7: Resolve per-item image_url (optional)

Rules:
- Prefer RSS media fields (media:content / media:thumbnail / enclosure).
- If missing, fetch article page and read `og:image` / `twitter:image`.
- If still missing, leave `image_url` empty.

## Step 8: Build Telegram payloads (but do not send)

Generate 5 message payloads that `techfi-publish` can upsert:
- `main`: title + highlights + section list + counts
- `tech`, `finance`, `geo`, `crypto`: each contains exactly 5 items with Chinese explanation + source link

Important:
- Telegram single message length limit exists; keep each message compact and designed to be editable.
- Use HTML-safe formatting (links, line breaks) as needed.

## Step 9: Write one artifact JSON

Write exactly one file: `artifacts/techfi-daily/latest.json`.

Schema is defined in `references/json-output.md`.

## References

- `references/sources.md` - RSS sources per section (English only)
- `references/scoring-and-dedup.md` - dedup + hotness scoring rules
- `references/json-output.md` - the only output JSON schema
