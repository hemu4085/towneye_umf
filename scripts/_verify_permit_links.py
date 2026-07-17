from backend.services.parcel_permits import get_parcel_permits, resolve_permit_external_link

# Without OpenGov record/location IDs: no external URL (portal home is useless for paste lookup)
link = resolve_permit_external_link(
    town_slug="arlington-ma",
    permit_number="D-26-0031",
    address="70-72 Massachusetts Ave, Arlington MA 02474",
    metadata={"address": "70-72 Massachusetts Ave, Arlington MA 02474"},
)
print("resolve", link)
assert link["link_kind"] == "manual"
assert link["detail_url"] is None
assert "searchKey=" not in (link.get("search_hint") or "")
assert "D-26-0031" in (link.get("search_hint") or "")

# With a real record id → /records/{id}
rec = resolve_permit_external_link(
    town_slug="arlington-ma",
    permit_number="X-1",
    metadata={"opengov_record_id": "12345"},
)
print("record", rec)
assert rec["link_kind"] == "record"
assert "/records/12345" in (rec["detail_url"] or "")

rows = get_parcel_permits("arlington-ma", "008.0-0001-0010.0", "5-7 Belknap St")
print("belknap", [(r.get("permit_number"), r.get("link_kind"), r.get("detail_url")) for r in rows[:2]])
assert rows and rows[0].get("link_kind") == "manual"
assert rows[0].get("detail_url") is None
print("OK")
