---
name: techfi-generate
description: Generates TechFiDaily content only (no publishing). Fetches English hot news via stable RSS sources across 8 sections (Tech-AI, Tech-Embodied, Tech-Biotech, Tech-Space, Tech-Spatial, Finance, Geopolitics, Crypto), dedupes and selects Top 5 per section, then uses DeepSeek LLM to produce easy-to-read Chinese explanations +点评 and optional image_url. Also generates a cross-section butterfly-effect insight. Outputs a single JSON artifact at artifacts/techfi-daily/latest.json. Trigger when user asks to generate TechFiDaily / daily news content.
---

# TechFiDaily Generate

Only generates the daily content and writes one reusable artifact JSON. Does **not** publish to Telegram or write to Lark.

## Quick Start

```text
生成TechFiDaily
生成每日新闻
```

## Defaults (fixed by design)

- **Date scope**: rolling 24 hours from generation time (北京时间), no date override.
- **Sections**: Tech-AI / Tech-Embodied / Tech-Biotech / Tech-Space / Tech-Spatial / Finance / Geopolitics / Crypto.
- **Output size**: Top 5 items per section (热点资讯, 7-day backfill when needed).
- **Sources**: English only; no exchange announcements; no blogs.
- **Output**: a single JSON file at `artifacts/techfi-daily/latest.json`.

## Workflow

Copy this checklist:

```text
Progress:
- [ ] Step 1: Determine time window (last 24 hours, Beijing time)
- [ ] Step 2: Fetch RSS feeds per section (English-only)
- [ ] Step 3: Normalize items (title/url/source/published_at)
- [ ] Step 4: Deduplicate & cluster similar stories
- [ ] Step 5: Score hotness and pick Top 5 per section
- [ ] Step 6: Generate Chinese plain-language explanations (fixed structure +点评)
- [ ] Step 7: Generate cross-section butterfly-effect insight
- [ ] Step 8: Resolve optional image_url per item (RSS image -> og:image)
- [ ] Step 9: Build Telegram message payloads (update-friendly)
- [ ] Step 10: Write artifacts/techfi-daily/latest.json
```

## Step 1: Determine time window (Beijing)

- `publish_date_bj`: today's date (Beijing).
- `content_date_bj`: today's date (Beijing, label only).
- Window: last 24 hours from generation time.

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

Goal: avoid repeating the same story across multiple outlets and sections.

Minimum viable rules:
- Exact same `url` ⇒ same item.
- Highly similar titles ⇒ same cluster (see `references/scoring-and-dedup.md`).

Pick one “primary link” per cluster (highest score / most authoritative).

Cross-section rule:
- If the same story appears in multiple sections, keep it only in the first section
  (order: Tech-AI → Tech-Embodied → Tech-Biotech → Tech-Space → Tech-Spatial → Finance → Geopolitics → Crypto).

## Step 5: Score hotness and pick Top 5

Use a simple, stable scoring recipe (see `references/scoring-and-dedup.md`):
- Recency
- Source tier weight
- Keyword weight (e.g., sanctions / CPI / ETF / lawsuit / rate hike / hack)

Select Top 5 clusters per section within the last 24 hours.
If fewer than 5 clusters exist, return fewer and record `partial` status.

## Step 6: Generate Chinese explanations (fixed structure)

For each selected item, generate Chinese content that is **easy to understand** and not hype:

Format (fixed):
- **发生了什么**：一句话讲清事实
- **为什么重要**：1–2句讲清影响（市场/政策/行业/风险）
- **点评**：1–2句观点/看法（基于标题与来源，不臆测新事实）
- **接下来关注什么**：一句话讲清可验证的后续

Keep it concise; avoid long paragraphs.
If the batch output is malformed, item count mismatches, or the section only has 1 item, fall back to per-item LLM calls.

## Step 7: Generate cross-section butterfly-effect insight

- Use all selected headlines across sections.
- Output 2-3 concise Chinese sentences that link at least two sections and
  describe a plausible asset transmission path.

## Step 8: Resolve per-item image_url (optional)

Rules:
- Prefer RSS media fields (media:content / media:thumbnail / enclosure).
- If missing, fetch article page and read `og:image` / `twitter:image`.
- If still missing, leave `image_url` empty.

## Step 9: Build Telegram payloads (but do not send)

Generate message payloads that `techfi-publish` can upsert:
- `main`: title + highlights + section list + counts
- `butterfly`: cross-section butterfly-effect insight
- `tech_ai`, `tech_embodied`, `tech_biotech`, `tech_space`, `tech_spatial`, `finance`, `geo`, `crypto`
  each contains up to 5 items with Chinese explanation + source link

Important:
- Telegram single message length limit exists; keep each message compact and designed to be editable.
- Use HTML-safe formatting (links, line breaks) as needed.

## Step 10: Write one artifact JSON

Write exactly one file: `artifacts/techfi-daily/latest.json`.

Schema is defined in `references/json-output.md`.

## References

- `references/sources.md` - RSS sources per section (English only)
- `references/scoring-and-dedup.md` - dedup + hotness scoring rules
- `references/json-output.md` - the only output JSON schema
