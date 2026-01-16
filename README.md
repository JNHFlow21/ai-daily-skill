# TechFiDaily

Daily news pipeline that generates Tech/Finance/Geopolitics/Crypto briefs from English sources and publishes to Telegram + Lark Bitable.

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

- Content date: yesterday (Beijing time)
- Output: JSON only (`artifacts/techfi-daily/latest.json`)
- Telegram: update the same 5 messages (main + 4 sections)
- Lark: single Daily table row per content date

## GitHub Secrets

Set these in repo secrets before enabling the workflow:

- `GEMINI_API_KEY`
- `GEMINI_API_BASE` (optional)
- `TG_BOT_TOKEN`
- `TG_CHAT_ID`
- `LARK_APP_ID`
- `LARK_APP_SECRET`
- `LARK_BITABLE_APP_TOKEN`
- `LARK_BITABLE_TABLE_ID`

## Notes

- Gemini model default: `gemini-3-flash-preview`
- Hacker News is used for hotness signal only (not final citations)
