# Telegram Upsert Rules (Channel)

## Pre-req

- Bot must be an admin in the channel.
- Messages must be originally sent by the bot to be editable.

## Message strategy (fixed 5)

Always maintain exactly 5 messages:

1) `main`
2) `tech`
3) `finance`
4) `geo`
5) `crypto`

## Upsert algorithm

- Load mapping from `tg_message_ids` if present.
- For each key in stable order:
  - If message_id exists: call `editMessageText`.
  - If missing or edit fails: call `sendMessage` and replace message_id for that key.
- Persist the refreshed mapping back to Bitable.

## Formatting

- Use `parse_mode=HTML`.
- Ensure content is HTML-safe (escape `<`, `>`, `&` unless used intentionally in tags).
- Keep each message short enough to avoid Telegram length limits; the generator should pre-format accordingly.

