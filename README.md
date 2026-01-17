# TechFiDaily

Daily news pipeline that generates AI + Web3 focused briefs from English sources and publishes to Telegram + Lark Bitable.

## Repo layout

- `plugins/techfi-generate/skills/techfi-generate/`: SOP for generation
- `plugins/techfi-publish/skills/techfi-publish/`: SOP for publishing
- `config/sources.yaml`: RSS sources (English only)
- `artifacts/techfi-daily/latest.json`: generator output (not committed)

## Environment

Copy `config/runtime.example.env` to `.env` and fill in secrets.

## Generate

```bash
python scripts/techfi_generate.py
```

Skip LLM (local smoke test):

```bash
python scripts/techfi_generate.py --no-llm
```

## Publish

```bash
python scripts/techfi_publish.py
```

## Default behavior

- Content window: rolling past 24 hours (Beijing time); `content_date_bj` is today
- Output: JSON only (`artifacts/techfi-daily/latest.json`)
- Sections (Top 5 each):
  - AI / 具身智能 / 生物科技 / 太空探索 / 无人机 / 空间计算
  - 金融 / 地缘政治 / 加密
- Telegram: main summary + butterfly insight + per-item messages (each item can include an image)
- Lark: single Daily table row per content date

## GitHub Secrets

Set these in repo secrets before enabling the workflow:

- `DEEPSEEK_API_KEY`
- `DEEPSEEK_MODEL` (optional, default `deepseek-chat`)
- `DEEPSEEK_API_BASE` (optional, default `https://api.deepseek.com`)
- `TG_BOT_TOKEN`
- `TG_CHAT_ID`
- `LARK_APP_ID`
- `LARK_APP_SECRET`
- `LARK_BITABLE_APP_TOKEN`
- `LARK_BITABLE_TABLE_ID`

## Notes

- LLM default: `deepseek-chat`
- Hacker News is used for hotness signal only (not final citations)
