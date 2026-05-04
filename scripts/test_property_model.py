"""
test_property_model.py
======================
Smoke-tests for the TePropertyAssessment data model changes.

Covers:
  1. Model import & instantiation (core/models.py)
  2. Factory transformation (core/factory.py)
  3. Parquet schema — all 6 towns have the expected first-class columns
  4. DuckDB query smoke-tests — the queries the preset buttons would generate

Run:
    python scripts/test_property_model.py
"""

import pathlib
import sys
import traceback

_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import duckdb
import pandas as pd

PASS = "  \033[32mPASS\033[0m"
FAIL = "  \033[31mFAIL\033[0m"

_TOWNS = [
    "arlington-ma",
    "burlington-ma",
    "lexington-ma",
    "somerville-ma",
    "winchester-ma",
    "woburn-ma",
]

_REQUIRED_COLS = {
    "te_property_pk", "parcel_id", "address",
    "zone_code", "assessed_value", "year_built",
    "building_type", "lot_size_sqft", "luc", "luc_description",
    "beds", "baths", "owner_name", "te_party_pk",
}

errors: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"{PASS}  {label}")
    else:
        msg = f"{label}" + (f" — {detail}" if detail else "")
        print(f"{FAIL}  {msg}")
        errors.append(msg)


# ---------------------------------------------------------------------------
# 1. Model import
# ---------------------------------------------------------------------------
print("\n── 1. Model import ──────────────────────────────────────")
try:
    from core.models import TePropertyAssessment, AuditFields
    check("TePropertyAssessment importable", True)
    fields = set(TePropertyAssessment.model_fields.keys())
    for col in _REQUIRED_COLS:
        check(f"  field '{col}' defined in TePropertyAssessment", col in fields)
except Exception as exc:
    check("TePropertyAssessment importable", False, str(exc))
    traceback.print_exc()


# ---------------------------------------------------------------------------
# 2. Factory round-trip
# ---------------------------------------------------------------------------
print("\n── 2. Factory round-trip ────────────────────────────────")
try:
    from core.factory import MedallionFactory
    factory = MedallionFactory("arlington-ma")
    check("MedallionFactory instantiation", True)

    raw = {
        "te_property_pk": 42,
        "parcel_id": "TEST-001",
        "address": "1 Main St",
        "zone_code": "R-2",
        "total_value": "$550,000",
        "year_built": "1985",
        "building_type": "Colonial",
        "lot_size": "8500",
        "luc": "101",
        "luc_description": "One Family",
        "beds": "3",
        "baths": "2.5",
        "owner_name": "TEST OWNER",
        "te_party_pk": 42,
        "te_source": "test",
        "te_geo_hash": "drt2zh",
        "metadata": {"extra_field": "extra_value"},
    }
    result = factory.map_to_property_assessment(raw)
    check("map_to_property_assessment() returns dict", isinstance(result, dict))
    check("assessed_value coerced to float", result.get("assessed_value") == 550000.0)
    check("year_built coerced to int", result.get("year_built") == 1985)
    check("beds coerced to int", result.get("beds") == 3)
    check("baths coerced to float", result.get("baths") == 2.5)
    check("zone_code preserved", result.get("zone_code") == "R-2")
    check("owner_name preserved", result.get("owner_name") == "TEST OWNER")
    check("audit field te_id present", bool(result.get("te_id")))
    check("audit field te_geo_hash present", bool(result.get("te_geo_hash")))
except Exception as exc:
    check("Factory round-trip", False, str(exc))
    traceback.print_exc()


# ---------------------------------------------------------------------------
# 3. Parquet schema — all towns
# ---------------------------------------------------------------------------
print("\n── 3. Parquet schema (all 6 towns) ──────────────────────")
gold_dir = _ROOT / "data" / "gold"
for town in _TOWNS:
    parquet_path = gold_dir / town / "property.parquet"
    if not parquet_path.exists():
        check(f"{town}/property.parquet exists", False, "file not found")
        continue
    check(f"{town}/property.parquet exists", True)
    try:
        schema_df = duckdb.execute(
            f"DESCRIBE SELECT * FROM read_parquet('{parquet_path}')"
        ).df()
        actual_cols = set(schema_df["column_name"].tolist())
        missing = _REQUIRED_COLS - actual_cols
        check(
            f"  {town}: all required columns present",
            len(missing) == 0,
            f"missing: {missing}" if missing else "",
        )
        n = duckdb.execute(
            f"SELECT COUNT(*) FROM read_parquet('{parquet_path}')"
        ).fetchone()[0]
        check(f"  {town}: row count > 0", n > 0, f"got {n} rows")

        non_null_assessed = duckdb.execute(
            f"SELECT COUNT(*) FROM read_parquet('{parquet_path}') WHERE assessed_value IS NOT NULL"
        ).fetchone()[0]
        check(
            f"  {town}: assessed_value populated",
            non_null_assessed > 0,
            f"{non_null_assessed}/{n} rows have assessed_value",
        )
    except Exception as exc:
        check(f"  {town}: schema check", False, str(exc))


# ---------------------------------------------------------------------------
# 4. DuckDB query smoke-tests  (mimic what the SQL agent would generate)
# ---------------------------------------------------------------------------
print("\n── 4. SQL query smoke-tests (arlington-ma) ──────────────")
ap = gold_dir / "arlington-ma" / "property.parquet"
zp = gold_dir / "arlington-ma" / "zoning.parquet"
ep = gold_dir / "arlington-ma" / "equity-index.parquet"
pp = gold_dir / "arlington-ma" / "permits.parquet"

queries = {
    "Top 5 by assessed_value": f"""
        SELECT parcel_id, address, owner_name, assessed_value
        FROM read_parquet('{ap}')
        WHERE assessed_value IS NOT NULL
        ORDER BY assessed_value DESC
        LIMIT 5
    """,
    "Properties built before 1940": f"""
        SELECT parcel_id, address, year_built, building_type
        FROM read_parquet('{ap}')
        WHERE year_built IS NOT NULL AND year_built < 1940
        LIMIT 10
    """,
    "Distinct zone codes": f"""
        SELECT DISTINCT zone_code
        FROM read_parquet('{ap}')
        WHERE zone_code IS NOT NULL
    """,
    "Zoning districts (zoning.parquet)": f"""
        SELECT zone_code, zone_description, max_height_ft
        FROM read_parquet('{zp}')
        ORDER BY zone_code
    """,
    "Avg permit approval days": f"""
        SELECT ROUND(AVG(
            DATEDIFF('day', CAST(application_date AS DATE), CAST(approval_date AS DATE))
        ), 1) AS avg_days
        FROM read_parquet('{pp}')
        WHERE application_date IS NOT NULL AND approval_date IS NOT NULL
    """,
    "High equity burden tracts": f"""
        SELECT geo_value, burden_score, is_disadvantaged
        FROM read_parquet('{ep}')
        ORDER BY burden_score DESC
        LIMIT 5
    """,
}

for label, sql in queries.items():
    try:
        df = duckdb.execute(sql).df()
        check(f"{label}: returns rows", not df.empty, f"{len(df)} rows")
        if not df.empty:
            print(f"     → {df.shape[0]} row(s), cols: {list(df.columns)}")
    except Exception as exc:
        check(f"{label}", False, str(exc))


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print("\n" + "─" * 55)
if errors:
    print(f"\033[31m{len(errors)} FAILURE(S):\033[0m")
    for e in errors:
        print(f"  • {e}")
    sys.exit(1)
else:
    print("\033[32mAll checks passed.\033[0m")
