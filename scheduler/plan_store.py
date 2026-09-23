from __future__ import annotations

import json
import os
import re
import secrets
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
LOCAL_DIR = ROOT / "data" / "subscribed_plans"
_ID_RE = re.compile(r"^[a-f0-9]{16}$")
_KEY_PREFIX = "pdcal:"


def _redis_creds() -> tuple[str, str] | None:
    url = (os.environ.get("KV_REST_API_URL") or os.environ.get("UPSTASH_REDIS_REST_URL") or "").strip()
    token = (os.environ.get("KV_REST_API_TOKEN") or os.environ.get("UPSTASH_REDIS_REST_TOKEN") or "").strip()
    if url and token:
        return url.rstrip("/"), token
    return None


def new_plan_id() -> str:
    return secrets.token_hex(8)


def parse_plan_id(raw: str) -> str | None:
    text = str(raw or "").strip()
    if text.lower().endswith(".ics"):
        text = text[:-4]
    text = text.strip("/").lower()
    if _ID_RE.fullmatch(text):
        return text
    return None


def _upstash(url: str, token: str, command: list[str]) -> Any:
    req = urllib.request.Request(
        url,
        data=json.dumps(command).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload.get("result")


def save_form(form: dict[str, Any], plan_id: str | None = None) -> str:
    pid = plan_id or new_plan_id()
    blob = json.dumps({"v": 1, "form": form}, separators=(",", ":"))
    creds = _redis_creds()
    if creds:
        try:
            _upstash(*creds, ["SET", f"{_KEY_PREFIX}{pid}", blob])
        except urllib.error.URLError as exc:
            raise RuntimeError("Could not save the calendar for subscribe.") from exc
        return pid
    if os.environ.get("VERCEL"):
        raise RuntimeError("Subscribe storage is not connected on Vercel yet.")
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    (LOCAL_DIR / f"{pid}.json").write_text(blob, encoding="utf-8")
    return pid


def load_form(plan_id: str) -> dict[str, Any] | None:
    pid = parse_plan_id(plan_id)
    if not pid:
        return None
    creds = _redis_creds()
    raw = None
    if creds:
        try:
            raw = _upstash(*creds, ["GET", f"{_KEY_PREFIX}{pid}"])
        except urllib.error.URLError:
            return None
    else:
        path = LOCAL_DIR / f"{pid}.json"
        if path.is_file():
            raw = path.read_text(encoding="utf-8")
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    form = payload.get("form") if isinstance(payload, dict) else None
    return form if isinstance(form, dict) else None
