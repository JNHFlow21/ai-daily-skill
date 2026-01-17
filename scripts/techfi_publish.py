#!/usr/bin/env python3
import argparse
import html
import time
import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

TIMEOUT_SECS = 20

SECTION_TITLES = {
    "tech_ai": "AI",
    "tech_embodied": "具身智能",
    "tech_biotech": "生物科技",
    "tech_space": "太空探索与无人机",
    "tech_spatial": "空间计算",
    "finance": "金融",
    "geo": "地缘政治",
    "crypto": "加密",
}

TECH_SECTION_KEYS = [
    "tech_ai",
    "tech_embodied",
    "tech_biotech",
    "tech_space",
    "tech_spatial",
]

SECTION_ORDER = TECH_SECTION_KEYS + ["finance", "geo", "crypto"]


@dataclass
class TelegramMessage:
    key: str
    text_html: str


class TelegramClient:
    def __init__(self, token: str, chat_id: str) -> None:
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{token}"

    def _post(self, method: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}/{method}"
        last_error: Optional[Exception] = None
        for attempt in range(5):
            response = requests.post(url, json=payload, timeout=TIMEOUT_SECS)
            if response.status_code == 429:
                try:
                    data = response.json()
                except Exception:
                    data = {}
                retry_after = None
                if isinstance(data, dict):
                    retry_after = data.get("parameters", {}).get("retry_after")
                if not retry_after:
                    retry_after = response.headers.get("Retry-After")
                if retry_after:
                    try:
                        time.sleep(float(retry_after))
                        continue
                    except Exception:
                        pass
                time.sleep(min(2 ** attempt, 8))
                last_error = RuntimeError(data or response.text)
                continue
            if response.status_code >= 500:
                time.sleep(min(2 ** attempt, 8))
                last_error = RuntimeError(response.text)
                continue
            response.raise_for_status()
            data = response.json()
            if not data.get("ok"):
                raise RuntimeError(data)
            return data
        if last_error:
            raise last_error
        raise RuntimeError("Telegram request failed without response")

    def send_message(self, text_html: str) -> int:
        payload = {
            "chat_id": self.chat_id,
            "text": text_html,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        data = self._post("sendMessage", payload)
        return data["result"]["message_id"]

    def edit_message(self, message_id: int, text_html: str) -> None:
        payload = {
            "chat_id": self.chat_id,
            "message_id": message_id,
            "text": text_html,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        self._post("editMessageText", payload)

    def send_photo(self, photo_url: str, caption: Optional[str] = None) -> int:
        payload: Dict[str, Any] = {
            "chat_id": self.chat_id,
            "photo": photo_url,
        }
        if caption:
            payload["caption"] = caption
            payload["parse_mode"] = "HTML"
        data = self._post("sendPhoto", payload)
        return data["result"]["message_id"]

    def edit_photo(self, message_id: int, photo_url: str, caption: Optional[str] = None) -> None:
        media: Dict[str, Any] = {"type": "photo", "media": photo_url}
        if caption:
            media["caption"] = caption
            media["parse_mode"] = "HTML"
        payload = {
            "chat_id": self.chat_id,
            "message_id": message_id,
            "media": media,
        }
        self._post("editMessageMedia", payload)


class BitableClient:
    def __init__(self, app_id: str, app_secret: str, app_token: str, table_id: str) -> None:
        self.app_id = app_id
        self.app_secret = app_secret
        self.app_token = app_token
        self.table_id = table_id
        self._token: Optional[str] = None

    def _get_token(self) -> str:
        if self._token:
            return self._token
        url = "https://open.larksuite.com/open-apis/auth/v3/tenant_access_token/internal"
        payload = {"app_id": self.app_id, "app_secret": self.app_secret}
        response = requests.post(url, json=payload, timeout=TIMEOUT_SECS)
        response.raise_for_status()
        data = response.json()
        if data.get("code") != 0:
            raise RuntimeError(data)
        self._token = data["tenant_access_token"]
        return self._token

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self._get_token()}", "Content-Type": "application/json"}

    def search_by_content_date(self, content_date_bj: str) -> Optional[Dict[str, Any]]:
        url = (
            "https://open.larksuite.com/open-apis/bitable/v1/"
            f"apps/{self.app_token}/tables/{self.table_id}/records/search"
        )
        payload = {
            "filter": {
                "conjunction": "and",
                "conditions": [
                    {"field_name": "content_date_bj", "operator": "is", "value": [content_date_bj]}
                ],
            }
        }
        response = requests.post(url, json=payload, headers=self._headers(), timeout=TIMEOUT_SECS)
        if not response.ok:
            raise RuntimeError(f"Bitable search failed: {response.status_code} {response.text}")
        data = response.json()
        if data.get("code") != 0:
            raise RuntimeError(data)
        items = data.get("data", {}).get("items", [])
        return items[0] if items else None

    def create_record(self, fields: Dict[str, Any]) -> Dict[str, Any]:
        url = (
            "https://open.larksuite.com/open-apis/bitable/v1/"
            f"apps/{self.app_token}/tables/{self.table_id}/records"
        )
        payload = {"fields": fields}
        response = requests.post(url, json=payload, headers=self._headers(), timeout=TIMEOUT_SECS)
        response.raise_for_status()
        data = response.json()
        if data.get("code") != 0:
            raise RuntimeError(data)
        return data.get("data", {})

    def update_record(self, record_id: str, fields: Dict[str, Any]) -> None:
        url = (
            "https://open.larksuite.com/open-apis/bitable/v1/"
            f"apps/{self.app_token}/tables/{self.table_id}/records/{record_id}"
        )
        payload = {"fields": fields}
        response = requests.put(url, json=payload, headers=self._headers(), timeout=TIMEOUT_SECS)
        response.raise_for_status()
        data = response.json()
        if data.get("code") != 0:
            raise RuntimeError(data)


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


def load_artifact(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_artifact(data: Dict[str, Any]) -> None:
    required = [
        ("meta", "publish_date_bj"),
        ("meta", "content_date_bj"),
        ("telegram", "messages"),
    ]
    for parent, key in required:
        if parent not in data or key not in data[parent]:
            raise ValueError(f"Missing {parent}.{key}")


def render_section_text(items: List[Dict[str, Any]]) -> str:
    lines = []
    for idx, item in enumerate(items, start=1):
        explain = item.get("explain_zh", {})
        line = (
            f"{idx}. {explain.get('what_happened', '')} "
            f"| {explain.get('why_it_matters', '')} "
            f"| {explain.get('viewpoint', '')} "
            f"| {explain.get('what_to_watch', '')}"
        )
        lines.append(line.strip())
    return "\n".join(lines)


def render_grouped_section_text(groups: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for group in groups:
        title = group.get("title", "")
        items = group.get("items", [])
        if title:
            lines.append(f"[{title}]")
        if items:
            lines.append(render_section_text(items))
        lines.append("")
    return "\n".join(lines).strip()


def limit_message(text: str, limit: int = 3800) -> str:
    if len(text) <= limit:
        return text
    lines = text.split("\n")
    while lines and len("\n".join(lines)) > limit - 20:
        lines.pop()
    return "\n".join(lines) + "\n..."


def limit_caption(text: str, limit: int = 900) -> str:
    if len(text) <= limit:
        return text
    lines = text.split("\n")
    while lines and len("\n".join(lines)) > limit - 20:
        lines.pop()
    return "\n".join(lines) + "\n..."


def send_with_fallback(
    telegram_client: TelegramClient,
    key_text: str,
    text_html: str,
    image_url: Optional[str],
    existing_ids: Dict[str, int],
    errors: List[str],
) -> Optional[int]:
    has_image = image_url and str(image_url).startswith(("http://", "https://"))
    if has_image:
        if key_text in existing_ids:
            try:
                telegram_client.edit_photo(existing_ids[key_text], str(image_url), text_html)
                return existing_ids[key_text]
            except Exception:
                try:
                    return telegram_client.send_message(text_html)
                except Exception as exc:
                    errors.append(f"Telegram item {key_text} failed: {exc}")
                    return None
        try:
            return telegram_client.send_photo(str(image_url), text_html)
        except Exception:
            try:
                return telegram_client.send_message(text_html)
            except Exception as exc:
                errors.append(f"Telegram item {key_text} failed: {exc}")
                return None
    if key_text in existing_ids:
        try:
            telegram_client.edit_message(existing_ids[key_text], text_html)
            return existing_ids[key_text]
        except Exception:
            try:
                return telegram_client.send_message(text_html)
            except Exception as exc:
                errors.append(f"Telegram item {key_text} failed: {exc}")
                return None
    try:
        return telegram_client.send_message(text_html)
    except Exception as exc:
        errors.append(f"Telegram item {key_text} failed: {exc}")
        return None


def parse_tg_message_ids(value: Optional[str]) -> Dict[str, int]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
        return {k: int(v) for k, v in parsed.items()}
    except Exception:
        return {}


def render_item_html(section_title: str, content_date_bj: str, idx: int, item: Dict[str, Any]) -> str:
    explain = item.get("explain_zh", {})
    url = html.escape(item.get("url", ""))
    source = html.escape(item.get("source", ""))
    lines = [
        f"<b>{section_title}</b> · {content_date_bj}",
        f"{idx}) {html.escape(explain.get('what_happened', ''))}",
        f"重要性：{html.escape(explain.get('why_it_matters', ''))}",
        f"点评：{html.escape(explain.get('viewpoint', ''))}",
        f"关注：{html.escape(explain.get('what_to_watch', ''))}",
        f"来源：<a href=\"{url}\">{source}</a>",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish TechFiDaily to Telegram and Lark Bitable")
    parser.add_argument("--artifact", default="artifacts/techfi-daily/latest.json")
    args = parser.parse_args()

    load_env_file()

    artifact = load_artifact(args.artifact)
    validate_artifact(artifact)

    publish_date_bj = artifact["meta"]["publish_date_bj"]
    content_date_bj = artifact["meta"]["content_date_bj"]

    highlights_zh = artifact.get("highlights_zh", [])
    sections = artifact.get("sections", {})

    tech_groups = [
        {"title": SECTION_TITLES[key], "items": sections.get(key, {}).get("items", [])}
        for key in TECH_SECTION_KEYS
    ]

    base_fields = {
        "publish_date_bj": publish_date_bj,
        "content_date_bj": content_date_bj,
        "title": f"TechFiDaily {content_date_bj}",
        "highlights": "\n".join(highlights_zh),
        "tech_md": render_grouped_section_text(tech_groups),
        "finance_md": render_section_text(sections.get("finance", {}).get("items", [])),
        "geo_md": render_section_text(sections.get("geo", {}).get("items", [])),
        "crypto_md": render_section_text(sections.get("crypto", {}).get("items", [])),
    }

    errors: List[str] = []
    bitable_record_id: Optional[str] = None
    bitable_client: Optional[BitableClient] = None
    bitable_ok = False

    app_id = os.getenv("LARK_APP_ID")
    app_secret = os.getenv("LARK_APP_SECRET")
    app_token = os.getenv("LARK_BITABLE_APP_TOKEN")
    table_id = os.getenv("LARK_BITABLE_TABLE_ID")

    if app_id and app_secret and app_token and table_id:
        try:
            bitable_client = BitableClient(app_id, app_secret, app_token, table_id)
            record = bitable_client.search_by_content_date(content_date_bj)
            if record:
                bitable_record_id = record["record_id"]
                bitable_client.update_record(bitable_record_id, base_fields)
            else:
                created = bitable_client.create_record(base_fields)
                bitable_record_id = created.get("record_id")
            bitable_ok = True
        except Exception as exc:
            errors.append(f"Bitable error: {exc}")
    else:
        errors.append("Bitable env vars missing; skip bitable")

    tg_token = os.getenv("TG_BOT_TOKEN")
    tg_chat_id = os.getenv("TG_CHAT_ID")
    telegram_ok = False
    tg_message_ids: Dict[str, int] = {}

    if tg_token and tg_chat_id:
        try:
            telegram_client = TelegramClient(tg_token, tg_chat_id)
            existing_ids = {}
            if bitable_record_id and bitable_client:
                record = bitable_client.search_by_content_date(content_date_bj)
                if record:
                    existing_ids = parse_tg_message_ids(record.get("fields", {}).get("tg_message_ids"))

            messages = artifact.get("telegram", {}).get("messages", [])
            message_map = {m.get("key"): m for m in messages if m.get("key")}

            main_message = message_map.get("main")
            if main_message:
                text_html = limit_message(main_message.get("text_html", ""))
                if text_html:
                    if "main" in existing_ids:
                        try:
                            telegram_client.edit_message(existing_ids["main"], text_html)
                            tg_message_ids["main"] = existing_ids["main"]
                        except Exception:
                            tg_message_ids["main"] = telegram_client.send_message(text_html)
                    else:
                        tg_message_ids["main"] = telegram_client.send_message(text_html)

            butterfly_message = message_map.get("butterfly")
            if butterfly_message:
                text_html = limit_message(butterfly_message.get("text_html", ""))
                if text_html:
                    if "butterfly" in existing_ids:
                        try:
                            telegram_client.edit_message(existing_ids["butterfly"], text_html)
                            tg_message_ids["butterfly"] = existing_ids["butterfly"]
                        except Exception:
                            tg_message_ids["butterfly"] = telegram_client.send_message(text_html)
                    else:
                        tg_message_ids["butterfly"] = telegram_client.send_message(text_html)

            for section in SECTION_ORDER:
                items = sections.get(section, {}).get("items", [])
                for idx, item in enumerate(items, start=1):
                    key_text = f"{section}-{idx}"
                    text_html = limit_caption(
                        render_item_html(SECTION_TITLES.get(section, section), content_date_bj, idx, item)
                    )
                    message_id = send_with_fallback(
                        telegram_client,
                        key_text,
                        text_html,
                        item.get("image_url"),
                        existing_ids,
                        errors,
                    )
                    if message_id:
                        tg_message_ids[key_text] = message_id
                    time.sleep(0.2)

            telegram_ok = True
        except Exception as exc:
            errors.append(f"Telegram error: {exc}")
    else:
        errors.append("Telegram env vars missing; skip telegram")

    status = "success"
    if errors and (telegram_ok or bitable_ok):
        status = "partial"
    if errors and not (telegram_ok or bitable_ok):
        status = "fail"

    if bitable_client and bitable_record_id:
        update_fields = {
            "status": status,
            "error": "\n".join(errors),
        }
        if tg_message_ids:
            update_fields["tg_message_ids"] = json.dumps(tg_message_ids)
        try:
            bitable_client.update_record(bitable_record_id, update_fields)
        except Exception as exc:
            errors.append(f"Bitable update error: {exc}")

    print(f"Publish status: {status}")
    if errors:
        print("Errors:")
        for err in errors:
            print(f"- {err}")

    return 0 if status != "fail" else 1


if __name__ == "__main__":
    raise SystemExit(main())
