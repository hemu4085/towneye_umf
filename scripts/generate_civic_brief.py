import argparse
import sys
import logging
from datetime import date
from reports.civic_entitlements_brief import CivicBriefInputs, CivicEntitlementsBriefGenerator

def main() -> int:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Tier 4 — Civic Entitlements Brief Generator")
    parser.add_argument("--town", required=True, help="Town slug (e.g. arlington-ma)")
    parser.add_argument("--parcel", required=True, help="Parcel ID (e.g. 008.0-0001-0010.0)")
    parser.add_argument("--output", required=True, help="Path to write the HTML output")
    args = parser.parse_args()

    inputs = CivicBriefInputs(
        town_slug=args.town,
        parcel_id=args.parcel,
        prepared_on=date.today()
    )

    generator = CivicEntitlementsBriefGenerator(town_slug=args.town, data_dir="data/gold")
    html = generator.generate(inputs)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(html)
        
    print(f"[OK] Wrote {args.output}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
