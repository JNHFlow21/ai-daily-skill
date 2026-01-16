#!/usr/bin/env python3
import argparse
import datetime as dt
import html
import json
import os
import re
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

import feedparser
import requests
import yaml
from dateutil import parser as dateparser
from zoneinfo import ZoneInfo

USER_AGENT = "TechFiDailyBot/1.0 (+https://github.com/JNHFlow21/ai-daily-skill)"
TIMEOUT_SECS = 20
MAX_ITEMS_PER_SECTION = 5

INDEX_FEED_MAP = {
    "https://arstechnica.com/rss-feeds/": ["https://feeds.arstechnica.com/arstechnica/index"],
    "https://www.wired.com/about/rss-feeds/": ["https://www.wired.com/feed/rss"],
    "https://www.theregister.com/Design/page/feeds.html": ["https://www.theregister.com/headlines.atom"],
    "https://www.cnbc.com/rss-feeds/": ["https://www.cnbc.com/id/100003114/device/rss/rss.html"],
    "https://www.federalreserve.gov/feeds/feeds.htm": ["https://www.federalreserve.gov/feeds/press_all.xml"],
    "https://www.ecb.europa.eu/home/html/rss.ga.html": ["https://www.ecb.europa.eu/press/pr/rss/html/index.en.html"],
    "https://news.un.org/en": ["https://news.un.org/feed/subscribe/en/news/all/rss.xml"],
    "https://www.iaea.org/feeds": ["https://www.iaea.org/feeds/press-releases"],
    "https://cointelegraph.com/rss-feeds": ["https://cointelegraph.com/rss"],
    "https://www.sec.gov/newsroom/press-releases": ["https://www.sec.gov/news/pressreleases.rss"],
    "https://www.cftc.gov/RSS/index.htm": ["https://www.cftc.gov/RSS/PressReleases.xml"],
}

KEYWORDS_BY_SECTION = {
    "tech": [
        "launch", "released", "acquire", "acquisition", "breach", "security",
        "chip", "ai", "model", "ban", "lawsuit"
    ],
    "finance": [
        "cpi", "inflation", "rate hike", "rate cut", "jobs report", "recession",
        "bond", "yield", "fed", "ecb"
    ],
    "geo": [
        "sanction", "ceasefire", "strike", "election", "blockade", "treaty",
        "summit", "military"
    ],
    "crypto": [
        "etf", "sec", "cftc", "lawsuit", "approval", "ban", "hack",
        "exploit", "stablecoin", "regulation"
    ],
}

TIER_A = ["SEC", "CFTC", "Federal Reserve", "ECB", "UN", "IAEA"]
TIER_B = ["BBC", "Guardian", "Al Jazeera"]

TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
    "ref", "source", "spm", "fbclid", "gclid"
}


@dataclass
class Item:
    section: str
    title_en: str
    url: str
    source: str
    published_at: Optional[str]
    summary_en: Optional[str]
    is_hot_signal: bool = False


class GeminiClient:
    def __init__(self, api_key: str, model: str, api_base: Optional[str] = None) -> None:
        self.api_key = api_key
        self.model = model
        self.api_base = api_base or "https://generativelanguage.googleapis.com/v1beta"

    def generate_text(self, prompt: str, max_tokens: int = 512) -> str:
        url = f"{self.api_base}/models/{self.model}:generateContent"
        params = {"key": self.api_key}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": max_tokens,
            },
        }
        response = requests.post(
            url,
            params=params,
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload),
            timeout=TIMEOUT_SECS,
        )
        response.raise_for_status()
        data = response.json()
        candidates = data.get("candidates", [])
        if not candidates:
            raise RuntimeError("Gemini returned no candidates")
        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            raise RuntimeError("Gemini returned empty content")
        return parts[0].get("text", "").strip()


def load_env_file(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def load_sources(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_feed_urls(source: Dict[str, Any], errors: List[str]) -> List[str]:
    if source.get("resolved_urls"):
        return source["resolved_urls"]
    url = source.get("url")
    if source.get("type") == "rss":
        return [url]
    if source.get("type") == "index":
        mapped = INDEX_FEED_MAP.get(url)
        if not mapped:
            errors.append(f"No feed mapping for index: {url}")
            return []
        return mapped
    errors.append(f"Unknown source type: {source.get('type')} for {url}")
    return []


def fetch_feed(url: str) -> feedparser.FeedParserDict:
    headers = {"User-Agent": USER_AGENT}
    response = requests.get(url, headers=headers, timeout=TIMEOUT_SECS)
    response.raise_for_status()
    return feedparser.parse(response.content)


def parse_datetime(value: Optional[str], fallback_struct: Optional[Any]) -> Optional[dt.datetime]:
    if value:
        try:
            parsed = dateparser.parse(value)
            if parsed is None:
                return None
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt.timezone.utc)
            return parsed
        except (ValueError, TypeError):
            return None
    if fallback_struct:
        try:
            parsed = dt.datetime(*fallback_struct[:6], tzinfo=dt.timezone.utc)
            return parsed
        except Exception:
            return None
    return None


def normalize_title(title: str) -> str:
    lowered = title.lower()
    lowered = re.sub(r"[\W_]+", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered)
    return lowered.strip()


def canonicalize_url(url: str) -> str:
    try:
        parsed = urlparse(url)
    except Exception:
        return url
    query = [(k, v) for k, v in parse_qsl(parsed.query) if k not in TRACKING_PARAMS]
    new_query = urlencode(query, doseq=True)
    cleaned = parsed._replace(query=new_query, fragment="")
    return urlunparse(cleaned)


def title_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a in b or b in a:
        return 0.95
    a_set = set(a.split())
    b_set = set(b.split())
    if not a_set or not b_set:
        return 0.0
    jaccard = len(a_set & b_set) / len(a_set | b_set)
    return jaccard


def source_tier_score(source: str) -> float:
    for key in TIER_A:
        if key.lower() in source.lower():
            return 1.0
    for key in TIER_B:
        if key.lower() in source.lower():
            return 0.7
    return 0.4


def compute_recency_score(published_at: Optional[dt.datetime], now: dt.datetime) -> float:
    if not published_at:
        return 0.2
    delta = now - published_at
    hours = max(delta.total_seconds() / 3600.0, 0.0)
    score = 1.0 - min(hours / 72.0, 1.0)
    return max(score, 0.2)


def keyword_bonus(title: str, section: str) -> float:
    total = 0.0
    title_lower = title.lower()
    for keyword in KEYWORDS_BY_SECTION.get(section, []):
        if keyword in title_lower:
            total += 0.05
    return total


def is_same_cluster(item: Item, cluster_item: Item) -> bool:
    if canonicalize_url(item.url) == canonicalize_url(cluster_item.url):
        return True
    a = normalize_title(item.title_en)
    b = normalize_title(cluster_item.title_en)
    return title_similarity(a, b) >= 0.6


def choose_primary(items: List[Item]) -> Item:
    def sort_key(i: Item) -> Tuple[float, float]:
        tier = source_tier_score(i.source)
        published_dt = parse_datetime(i.published_at, None)
        ts = published_dt.timestamp() if published_dt else 0.0
        return (tier, ts)
    return sorted(items, key=sort_key, reverse=True)[0]


def extract_items_from_feed(section: str, source_name: str, feed: feedparser.FeedParserDict, is_hot_signal: bool) -> List[Item]:
    items = []
    for entry in feed.entries:
        title = entry.get("title", "").strip()
        url = entry.get("link", "").strip()
        if not title or not url:
            continue
        published_dt = parse_datetime(entry.get("published"), entry.get("published_parsed"))
        if not published_dt:
            published_dt = parse_datetime(entry.get("updated"), entry.get("updated_parsed"))
        published_at = published_dt.isoformat() if published_dt else None
        summary = entry.get("summary", None)
        items.append(
            Item(
                section=section,
                title_en=title,
                url=url,
                source=source_name,
                published_at=published_at,
                summary_en=summary,
                is_hot_signal=is_hot_signal,
            )
        )
    return items


def filter_by_date(items: List[Item], content_date_bj: str) -> List[Item]:
    tz_bj = ZoneInfo("Asia/Shanghai")
    results = []
    for item in items:
        if not item.published_at:
            results.append(item)
            continue
        try:
            published_dt = dateparser.parse(item.published_at)
        except Exception:
            results.append(item)
            continue
        if published_dt.tzinfo is None:
            published_dt = published_dt.replace(tzinfo=dt.timezone.utc)
        published_bj = published_dt.astimezone(tz_bj).date().isoformat()
        if published_bj == content_date_bj:
            results.append(item)
    return results


def build_clusters(items: List[Item]) -> List[List[Item]]:
    clusters: List[List[Item]] = []
    for item in items:
        placed = False
        for cluster in clusters:
            if is_same_cluster(item, cluster[0]):
                cluster.append(item)
                placed = True
                break
        if not placed:
            clusters.append([item])
    return clusters


def extract_hot_signal_titles(items: List[Item]) -> List[str]:
    titles = []
    for item in items:
        if item.is_hot_signal:
            titles.append(normalize_title(item.title_en))
    return titles


def hn_bonus_for_title(title: str, hot_titles: List[str]) -> float:
    if not hot_titles:
        return 0.0
    normalized = normalize_title(title)
    for hot in hot_titles:
        if title_similarity(normalized, hot) >= 0.6:
            return 0.15
    return 0.0


def generate_explain(client: Optional[GeminiClient], item: Item) -> Dict[str, str]:
    if client is None:
        return {
            "what_happened": f"新闻要点：{item.title_en}",
            "why_it_matters": "重要性：待补充",
            "what_to_watch": "关注点：待补充",
        }
    prompt = (
        "Summarize the following English news headline into Chinese with plain language. "
        "Return strict JSON with keys: what_happened, why_it_matters, what_to_watch. "
        "Each value must be one sentence, no hype, no emojis, <= 30 Chinese characters. "
        f"Headline: {item.title_en}\n"
        f"Source: {item.source}\n"
    )
    if item.summary_en:
        prompt += f"Summary: {item.summary_en}\n"
    raw = client.generate_text(prompt, max_tokens=256)
    parsed = safe_json_from_text(raw)
    if parsed:
        return parsed
    return {
        "what_happened": f"新闻要点：{item.title_en}",
        "why_it_matters": "重要性：待补充",
        "what_to_watch": "关注点：待补充",
    }


def generate_highlights(client: Optional[GeminiClient], items: List[Dict[str, Any]]) -> List[str]:
    if client is None:
        return ["要点待生成（LLM未启用）"]
    lines = []
    for item in items:
        lines.append(f"[{item['section']}] {item['title_en']}")
    prompt = (
        "Create 3-5 concise Chinese highlights for a daily news brief. "
        "Return strict JSON array of strings. Each item <= 30 Chinese characters. "
        "Input headlines:\n" + "\n".join(lines)
    )
    raw = client.generate_text(prompt, max_tokens=256)
    parsed = safe_json_from_text(raw)
    if isinstance(parsed, list):
        return [str(x) for x in parsed][:5]
    return ["要点待生成"]


def safe_json_from_text(text: str) -> Optional[Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return None


def build_telegram_messages(
    content_date_bj: str,
    highlights_zh: List[str],
    sections: Dict[str, Dict[str, Any]],
) -> List[Dict[str, str]]:
    messages = []

    main_lines = [f"<b>TechFiDaily</b> · {content_date_bj}"]
    main_lines.append("\n<b>今日要点</b>")
    for idx, highlight in enumerate(highlights_zh, start=1):
        main_lines.append(f"{idx}. {html.escape(highlight)}")
    main_lines.append("\n<b>板块数量</b>")
    section_names = {
        "tech": "科技",
        "finance": "金融",
        "geo": "地缘政治",
        "crypto": "加密",
    }
    for key in ["tech", "finance", "geo", "crypto"]:
        count = len(sections[key]["items"])
        main_lines.append(f"- {section_names[key]}: {count}")
    messages.append({"key": "main", "text_html": "\n".join(main_lines)})

    for key, title in [("tech", "科技"), ("finance", "金融"), ("geo", "地缘政治"), ("crypto", "加密")]:
        lines = [f"<b>{title}</b> · {content_date_bj}"]
        for idx, item in enumerate(sections[key]["items"], start=1):
            explain = item["explain_zh"]
            lines.append("")
            lines.append(f"{idx}) {html.escape(explain['what_happened'])}")
            lines.append(f"重要性：{html.escape(explain['why_it_matters'])}")
            lines.append(f"关注：{html.escape(explain['what_to_watch'])}")
            lines.append(f"来源：<a href=\"{html.escape(item['url'])}\">{html.escape(item['source'])}</a>")
        messages.append({"key": key, "text_html": "\n".join(lines)})
    return messages


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate TechFiDaily JSON artifact")
    parser.add_argument("--sources", default="config/sources.yaml")
    parser.add_argument("--out", default="artifacts/techfi-daily/latest.json")
    parser.add_argument("--no-llm", action="store_true")
    args = parser.parse_args()

    load_env_file()

    tz_bj = ZoneInfo("Asia/Shanghai")
    now_bj = dt.datetime.now(tz_bj)
    publish_date_bj = now_bj.date().isoformat()
    content_date_bj = (now_bj.date() - dt.timedelta(days=1)).isoformat()

    config = load_sources(args.sources)
    sections_config = config.get("sections", {})

    all_items: Dict[str, List[Item]] = {"tech": [], "finance": [], "geo": [], "crypto": []}
    errors: List[str] = []
    sources_used: List[Dict[str, Any]] = []

    for section, section_cfg in sections_config.items():
        for source in section_cfg.get("primary_sources", []):
            feed_urls = resolve_feed_urls(source, errors)
            for feed_url in feed_urls:
                try:
                    feed = fetch_feed(feed_url)
                    items = extract_items_from_feed(section, source["name"], feed, False)
                    all_items[section].extend(items)
                    sources_used.append({"section": section, "source": source["name"], "url": feed_url, "count": len(items)})
                except Exception as exc:
                    errors.append(f"{section}:{source['name']}::{feed_url}::{exc}")
        for source in section_cfg.get("hot_signal_sources", []):
            feed_urls = resolve_feed_urls(source, errors)
            for feed_url in feed_urls:
                try:
                    feed = fetch_feed(feed_url)
                    items = extract_items_from_feed(section, source["name"], feed, True)
                    all_items[section].extend(items)
                    sources_used.append({"section": section, "source": source["name"], "url": feed_url, "count": len(items), "hot_signal": True})
                except Exception as exc:
                    errors.append(f"{section}:{source['name']}::{feed_url}::{exc}")

    client = None
    if not args.no_llm:
        api_key = os.getenv("GEMINI_API_KEY")
        model = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")
        api_base = os.getenv("GEMINI_API_BASE")
        if not api_key:
            errors.append("GEMINI_API_KEY is missing; falling back to no-llm mode")
        else:
            client = GeminiClient(api_key=api_key, model=model, api_base=api_base)

    sections_output: Dict[str, Dict[str, Any]] = {}
    dedup_stats: Dict[str, Any] = {}
    selected_for_highlights: List[Dict[str, Any]] = []

    for section, items in all_items.items():
        filtered = filter_by_date(items, content_date_bj)
        hot_titles = extract_hot_signal_titles(filtered)
        primary_items = [i for i in filtered if not i.is_hot_signal]
        clusters = build_clusters(primary_items)

        scored: List[Tuple[float, Item, List[Item]]] = []
        now_dt = dt.datetime.now(tz_bj)
        for cluster in clusters:
            primary = choose_primary(cluster)
            published_dt = parse_datetime(primary.published_at, None)
            recency = compute_recency_score(published_dt, now_dt) if published_dt else 0.2
            source_score = source_tier_score(primary.source)
            bonus = keyword_bonus(primary.title_en, section)
            hn_bonus = hn_bonus_for_title(primary.title_en, hot_titles)
            score = recency + source_score + bonus + hn_bonus
            scored.append((score, primary, cluster))

        scored.sort(key=lambda x: x[0], reverse=True)
        top_clusters = scored[:MAX_ITEMS_PER_SECTION]
        section_items = []
        for score, primary, cluster in top_clusters:
            explain = generate_explain(client, primary)
            section_items.append({
                "title_en": primary.title_en,
                "source": primary.source,
                "url": primary.url,
                "published_at": primary.published_at,
                "explain_zh": explain,
            })
            selected_for_highlights.append({
                "section": section,
                "title_en": primary.title_en,
            })

        sections_output[section] = {"items": section_items}
        dedup_stats[section] = {
            "raw_count": len(items),
            "filtered_count": len(filtered),
            "cluster_count": len(clusters),
            "selected": len(section_items),
        }

    highlights_zh = generate_highlights(client, selected_for_highlights)
    telegram_messages = build_telegram_messages(content_date_bj, highlights_zh, sections_output)

    output = {
        "meta": {
            "version": "1",
            "publish_date_bj": publish_date_bj,
            "content_date_bj": content_date_bj,
            "generated_at": dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc).isoformat(),
        },
        "highlights_zh": highlights_zh,
        "sections": sections_output,
        "telegram": {
            "messages": telegram_messages,
        },
        "debug": {
            "sources_used": sources_used,
            "dedup_stats": dedup_stats,
            "errors": errors,
        },
    }

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Wrote {args.out}")
    if errors:
        print("Errors:")
        for err in errors:
            print(f"- {err}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
