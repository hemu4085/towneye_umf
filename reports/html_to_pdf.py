# [FILE PATH]: reports/html_to_pdf.py
"""
HTML → PDF conversion for buildability brief exports.

Uses Playwright (Chromium) when available; falls back to wkhtmltopdf.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import os
from datetime import date
from pathlib import Path

_META_SEP = r"&nbsp;\s*(?:·|&middot;)\s*&nbsp;\s*"
_PREPARED_FOR_RE = re.compile(
    rf"Prepared for [^<&]+?\s*{_META_SEP}",
    re.IGNORECASE,
)
_PREPARED_ON_RE = re.compile(
    rf"Prepared on [^<&]+?\s*{_META_SEP}",
    re.IGNORECASE,
)


def format_report_date(d: date) -> str:
    """Human-readable date matching brief headers (e.g. May 5, 2026)."""
    return f"{d.strftime('%B')} {d.day}, {d.year}"


def patch_prepared_for(
    html: str,
    *,
    prepared_for: str | None = None,
    prepared_on: date | None = None,
    remove_prepared_for: bool = False,
) -> str:
    """
    Replace, insert, or remove the ``Prepared for`` / ``Prepared on`` header lines.

    When ``prepared_for`` is a non-empty string, any existing recipient name
    is replaced — or the line is inserted when absent.  When
    ``remove_prepared_for`` is true (or ``prepared_for`` is an empty string),
    the recipient line is dropped entirely.
    """
    if remove_prepared_for or prepared_for == "":
        html = _PREPARED_FOR_RE.sub("", html, count=1)
    elif prepared_for is not None:
        recipient = f"Prepared for {prepared_for} &nbsp;·&nbsp; "
        if _PREPARED_FOR_RE.search(html):
            html = _PREPARED_FOR_RE.sub(recipient, html, count=1)
        elif _PREPARED_ON_RE.search(html):
            html = _PREPARED_ON_RE.sub(recipient + r"\g<0>", html, count=1)
        else:
            html = re.sub(
                r'(<div class="meta">\s*)',
                rf"\1{recipient}",
                html,
                count=1,
            )

    if prepared_on is not None:
        date_line = f"Prepared on {format_report_date(prepared_on)} &nbsp;·&nbsp; "
        if _PREPARED_ON_RE.search(html):
            html = _PREPARED_ON_RE.sub(date_line, html, count=1)
        elif prepared_for and not remove_prepared_for:
            html = re.sub(
                rf"(Prepared for {re.escape(prepared_for)} &nbsp;·&nbsp; )",
                rf"\1{date_line}",
                html,
                count=1,
            )
        else:
            html = re.sub(
                r'(<div class="meta">\s*)',
                rf"\1{date_line}",
                html,
                count=1,
            )

    return html


def agent_brief_pdf_path(agent_name: str, output_dir: Path | None = None) -> Path:
    """
    Standard agent brief filename: ``29_walnut_buildability_brief_for_jane_smith.pdf``.
    """
    out_dir = output_dir or Path("reports/output")
    slug = slugify_prepared_for(agent_name.strip())
    return out_dir / f"29_walnut_buildability_brief_for_{slug}.pdf"


def export_agent_brief(
    html_path: Path,
    agent_name: str,
    *,
    pdf_path: Path | None = None,
    prepared_on: date | None = None,
    output_dir: Path | None = None,
) -> Path:
    """
    Export one agent-specific PDF from a brief HTML template.

    Sets the header ``Prepared for`` line and writes
    ``29_walnut_buildability_brief_for_{name}.pdf`` by default.
    """
    agent_name = agent_name.strip()
    if not agent_name:
        raise ValueError("agent_name must be a non-empty string")

    out_dir = output_dir or html_path.parent
    destination = pdf_path or agent_brief_pdf_path(agent_name, out_dir)
    convert_html_to_pdf(
        html_path,
        destination,
        prepared_for=agent_name,
        prepared_on=prepared_on or date.today(),
    )
    return destination


def slugify_prepared_for(name: str) -> str:
    """Lowercase recipient name for use in filenames (e.g. 'Julie Gibson' → 'julie_gibson')."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def first_name_slug(name: str) -> str:
    """First name only, slugified (e.g. 'Jane Smith' → 'jane')."""
    first = name.strip().split()[0] if name.strip() else ""
    return re.sub(r"[^a-z0-9]+", "", first.lower())


def parcel_slug_for_pdf(parcel_id: str) -> str:
    """
    Compact parcel id for PDF filenames.

    ``128.0-0003-0012.0`` → ``128-3-12``
    """
    normalized = parcel_id.replace(".0", "")
    parts = normalized.split("-")
    segments: list[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if part.isdigit():
            segments.append(str(int(part)))
        else:
            segments.append(part)
    return "-".join(segments)


def pdf_output_path(
    html_path: Path,
    *,
    prepared_for: str | None = None,
    town_slug: str | None = None,
    parcel_id: str | None = None,
) -> Path:
    """
    Resolve the PDF destination path.

    When ``prepared_for`` is set, append the agent's first name so each
    recipient gets a unique file (e.g. ``brief_jane.pdf``).  Without a
    recipient, replace the HTML suffix with ``.pdf``.
    """
    if prepared_for:
        agent = first_name_slug(prepared_for)
        if agent:
            if town_slug and parcel_id:
                town_prefix = town_slug.split("-")[0]
                parcel_part = parcel_slug_for_pdf(parcel_id)
                return html_path.parent / f"{town_prefix}_{parcel_part}_{agent}.pdf"
            return html_path.with_name(f"{html_path.stem}_{agent}.pdf")
    return html_path.with_suffix(".pdf")


def _convert_with_playwright(html_path: Path, pdf_path: Path, *, html: str | None = None) -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False

    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page()
            if html is not None:
                page.set_content(html, wait_until="networkidle")
            else:
                page.goto(html_path.resolve().as_uri(), wait_until="networkidle")
            page.emulate_media(media="print")
            page.pdf(path=str(pdf_path), print_background=True)
        finally:
            browser.close()
    return True


def _convert_with_wkhtmltopdf(html_path: Path, pdf_path: Path, *, html: str | None = None) -> bool:
    wkhtmltopdf = shutil.which("wkhtmltopdf")
    if not wkhtmltopdf:
        return False

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    source = html_path
    temp_html: Path | None = None
    if html is not None:
        fd, temp_name = tempfile.mkstemp(suffix=".html", prefix="brief_")
        os.close(fd)
        temp_html = Path(temp_name)
        temp_html.write_text(html, encoding="utf-8")
        source = temp_html

    try:
        subprocess.run(
            [wkhtmltopdf, str(source.resolve()), str(pdf_path.resolve())],
            check=True,
            capture_output=True,
        )
    finally:
        if temp_html is not None:
            temp_html.unlink(missing_ok=True)
    return True


def convert_html_to_pdf(
    html_path: Path,
    pdf_path: Path,
    *,
    prepared_for: str | None = None,
    prepared_on: date | None = None,
    remove_prepared_for: bool = False,
) -> None:
    """
    Convert ``html_path`` to ``pdf_path``.

    Pass ``prepared_for`` to replace the header recipient name before rendering.
    Pass ``prepared_on`` to replace the header date.  Set ``remove_prepared_for``
    (or ``prepared_for=""``) to drop the recipient line entirely.

    Raises ``FileNotFoundError`` if the HTML file is missing.
    Raises ``RuntimeError`` if no PDF backend is available.
    """
    if not html_path.is_file():
        raise FileNotFoundError(f"HTML output not found: {html_path}")

    html: str | None = None
    if remove_prepared_for or prepared_for is not None or prepared_on is not None:
        html = patch_prepared_for(
            html_path.read_text(encoding="utf-8"),
            prepared_for=prepared_for,
            prepared_on=prepared_on,
            remove_prepared_for=remove_prepared_for,
        )

    if _convert_with_playwright(html_path, pdf_path, html=html):
        return
    if _convert_with_wkhtmltopdf(html_path, pdf_path, html=html):
        return

    raise RuntimeError(
        "PDF export requires Playwright (pip install playwright && playwright install chromium) "
        "or wkhtmltopdf on PATH."
    )
