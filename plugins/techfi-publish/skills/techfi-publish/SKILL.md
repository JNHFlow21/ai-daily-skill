---
name: techfi-publish
description: Publishes TechFiDaily from a generated JSON artifact. Reads artifacts/techfi-daily/latest.json, upserts a single-row archive in Lark Bitable (Daily table, English columns), and upserts Telegram channel messages by editing the same 5 messages (main + 4 sections) using stored message IDs. Trigger when user asks to push/publish daily news to Telegram and record to Bitable.
---

# TechFiDaily Publish

Reads the generator artifact JSON and performs **publishing + archiving**:
- Update (edit) the same 5 Telegram channel messages each day.
- Upsert a daily archive row into Lark Bitable.

## Quick Start

```text
推送每日新闻
发布TechFiDaily
```

## Inputs

- Required artifact: `artifacts/techfi-daily/latest.json` (see generator schema).

## Required Secrets / Env

Telegram:
- `TG_BOT_TOKEN`
- `TG_CHAT_ID` (channel id, e.g. `-1003338913433`)

Lark (Bitable):
- `LARK_APP_ID`
- `LARK_APP_SECRET`
- `LARK_BITABLE_APP_TOKEN`
- `LARK_BITABLE_TABLE_ID`

## Workflow

```text
Progress:
- [ ] Step 1: Load and validate artifacts/techfi-daily/latest.json
- [ ] Step 2: Upsert Daily row into Lark Bitable (by content_date_bj)
- [ ] Step 3: Upsert Telegram 5 messages (edit if exists, else send)
- [ ] Step 4: Write back tg_message_ids to Bitable
- [ ] Step 5: Set status/error in Bitable
```

## Step 1: Load and validate artifact

Validation checks (minimum):
- `meta.publish_date_bj` and `meta.content_date_bj` exist.
- `telegram.messages` contains exactly 5 keys: `main`, `tech`, `finance`, `geo`, `crypto`.

## Step 2: Upsert Daily row into Bitable

Use the schema in `references/bitable-daily-schema.md`.

Upsert key:
- Use `content_date_bj` as the unique key for “this issue”.

Write fields:
- `publish_date_bj`, `content_date_bj`
- `tech_md`, `finance_md`, `geo_md`, `crypto_md` (store Chinese explanation text)
- `status`, `error`

## Step 3: Upsert Telegram 5 messages

Rules:
- If a `tg_message_ids` JSON exists in the Bitable row, prefer `editMessageText`.
- If not present (first run) or editing fails (message deleted), use `sendMessage` and refresh that message id.

Keep messages update-friendly:
- Use stable order: main → tech → finance → geo → crypto
- Use HTML parse mode

Details: `references/telegram-upsert.md`.

## Step 4: Persist message IDs

Store a JSON string in `tg_message_ids`, e.g.:

```json
{"main":123,"tech":124,"finance":125,"geo":126,"crypto":127}
```

## Step 5: Status & error handling

- Success: `status=success`, `error=""`
- Partial: at least one section missing but publish/archive succeeded ⇒ `status=partial`
- Fail: publish or archive failed ⇒ `status=fail` and record the reason

## References

- `references/bitable-daily-schema.md` - Daily single-table columns (English)
- `references/telegram-upsert.md` - Telegram edit/send rules and pitfalls
- `references/artifact-contract.md` - How latest.json maps to Telegram + Bitable
- `references/github-actions-ops.md` - Scheduling + required GitHub Secrets

