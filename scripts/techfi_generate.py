#!/usr/bin/env python3
import argparse
import datetime as dt
import html
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urljoin, urlparse, urlunparse, parse_qsl, urlencode

import feedparser
import requests
import yaml
from dateutil import parser as dateparser
from zoneinfo import ZoneInfo

USER_AGENT = "TechFiDailyBot/1.0 (+https://github.com/JNHFlow21/ai-daily-skill)"
TIMEOUT_SECS = 20
MAX_ITEMS_PER_SECTION = 5
WINDOW_HOURS = 24
SECTION_ALIASES = {"geopolitics": "geo"}

SECTION_ORDER = [
    "tech_ai",
    "tech_embodied",
    "tech_biotech",
    "tech_space",
    "tech_spatial",
    "finance",
    "geo",
    "crypto",
]

INDEX_FEED_MAP = {
    "https://arstechnica.com/rss-feeds/": ["https://feeds.arstechnica.com/arstechnica/index"],
    "https://www.wired.com/about/rss-feeds/": ["https://www.wired.com/feed/rss"],
    "https://www.theregister.com/Design/page/feeds.html": ["https://www.theregister.com/headlines.atom"],
    "https://www.cnbc.com/rss-feeds/": ["https://www.cnbc.com/id/100003114/device/rss/rss.html"],
    "https://www.federalreserve.gov/feeds/feeds.htm": ["https://www.federalreserve.gov/feeds/press_all.xml"],
    "https://www.ecb.europa.eu/home/html/rss.ga.html": ["https://www.ecb.europa.eu/rss/press.html"],
    "https://news.un.org/en": ["https://news.un.org/feed/subscribe/en/news/all/rss.xml"],
    "https://www.iaea.org/feeds": ["https://www.iaea.org/feeds/topnews"],
    "https://cointelegraph.com/rss-feeds": ["https://cointelegraph.com/rss"],
    "https://www.sec.gov/newsroom/press-releases": ["https://www.sec.gov/news/pressreleases.rss"],
    "https://www.cftc.gov/RSS/index.htm": ["https://www.cftc.gov/RSS/RSSGP/rssgp.xml"],
}

KEYWORDS_BY_SECTION = {
    "tech_ai": [
        "ai", "model", "chip", "gpu", "compute", "regulation", "policy",
        "benchmark", "alignment", "inference", "training"
    ],
    "tech_embodied": [
        "robot", "robotics", "autonomous", "drone", "uav", "sensor",
        "manufacturing", "automation"
    ],
    "tech_biotech": [
        "biotech", "gene", "genetic", "clinical", "trial", "therapy",
        "drug", "pharma", "crispr"
    ],
    "tech_space": [
        "launch", "rocket", "satellite", "orbit", "mission", "nasa",
        "space", "aerospace", "drone", "uav"
    ],
    "tech_spatial": [
        "vr", "ar", "xr", "spatial", "headset", "mixed reality", "vision",
        "display"
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

TIER_A = [
    "SEC", "CFTC", "Federal Reserve", "ECB", "BIS", "EIA", "FSB",
    "UN", "IAEA", "NASA", "JPL", "NIST", "NSF", "OpenAI", "State Department"
]
TIER_B = [
    "BBC", "Guardian", "Al Jazeera", "Nature", "IEEE", "SpaceNews",
    "Mixed", "Road to VR", "smol", "SIPRI", "RUSI", "CSIS", "CFR",
    "TechCrunch", "STAT", "BioPharma Dive",
    "Robot Report", "Robotics Business Review", "UploadVR", "Space.com",
    "Foreign Policy", "News-Medical"
]

TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
    "ref", "source", "spm", "fbclid", "gclid"
}

TZINFOS = {
    "UTC": 0,
    "GMT": 0,
    "UT": 0,
    "EST": -5 * 3600,
    "EDT": -4 * 3600,
    "CST": -6 * 3600,
    "CDT": -5 * 3600,
    "MST": -7 * 3600,
    "MDT": -6 * 3600,
    "PST": -8 * 3600,
    "PDT": -7 * 3600,
    "CET": 1 * 3600,
    "CEST": 2 * 3600,
    "BST": 1 * 3600,
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
    image_url: Optional[str] = None


class GeminiClient:
    def __init__(self, api_key: str, model: str, api_base: Optional[str] = None) -> None:
        self.api_key = api_key
        self.model = model
        self.api_base = api_base or "https://generativelanguage.googleapis.com/v1beta"

    def generate_text(
        self,
        prompt: str,
        max_tokens: int = 512,
        response_mime_type: Optional[str] = None,
        response_schema: Optional[Dict[str, Any]] = None,
    ) -> str:
        url = f"{self.api_base}/models/{self.model}:generateContent"
        params = {"key": self.api_key}
        generation_config: Dict[str, Any] = {
            "temperature": 0.2,
            "maxOutputTokens": max_tokens,
        }
        if response_mime_type:
            generation_config["responseMimeType"] = response_mime_type
        if response_schema:
            generation_config["responseSchema"] = response_schema
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": generation_config,
        }
        last_error: Optional[Exception] = None
        for attempt in range(5):
            try:
                response = requests.post(
                    url,
                    params=params,
                    headers={"Content-Type": "application/json"},
                    data=json.dumps(payload),
                    timeout=TIMEOUT_SECS,
                )
                if response.status_code in (429, 500, 503):
                    raise requests.HTTPError(
                        f"Gemini status {response.status_code}", response=response
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
            except requests.HTTPError as exc:
                last_error = exc
                if getattr(exc.response, "status_code", None) in (429, 500, 503):
                    retry_after = None
                    if exc.response is not None:
                        retry_after = exc.response.headers.get("Retry-After")
                    if retry_after and retry_after.isdigit():
                        time.sleep(int(retry_after))
                    else:
                        time.sleep(min(2 ** attempt, 10))
                    continue
                raise
            except Exception as exc:
                last_error = exc
                time.sleep(min(2 ** attempt, 10))
        if last_error:
            raise RuntimeError(f"Gemini failed after retries: {last_error}") from last_error
        raise RuntimeError("Gemini failed without error")


class DeepSeekClient:
    def __init__(self, api_key: str, model: str, api_base: Optional[str] = None) -> None:
        self.api_key = api_key
        self.model = model
        self.api_base = api_base or "https://api.deepseek.com"

    def generate_text(
        self,
        prompt: str,
        max_tokens: int = 512,
        response_mime_type: Optional[str] = None,
        response_schema: Optional[Dict[str, Any]] = None,
    ) -> str:
        url = f"{self.api_base}/chat/completions"
        messages = []
        if response_mime_type == "application/json":
            messages.append(
                {
                    "role": "system",
                    "content": "Return only valid JSON. Do not include markdown or extra text.",
                }
            )
        messages.append({"role": "user", "content": prompt})
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": max_tokens,
        }
        last_error: Optional[Exception] = None
        for attempt in range(5):
            try:
                response = requests.post(
                    url,
                    headers=headers,
                    data=json.dumps(payload),
                    timeout=TIMEOUT_SECS,
                )
                if response.status_code in (429, 500, 503):
                    raise requests.HTTPError(
                        f"DeepSeek status {response.status_code}", response=response
                    )
                response.raise_for_status()
                data = response.json()
                choices = data.get("choices", [])
                if not choices:
                    raise RuntimeError("DeepSeek returned no choices")
                content = choices[0].get("message", {}).get("content", "")
                if not content:
                    raise RuntimeError("DeepSeek returned empty content")
                return str(content).strip()
            except requests.HTTPError as exc:
                last_error = exc
                if getattr(exc.response, "status_code", None) in (429, 500, 503):
                    retry_after = None
                    if exc.response is not None:
                        retry_after = exc.response.headers.get("Retry-After")
                    if retry_after and retry_after.isdigit():
                        time.sleep(int(retry_after))
                    else:
                        time.sleep(min(2 ** attempt, 10))
                    continue
                raise
            except Exception as exc:
                last_error = exc
                time.sleep(min(2 ** attempt, 10))
        if last_error:
            raise RuntimeError(f"DeepSeek failed after retries: {last_error}") from last_error
        raise RuntimeError("DeepSeek failed without error")


LLMClient = Union[GeminiClient, DeepSeekClient]


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
            parsed = dateparser.parse(value, tzinfos=TZINFOS)
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
        image_url = extract_image_from_entry(entry)
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
                image_url=image_url,
            )
        )
    return items


def extract_image_from_entry(entry: Any) -> Optional[str]:
    candidates: List[str] = []
    for media in entry.get("media_content", []) or []:
        if isinstance(media, dict) and media.get("url"):
            candidates.append(media["url"])
    for media in entry.get("media_thumbnail", []) or []:
        if isinstance(media, dict) and media.get("url"):
            candidates.append(media["url"])
    image = entry.get("image")
    if isinstance(image, dict) and image.get("href"):
        candidates.append(image["href"])
    for link in entry.get("links", []) or []:
        if not isinstance(link, dict):
            continue
        if link.get("rel") == "enclosure" and str(link.get("type", "")).startswith("image/"):
            if link.get("href"):
                candidates.append(link["href"])
    for url in candidates:
        if url and url.startswith(("http://", "https://")):
            return url
    return None


def fetch_og_image(url: str) -> Optional[str]:
    if not url:
        return None
    headers = {"User-Agent": USER_AGENT}
    try:
        response = requests.get(url, headers=headers, timeout=TIMEOUT_SECS)
        response.raise_for_status()
    except Exception:
        return None
    text = response.text
    patterns = [
        r'<meta[^>]+property=["\']og:image["\'][^>]*content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*property=["\']og:image["\']',
        r'<meta[^>]+name=["\']twitter:image["\'][^>]*content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*name=["\']twitter:image["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            image_url = match.group(1).strip()
            if image_url.startswith(("http://", "https://")):
                return image_url
            return urljoin(url, image_url)
    return None


def resolve_image_url(item: Item) -> Optional[str]:
    if item.image_url:
        return item.image_url
    return fetch_og_image(item.url)


def filter_by_date(items: List[Item], now_dt: dt.datetime) -> List[Item]:
    tz_bj = ZoneInfo("Asia/Shanghai")
    window_start = now_dt - dt.timedelta(hours=WINDOW_HOURS)
    results: List[Item] = []
    for item in items:
        if not item.published_at:
            continue
        published_dt = parse_datetime(item.published_at, None)
        if not published_dt:
            continue
        published_bj = published_dt.astimezone(tz_bj)
        if window_start <= published_bj <= now_dt:
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


def is_duplicate_global(item: Item, selected: List[Item]) -> bool:
    for existing in selected:
        if is_same_cluster(item, existing):
            return True
    return False


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


def fallback_explain(item: Item) -> Dict[str, str]:
    return {
        "what_happened": f"新闻要点：{item.title_en}",
        "why_it_matters": "重要性：待补充",
        "viewpoint": "点评：待补充",
        "what_to_watch": "关注点：待补充",
    }


def generate_explain(client: Optional[LLMClient], item: Item) -> Dict[str, str]:
    if client is None:
        return fallback_explain(item)
    prompt = (
        "Summarize the following English news headline into Chinese with plain language. "
        "Return strict JSON with keys: what_happened, why_it_matters, viewpoint, what_to_watch. "
        "Each value must be 1-2 sentences, <= 60 Chinese characters, no hype, no emojis. "
        "Viewpoint should be a brief analyst-style comment based only on the headline and source. "
        f"Headline: {item.title_en}\n"
        f"Source: {item.source}\n"
    )
    if item.summary_en:
        prompt += f"Summary: {item.summary_en}\n"
    raw = client.generate_text(
        prompt,
        max_tokens=256,
        response_mime_type="application/json",
        response_schema={
            "type": "object",
            "properties": {
                "what_happened": {"type": "string"},
                "why_it_matters": {"type": "string"},
                "viewpoint": {"type": "string"},
                "what_to_watch": {"type": "string"},
            },
            "required": ["what_happened", "why_it_matters", "viewpoint", "what_to_watch"],
        },
    )
    parsed = safe_json_from_text(raw)
    if parsed:
        return parsed
    return fallback_explain(item)


def fallback_highlights(reason: str) -> List[str]:
    return [f"要点待生成（{reason}）"]


def generate_explain_batch(client: LLMClient, items: List[Item]) -> List[Dict[str, str]]:
    explain_keys = {"what_happened", "why_it_matters", "viewpoint", "what_to_watch"}

    def is_explain_obj(value: Any) -> bool:
        return isinstance(value, dict) and explain_keys.issubset(value.keys())

    def coerce_explain_list(value: Any) -> Optional[List[Dict[str, str]]]:
        if isinstance(value, list):
            return value  # caller will normalize
        if isinstance(value, dict):
            items_value = value.get("items")
            if isinstance(items_value, list):
                return items_value
            if is_explain_obj(items_value):
                return [items_value]
            if is_explain_obj(value):
                return [value]
            if all(is_explain_obj(v) for v in value.values()):
                return list(value.values())
        return None

    if len(items) == 1:
        return [generate_explain(client, items[0])]

    lines = []
    for idx, item in enumerate(items, start=1):
        line = f"{idx}. {item.title_en} (Source: {item.source})"
        if item.summary_en:
            line += f" | Summary: {item.summary_en}"
        lines.append(line)
    is_deepseek = isinstance(client, DeepSeekClient)
    if is_deepseek:
        prompt = (
            "You are given English news headlines. Return a JSON object with key items (array) "
            "with the same length and order. Each element must be an object with keys: "
            "what_happened, why_it_matters, viewpoint, what_to_watch. Each value must be 1-2 "
            "sentences, <= 60 Chinese characters, no hype, no emojis. "
            "Viewpoint should be a brief analyst-style comment based only on the headline and source. "
            "Always return items as an array even if there is only one input. "
            "Input:\n" + "\n".join(lines)
        )
    else:
        prompt = (
            "You are given English news headlines. Return a JSON array with the same length and order. "
            "Each element must be an object with keys: what_happened, why_it_matters, viewpoint, what_to_watch. "
            "Each value must be 1-2 sentences, <= 60 Chinese characters, no hype, no emojis. "
            "Viewpoint should be a brief analyst-style comment based only on the headline and source. "
            "Input:\n" + "\n".join(lines)
        )
    schema = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "what_happened": {"type": "string"},
                "why_it_matters": {"type": "string"},
                "viewpoint": {"type": "string"},
                "what_to_watch": {"type": "string"},
            },
            "required": ["what_happened", "why_it_matters", "viewpoint", "what_to_watch"],
        },
    }
    raw = client.generate_text(
        prompt,
        max_tokens=512,
        response_mime_type="application/json",
        response_schema=schema,
    )
    parsed_list = coerce_explain_list(safe_json_from_text(raw))
    if not isinstance(parsed_list, list):
        raise RuntimeError("LLM batch output is not a list")
    normalized: List[Dict[str, str]] = []
    for idx in range(len(items)):
        value = parsed_list[idx] if idx < len(parsed_list) else None
        if is_explain_obj(value):
            normalized.append(value)
        else:
            normalized.append(generate_explain(client, items[idx]))
    return normalized


def generate_highlights(client: Optional[LLMClient], items: List[Dict[str, Any]]) -> List[str]:
    if client is None:
        return fallback_highlights("LLM未启用")
    lines = []
    for item in items:
        lines.append(f"[{item['section']}] {item['title_en']}")
    is_deepseek = isinstance(client, DeepSeekClient)
    if is_deepseek:
        prompt = (
            "Create 3-5 concise Chinese highlights for a daily news brief. "
            "Return a JSON object with key highlights (array of strings). "
            "Each item <= 30 Chinese characters. "
            "Input headlines:\n" + "\n".join(lines)
        )
    else:
        prompt = (
            "Create 3-5 concise Chinese highlights for a daily news brief. "
            "Return strict JSON array of strings. Each item <= 30 Chinese characters. "
            "Input headlines:\n" + "\n".join(lines)
        )
    schema = {"type": "array", "items": {"type": "string"}}
    raw = client.generate_text(
        prompt,
        max_tokens=256,
        response_mime_type="application/json",
        response_schema=schema,
    )
    parsed = safe_json_from_text(raw)
    if isinstance(parsed, dict) and isinstance(parsed.get("items"), list):
        parsed = parsed["items"]
    if isinstance(parsed, dict) and isinstance(parsed.get("highlights"), list):
        parsed = parsed["highlights"]
    if isinstance(parsed, list):
        return [str(x) for x in parsed][:5]
    return fallback_highlights("LLM输出异常")


def fallback_butterfly_effect(reason: str) -> str:
    return f"跨板块联动待生成（{reason}）"


def generate_butterfly_effect(client: Optional[LLMClient], items: List[Dict[str, Any]]) -> str:
    if client is None:
        return fallback_butterfly_effect("LLM未启用")
    lines = []
    for item in items:
        lines.append(f"[{item['section']}] {item['title_en']}")
    is_deepseek = isinstance(client, DeepSeekClient)
    if is_deepseek:
        prompt = (
            "Role: 全球跨资产首席分析师（AI + Web3背景）。基于标题生成跨板块蝴蝶效应分析，要求：\n"
            "1) 至少关联两个板块；\n"
            "2) 明确资产传导链路（美股/大宗商品/贵金属/加密里至少提到两类）；\n"
            "3) 标注信号还是噪音；\n"
            "4) 给出生活化类比；\n"
            "5) 2-4句中文，每句<=80字，不臆测新事实。\n"
            "Return JSON object with key butterfly_effect.\n"
            "Input headlines:\n" + "\n".join(lines)
        )
    else:
        prompt = (
            "Create a Chinese cross-section butterfly-effect insight. Link at least two sections, "
            "mention a plausible asset transmission path (US equities/commodities/precious metals/crypto), "
            "label signal vs noise, and include a life analogy. 2-4 sentences, <=80 chars each. "
            "Return JSON object with key butterfly_effect.\n"
            "Input headlines:\n" + "\n".join(lines)
        )
    raw = client.generate_text(
        prompt,
        max_tokens=256,
        response_mime_type="application/json",
        response_schema={
            "type": "object",
            "properties": {"butterfly_effect": {"type": "string"}},
            "required": ["butterfly_effect"],
        },
    )
    parsed = safe_json_from_text(raw)
    if isinstance(parsed, dict) and isinstance(parsed.get("butterfly_effect"), str):
        return parsed["butterfly_effect"]
    return fallback_butterfly_effect("LLM输出异常")


def safe_json_from_text(text: str) -> Optional[Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\\s*|\\s*```$", "", text, flags=re.IGNORECASE | re.DOTALL).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    def try_parse_substring(start: int, opening: str, closing: str) -> Optional[Any]:
        depth = 0
        for idx in range(start, len(text)):
            ch = text[idx]
            if ch == opening:
                depth += 1
            elif ch == closing:
                depth -= 1
                if depth == 0:
                    snippet = text[start : idx + 1]
                    try:
                        return json.loads(snippet)
                    except json.JSONDecodeError:
                        return None
        return None

    for idx, ch in enumerate(text):
        if ch == "{":
            parsed = try_parse_substring(idx, "{", "}")
            if parsed is not None:
                return parsed
        elif ch == "[":
            parsed = try_parse_substring(idx, "[", "]")
            if parsed is not None:
                return parsed

    match = re.search(r"\{.*?\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    match = re.search(r"\[.*?\]", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return None


def build_telegram_messages(
    content_date_bj: str,
    highlights_zh: List[str],
    sections: Dict[str, Dict[str, Any]],
    butterfly_effect: Optional[str],
) -> List[Dict[str, str]]:
    messages = []

    main_lines = [f"<b>TechFiDaily</b> · {content_date_bj}"]
    main_lines.append("统计口径：过去24小时")
    main_lines.append("\n<b>今日要点</b>")
    for idx, highlight in enumerate(highlights_zh, start=1):
        main_lines.append(f"{idx}. {html.escape(highlight)}")
    main_lines.append("\n<b>板块数量</b>")
    section_names = {
        "tech_ai": "AI",
        "tech_embodied": "具身智能",
        "tech_biotech": "生物科技",
        "tech_space": "太空探索与无人机",
        "tech_spatial": "空间计算",
        "finance": "金融",
        "geo": "地缘政治",
        "crypto": "加密",
    }
    section_order = [s for s in SECTION_ORDER if s in sections]
    for key in section_order:
        count = len(sections.get(key, {}).get("items", []))
        main_lines.append(f"- {section_names.get(key, key)}: {count}")
    messages.append({"key": "main", "text_html": "\n".join(main_lines)})

    if butterfly_effect:
        lines = [f"<b>跨板块蝴蝶效应</b> · {content_date_bj}", html.escape(butterfly_effect)]
        messages.append({"key": "butterfly", "text_html": "\n".join(lines)})

    for key in section_order:
        title = section_names.get(key, key)
        lines = [f"<b>{title}</b> · {content_date_bj}"]
        for idx, item in enumerate(sections.get(key, {}).get("items", []), start=1):
            explain = item["explain_zh"]
            lines.append("")
            lines.append(f"{idx}) {html.escape(explain['what_happened'])}")
            lines.append(f"重要性：{html.escape(explain['why_it_matters'])}")
            lines.append(f"点评：{html.escape(explain.get('viewpoint', ''))}")
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
    content_date_bj = now_bj.date().isoformat()

    config = load_sources(args.sources)
    sections_config = config.get("sections", {})

    all_items: Dict[str, List[Item]] = {}
    errors: List[str] = []
    sources_used: List[Dict[str, Any]] = []

    for section, section_cfg in sections_config.items():
        canonical_section = SECTION_ALIASES.get(section, section)
        all_items.setdefault(canonical_section, [])
        for source in section_cfg.get("primary_sources", []):
            feed_urls = resolve_feed_urls(source, errors)
            for feed_url in feed_urls:
                try:
                    feed = fetch_feed(feed_url)
                    items = extract_items_from_feed(canonical_section, source["name"], feed, False)
                    all_items[canonical_section].extend(items)
                    sources_used.append({"section": canonical_section, "source": source["name"], "url": feed_url, "count": len(items)})
                except Exception as exc:
                    errors.append(f"{canonical_section}:{source['name']}::{feed_url}::{exc}")
        for source in section_cfg.get("hot_signal_sources", []):
            feed_urls = resolve_feed_urls(source, errors)
            for feed_url in feed_urls:
                try:
                    feed = fetch_feed(feed_url)
                    items = extract_items_from_feed(canonical_section, source["name"], feed, True)
                    all_items[canonical_section].extend(items)
                    sources_used.append({"section": canonical_section, "source": source["name"], "url": feed_url, "count": len(items), "hot_signal": True})
                except Exception as exc:
                    errors.append(f"{canonical_section}:{source['name']}::{feed_url}::{exc}")

    client: Optional[LLMClient] = None
    if not args.no_llm:
        deepseek_key = os.getenv("DEEPSEEK_API_KEY")
        if not deepseek_key:
            errors.append("DEEPSEEK_API_KEY is missing; falling back to no-llm mode")
        else:
            model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
            api_base = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com")
            client = DeepSeekClient(api_key=deepseek_key, model=model, api_base=api_base)

    sections_output: Dict[str, Dict[str, Any]] = {}
    dedup_stats: Dict[str, Any] = {}
    selected_for_highlights: List[Dict[str, Any]] = []
    global_selected: List[Item] = []

    section_order = [s for s in SECTION_ORDER if s in all_items]
    for section in list(all_items.keys()):
        if section not in section_order:
            section_order.append(section)

    now_dt = dt.datetime.now(tz_bj)
    for section in section_order:
        items = all_items.get(section, [])
        filtered = filter_by_date(items, now_dt)
        hot_titles = extract_hot_signal_titles(filtered)
        primary_items = [i for i in filtered if not i.is_hot_signal]
        clusters = build_clusters(primary_items)

        scored: List[Tuple[float, Item, List[Item]]] = []
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
        section_items: List[Dict[str, Any]] = []
        primary_items: List[Item] = []
        skipped_global_dup = 0
        for _, primary, _ in scored:
            if len(primary_items) >= MAX_ITEMS_PER_SECTION:
                break
            if is_duplicate_global(primary, global_selected):
                skipped_global_dup += 1
                continue
            primary_items.append(primary)
            global_selected.append(primary)
        explains: List[Dict[str, str]] = []
        if client is not None and primary_items:
            try:
                explains = generate_explain_batch(client, primary_items)
            except Exception as exc:
                errors.append(f"LLM batch failed: {section}:{exc}")
                explains = []
        if len(explains) != len(primary_items):
            explains = [fallback_explain(item) for item in primary_items]
        for primary, explain in zip(primary_items, explains):
            image_url = resolve_image_url(primary)
            section_items.append({
                "title_en": primary.title_en,
                "source": primary.source,
                "url": primary.url,
                "published_at": primary.published_at,
                "explain_zh": explain,
                "image_url": image_url,
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
            "skipped_global_dup": skipped_global_dup,
        }

    if client is None:
        highlights_zh = fallback_highlights("LLM未启用或失败")
    else:
        try:
            highlights_zh = generate_highlights(client, selected_for_highlights)
        except Exception as exc:
            errors.append(f"LLM highlights failed: {exc}")
            highlights_zh = fallback_highlights("LLM失败")

    if client is None:
        butterfly_effect_zh = fallback_butterfly_effect("LLM未启用或失败")
    else:
        try:
            butterfly_effect_zh = generate_butterfly_effect(client, selected_for_highlights)
        except Exception as exc:
            errors.append(f"LLM butterfly effect failed: {exc}")
            butterfly_effect_zh = fallback_butterfly_effect("LLM失败")

    telegram_messages = build_telegram_messages(
        content_date_bj, highlights_zh, sections_output, butterfly_effect_zh
    )

    output = {
        "meta": {
            "version": "1",
            "publish_date_bj": publish_date_bj,
            "content_date_bj": content_date_bj,
            "window_hours": WINDOW_HOURS,
            "generated_at": dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc).isoformat(),
        },
        "highlights_zh": highlights_zh,
        "butterfly_effect_zh": butterfly_effect_zh,
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
