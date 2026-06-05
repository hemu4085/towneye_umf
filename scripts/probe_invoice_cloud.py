#!/usr/bin/env python3
"""One-shot probe for Invoice Cloud guest parcel lookup (dev only)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import requests

PARCEL = sys.argv[1] if len(sys.argv) > 1 else "128.0-0003-0012.0"
BG = "5e51c1b1-f981-4a8c-ad97-3ffd74eacb9b"
ITI = "8"
VSII = "346"
VANITY = "https://www.invoicecloud.com/arlingtonma"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def _hidden_fields(html: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in re.finditer(
        r'<input[^>]+type="hidden"[^>]+name="([^"]+)"[^>]+value="([^"]*)"',
        html,
        re.I,
    ):
        out[m.group(1)] = m.group(2)
    for m in re.finditer(
        r'<input[^>]+type="hidden"[^>]+value="([^"]*)"[^>]+name="([^"]+)"',
        html,
        re.I,
    ):
        out[m.group(2)] = m.group(1)
    return out


def _text_fields(html: str) -> list[str]:
    return [
        m.group(1)
        for m in re.finditer(
            r'<input[^>]+type="text"[^>]+name="([^"]+)"',
            html,
            re.I,
        )
    ]


def _submit_buttons(html: str) -> list[tuple[str, str]]:
    return [
        (m.group(1), m.group(2))
        for m in re.finditer(
            r'<input[^>]+type="submit"[^>]+name="([^"]+)"[^>]*value="([^"]*)"',
            html,
            re.I,
        )
    ]


def main() -> int:
    session = requests.Session()
    session.headers["User-Agent"] = UA

    landing = session.get(VANITY, timeout=30)
    landing.raise_for_status()
    m = re.search(r"/portal/\(S\(([^)]+)\)\)/2", landing.text)
    if not m:
        print("NO_SESSION")
        return 1
    sess = m.group(1)
    print("SESSION", sess)

    base = f"https://www.invoicecloud.com/portal/(S({sess}))/2"
    loc_url = f"{base}/customerlocator.aspx?iti={ITI}&bg={BG}&vsii={VSII}&return=1"
    loc = session.get(loc_url, timeout=30)
    loc.raise_for_status()
    Path("/tmp/ic-locator-req.html").write_text(loc.text, encoding="utf-8")
    print("LOCATOR_LEN", len(loc.text))

    hidden = _hidden_fields(loc.text)
    texts = _text_fields(loc.text)
    buttons = _submit_buttons(loc.text)
    print("TEXT_FIELDS", texts)
    print("BUTTONS", buttons)
    all_inputs = re.findall(r"<input[^>]+>", loc.text, re.I)
    print("ALL_INPUTS", len(all_inputs))
    for tag in all_inputs[:15]:
        print(" ", tag[:220])
    Path("data/cache/ic-locator-debug.html").parent.mkdir(parents=True, exist_ok=True)
    Path("data/cache/ic-locator-debug.html").write_text(loc.text, encoding="utf-8")
    print("WROTE data/cache/ic-locator-debug.html")

    search_name = next(
        (n for n in texts if re.search(r"locator|account|parcel|txt", n, re.I)),
        texts[0] if texts else None,
    )
    if not search_name or not buttons:
        print("NO_FORM")
        return 1

    data = dict(hidden)
    data[search_name] = PARCEL
    btn_name, btn_val = buttons[0]
    data[btn_name] = btn_val

    result = session.post(loc_url, data=data, timeout=30)
    Path("/tmp/ic-search-result.html").write_text(result.text, encoding="utf-8")
    print("POST_STATUS", result.status_code, "LEN", len(result.text))
    print("FINAL_URL", result.url)

    low = result.text.lower()
    for kw in ("balance", "due", "paid", "current", "delinquent", "walnut", "128.0", "quarter", "amount"):
        if kw in low:
            print("HAS", kw)

    rows = re.findall(r"<tr[^>]*>.*?</tr>", result.text, re.I | re.S)
    print("ROWS", len(rows))
    for row in rows[:8]:
        text = re.sub(r"<[^>]+>", " ", row)
        text = " ".join(text.split())
        if text.strip():
            print("ROW", text[:240])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
