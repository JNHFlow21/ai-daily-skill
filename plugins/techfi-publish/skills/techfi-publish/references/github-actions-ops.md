# GitHub Actions Ops (MVP)

Goal: run daily at 08:00 Beijing time and upsert Telegram + Bitable.

## Schedule

GitHub Actions cron uses UTC.

- 08:00 Beijing time (UTC+8) = 00:00 UTC
- Cron: `0 0 * * *`

## Secrets (GitHub Repository → Settings → Secrets and variables → Actions)

Telegram:
- `TG_BOT_TOKEN`
- `TG_CHAT_ID` (e.g. `-1003338913433`)

Lark:
- `LARK_APP_ID`
- `LARK_APP_SECRET`
- `LARK_BITABLE_APP_TOKEN`
- `LARK_BITABLE_TABLE_ID`

## Recommended run order

1) Run `techfi-generate` to write `artifacts/techfi-daily/latest.json`
2) Run `techfi-publish` to publish + archive from that artifact

## Failure policy

- If generation fails: do not publish; record failure in logs.
- If publish partially fails: still upsert Bitable with `status=partial` and store the error.

