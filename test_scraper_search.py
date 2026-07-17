import os
import glob

print("Checking existing scrapers for PDF or LLM extraction logic...")
for f in glob.glob("scrapers/**/*.py", recursive=True):
    with open(f, "r") as file:
        content = file.read()
        if "pdf" in content.lower() or "agenda" in content.lower() or "minutes" in content.lower():
            print(f"File: {f}")
