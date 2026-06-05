"""Tests for Invoice Cloud guest property-tax lookup."""

from __future__ import annotations

from backend.services.invoice_cloud_client import (
    _infer_status,
    _parse_invoice_tables,
    lookup_property_tax_live,
)


def test_infer_status_current_when_zero_balance():
    assert _infer_status(0.0, "Paid in full") == "CURRENT"


def test_infer_status_past_due_with_balance():
    assert _infer_status(1250.0, "Open bill") == "PAST_DUE"


def test_parse_invoice_table_rows():
    html = """
    <html><body>
      <table>
        <tr><th>Description</th><th>Due Date</th><th>Amount</th><th>Balance</th><th>Status</th></tr>
        <tr>
          <td>Q3 Real Estate</td><td>02/01/2026</td><td>$1,200.00</td><td>$0.00</td><td>Paid</td>
        </tr>
      </table>
      <div>Parcel 128.0-0003-0012.0</div>
    </body></html>
    """
    rows = _parse_invoice_tables(html, "128.0-0003-0012.0")
    assert len(rows) >= 1
    assert rows[0]["parcel_id"] == "128.0-0003-0012.0"
    assert rows[0]["balance_due"] == 0
    assert rows[0]["status"] in {"CURRENT", "PAID", "UNKNOWN", "OPEN"}


def test_live_lookup_disabled_returns_empty():
    town_cfg = {"lender_report": {"invoice_cloud": {"enabled": False}}}
    assert lookup_property_tax_live(town_cfg, "128.0-0003-0012.0") == []
