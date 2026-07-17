#!/usr/bin/env python3
"""One-shot verify Belknap + Walnut for attorney zoning pack."""
from __future__ import annotations

from backend.services.buildability import collect_brief_data, generate_buildability_json
from backend.services.zoning import generate_zoning_json

PARCELS = [
    ("008.0-0001-0010.0", "5-7 Belknap St"),
    ("128.0-0003-0012.0", "29 Walnut St"),
]


def main() -> None:
    for pid, label in PARCELS:
        data = collect_brief_data("arlington-ma", pid)
        z = generate_zoning_json(data)
        generate_buildability_json(data)
        base = [h.code for h in data.base_zoning_hits]
        ov = [h.code for h in data.overlay_zoning_hits]
        nmf_rule = data.zoning_rules.get("NMF")
        envs = [(e.zone_code, e.max_gfa_sqft, e.qualifies, e.max_far) for e in data.envelopes]
        print("=" * 60)
        print(label, pid)
        print("base", base, "overlay", ov)
        print("has_election", data.has_overlay_election, "mbta", data.has_mbta_communities_overlay)
        if nmf_rule:
            print(
                "NMF rule far=",
                nmf_rule.max_far,
                "h=",
                nmf_rule.max_height_ft,
                "notes=",
                (nmf_rule.notes or "")[:90],
            )
        else:
            print("NMF rule MISSING")
        print("envelopes", envs)
        el = z.get("overlay_election") or {}
        print("election", el.get("recommended_regime"), "does_not_stack", el.get("does_not_stack"))
        print("citation:", (el.get("legal_basis") or "")[:100])
        assert el.get("does_not_stack") is True or not data.has_overlay_election
        assert "NMF" in ov, f"{label}: expected NMF overlay"
        assert nmf_rule is not None, f"{label}: NMF config/parquet rule required"
        assert nmf_rule.max_far is not None, f"{label}: NMF FAR missing"
        print("pathway", len(z.get("process_pathway") or []), "footnote", bool(z.get("process_pathway_footnote")))
        for row in (z.get("dimensional_comparison") or {}).get("rows") or []:
            if row["standard"] in ("Min. lot size", "Lot qualifies?", "Max. FAR"):
                print(" ", row["standard"], row["values"])
        print("open_items[0]:", (z.get("open_items") or [""])[0][:120])
    print("OK — Belknap + Walnut attorney checks passed")


if __name__ == "__main__":
    main()
