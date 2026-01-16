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
    "generated_at": "ISO-8601"
  },
  "highlights_zh": ["...", "..."],
  "sections": {
    "tech": { "items": [] },
    "finance": { "items": [] },
    "geo": { "items": [] },
    "crypto": { "items": [] }
  },
  "telegram": {
    "messages": [
      { "key": "main", "text_html": "..." },
      { "key": "tech", "text_html": "..." },
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

## Item shape (each section has exactly 5 items when possible)

```json
{
  "title_en": "English headline",
  "source": "BBC | CoinDesk | SEC | ...",
  "url": "https://...",
  "published_at": "ISO-8601 or original string",
  "explain_zh": {
    "what_happened": "发生了什么（一句话）",
    "why_it_matters": "为什么重要（一句话）",
    "what_to_watch": "接下来关注什么（一句话）"
  }
}
```

Notes:
- `telegram.messages[].text_html` should be ready for Telegram `parse_mode=HTML`.
- The publisher is responsible for send/edit; generator only constructs payload.

