import pandas as pd
df = pd.read_parquet("data/gold/arlington-ma/permits.parquet")
record = df[df["metadata"].astype(str).str.contains("BELKNAP", case=False, na=False)]
print(record.to_string())
