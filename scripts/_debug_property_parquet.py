# [FILE PATH]: scripts/_debug_property_parquet.py
"""Quick inspector for property.parquet schema + a known parcel (29 Walnut)."""
import pandas as pd

for slug in ["arlington-ma", "lexington-ma"]:
    print(f"=== {slug} ===")
    df = pd.read_parquet(f"data/gold/{slug}/property.parquet")
    print("rows:", len(df))
    print("cols:", list(df.columns))
    if slug == "arlington-ma":
        m = df[df["parcel_id"] == "128.0-0003-0012.0"]
        if not m.empty:
            print("29 Walnut:")
            print(m.iloc[0].to_dict())
    print()
    sample = df.sample(n=2, random_state=42)
    for _, r in sample.iterrows():
        print(f"sample {r.get('parcel_id')}: address={r.get('address')!r}  owner_name={r.get('owner_name')!r}")
    print()
