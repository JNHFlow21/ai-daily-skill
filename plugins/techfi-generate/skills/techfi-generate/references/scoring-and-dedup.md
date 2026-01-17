# Dedup + Hotness Scoring (MVP)

This is intentionally simple and stable. Prefer predictable behavior over “smart” behavior.

## Normalize

- Normalize title for comparisons: lowercase; trim spaces; remove punctuation; collapse whitespace.
- Always keep the original `title_en` unchanged for display/reference.

## Dedup / clustering

Apply in order:

1) **Same URL**: if `url` matches exactly ⇒ same item.
2) **Same canonical host+path**: strip tracking params (`utm_*`, `ref`, etc.) and compare.
3) **Title similarity** (MVP): if normalized titles are very close (e.g., one contains the other or high token overlap) ⇒ same cluster.

Pick cluster primary item:
- Prefer higher tier sources.
- Prefer more recent `published_at`.

## Source tiers (suggested)

- Tier A (official): SEC / CFTC / central banks / UN / IAEA / NASA / NIST / NSF / JPL
- Tier B (major/industry): Nature / IEEE / SpaceNews / Fierce Biotech / Mixed / Road to VR / sUAS
- Tier C (other industry/news): any remaining RSS sources

## Hotness score (simple)

Compute a stable score per cluster:

- `recency_score`: newer is higher.
- `source_score`: Tier A > Tier B > Tier C.
- `keyword_bonus`: add small bonuses for high-signal keywords.

### Keyword bonus examples

- Finance: CPI, jobs report, rate hike/cut, inflation, recession, bond yields
- Geo: sanctions, ceasefire, strike, election, blockade, treaty
- Crypto: ETF, SEC, CFTC, lawsuit, approval, ban, hack, exploit, stablecoin, regulation
- Tech: launches, acquisition, security breach, major model release

## Selection

- Select Top 5 clusters per section within the last 24 hours.
- If fewer than 5 clusters exist, return fewer and record `partial` status.
