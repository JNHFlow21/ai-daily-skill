# Lark Bitable: `Daily` (Single Table, MVP)

Goal: one-row-per-issue archive for your own review and recovery.

## Columns (English)

- `publish_date_bj` (text or date; e.g., `2026-01-16`)
- `content_date_bj` (text or date; e.g., `2026-01-15`) **unique key**
- `title` (text; optional)
- `highlights` (long text; optional)
- `tech_md` (long text; store Chinese explanations)
- `finance_md` (long text)
- `geo_md` (long text)
- `crypto_md` (long text)
- `tg_message_ids` (long text; JSON string mapping keys → Telegram message_id)
- `status` (single select: `success` / `partial` / `fail`)
- `error` (long text)

## Idempotency

Upsert by `content_date_bj`:
- If exists: update row, and edit Telegram messages using stored `tg_message_ids`.
- If not: create row, send Telegram messages, write `tg_message_ids` back.

