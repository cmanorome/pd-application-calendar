from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any


def _fold(line: str) -> str:
    if len(line) <= 75:
        return line
    chunks = [line[:75]]
    rest = line[75:]
    while rest:
        chunks.append(" " + rest[:74])
        rest = rest[74:]
    return "\r\n".join(chunks)


def _esc(text: str) -> str:
    return (
        (text or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def to_ics(
    events: list[dict[str, Any]],
    *,
    calendar_name: str = "Plant Doctor application calendar",
    plan_id: str | None = None,
) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Plant Doctor//Application Calendar//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_esc(calendar_name)}",
        "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
        "X-PUBLISHED-TTL:PT12H",
    ]
    uid_ns = plan_id or "download"
    for i, ev in enumerate(events):
        day = date.fromisoformat(ev["date"])
        end = day + timedelta(days=1)
        usage = ev.get("usage_labels") or []
        desc_parts = [
            ev.get("how_often") or "",
            ", ".join(usage) if usage else "",
            ev.get("amount_label") or ev.get("rate_label") or "",
            ev.get("notes") or "",
            ev.get("product_url") or "",
        ]
        desc = "\\n".join(_esc(p) for p in desc_parts if p)
        sku = ev.get("sku") or "pd"
        uid = f"{uid_ns}-{sku}-{ev['date']}-{i}@plantdoctor.com.au"
        summary = f"Plant Doctor: {ev.get('name') or 'Application'}"
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{stamp}",
                f"DTSTART;VALUE=DATE:{day.strftime('%Y%m%d')}",
                f"DTEND;VALUE=DATE:{end.strftime('%Y%m%d')}",
                _fold(f"SUMMARY:{_esc(summary)}"),
                _fold(f"DESCRIPTION:{desc}"),
                "END:VEVENT",
            ]
        )
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
