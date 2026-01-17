# Output JSON Schema (Single Artifact)

The generator writes exactly one file: `artifacts/techfi-daily/latest.json`.

It must be sufficient for:
- Human reading (Chinese explanations)
- Downstream publishing (Telegram message payloads)
- Archiving (Lark Bitable fields)

## Required top-level fields

```json
{
  "meta": {
    "version": "1",
    "publish_date_bj": "YYYY-MM-DD",
    "content_date_bj": "YYYY-MM-DD",
    "window_hours": 24,
    "generated_at": "ISO-8601"
  },
  "highlights_zh": ["...", "..."],
  "butterfly_effect_zh": "...",
  "sections": {
    "tech_ai": { "items": [] },
    "tech_embodied": { "items": [] },
    "tech_biotech": { "items": [] },
    "tech_space": { "items": [] },
    "tech_spatial": { "items": [] },
    "finance": { "items": [] },
    "geo": { "items": [] },
    "crypto": { "items": [] }
  },
  "telegram": {
    "messages": [
      { "key": "main", "text_html": "..." },
      { "key": "butterfly", "text_html": "..." },
      { "key": "tech_ai", "text_html": "..." },
      { "key": "tech_embodied", "text_html": "..." },
      { "key": "tech_biotech", "text_html": "..." },
      { "key": "tech_space", "text_html": "..." },
      { "key": "tech_spatial", "text_html": "..." },
      { "key": "finance", "text_html": "..." },
      { "key": "geo", "text_html": "..." },
      { "key": "crypto", "text_html": "..." }
    ]
  },
  "debug": {
    "sources_used": [],
    "dedup_stats": {},
    "errors": []
  }
}
```

## Item shape (each section has up to 5 items from the last 24 hours)

```json
{
  "title_en": "English headline",
  "source": "BBC | CoinDesk | SEC | ...",
  "url": "https://...",
  "published_at": "ISO-8601 or original string",
  "image_url": "https://... (optional)",
  "explain_zh": {
    "what_happened": "发生了什么（一句话）",
    "why_it_matters": "为什么重要（1-2句）",
    "viewpoint": "点评（1-2句）",
    "what_to_watch": "接下来关注什么（一句话）"
  }
}
```

Notes:
- `telegram.messages[].text_html` should be ready for Telegram `parse_mode=HTML`.
- The publisher is responsible for send/edit; generator only constructs payload.
