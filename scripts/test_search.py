import pandas as pd
import glob
import os

def search_parquets(term):
    for f in glob.glob("data/gold/arlington-ma/*.parquet"):
        try:
            df = pd.read_parquet(f)
            df_str = df.astype(str)
            mask = df_str.apply(lambda x: x.str.contains(term, case=False, na=False)).any(axis=1)
            if mask.any():
                print(f"[{os.path.basename(f)}] matched '{term}' in {mask.sum()} row(s)")
        except Exception as e:
            pass

print("Searching for '3816'...")
search_parquets("3816")
print("\nSearching for 'Docket'...")
search_parquets("Docket")
