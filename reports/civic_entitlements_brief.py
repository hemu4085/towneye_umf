# [FILE PATH]: reports/civic_entitlements_brief.py
import json
import logging
import pathlib
import pandas as pd
from datetime import date
from typing import Any, Dict, List, Optional
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

class CivicBriefInputs(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    town_slug: str = Field(..., description="Kebab-case town id (e.g. 'arlington-ma').")
    parcel_id: str = Field(..., description="Stable parcel natural key.")
    prepared_on: Optional[date] = Field(None)

class CivicEntitlement(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    event_type: str
    address: str
    docket: Optional[str] = None
    status: str
    board: str
    summary: str

class CivicBriefData(BaseModel):
    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True)
    inputs: CivicBriefInputs
    entitlements: List[CivicEntitlement] = Field(default_factory=list)
    has_entitlements: bool = False

    @property
    def report_date_text(self) -> str:
        d = self.inputs.prepared_on or date.today()
        return d.strftime("%B %-d, %Y") if hasattr(d, "strftime") else str(d)

_TEMPLATE_DIR = pathlib.Path(__file__).resolve().parent / "templates"
_TEMPLATE_NAME = "civic_entitlements_brief.html.j2"

class CivicEntitlementsBriefGenerator:
    def __init__(self, town_slug: str, data_dir: str | pathlib.Path = "data/gold"):
        self.town_slug = town_slug
        self._data_dir = pathlib.Path(data_dir)
        self._jinja_env = Environment(
            loader=FileSystemLoader(_TEMPLATE_DIR),
            autoescape=select_autoescape(["html", "j2"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def generate(self, inputs: CivicBriefInputs) -> str:
        if inputs.town_slug != self.town_slug:
            raise ValueError("Town slug mismatch")
        data = self.collect_data(inputs)
        template = self._jinja_env.get_template(_TEMPLATE_NAME)
        return template.render(d=data)

    def collect_data(self, inputs: CivicBriefInputs) -> CivicBriefData:
        # 1. Fetch property info to get address
        prop_path = self._data_dir / self.town_slug / "property.parquet"
        address = None
        if prop_path.exists():
            df_prop = pd.read_parquet(prop_path)
            hits = df_prop[df_prop["parcel_id"] == inputs.parcel_id]
            if not hits.empty:
                address = str(hits.iloc[0].get("address", "")).upper().strip()

        entitlements = []
        minutes_path = self._data_dir / self.town_slug / "civic_minutes.parquet"
        
        if minutes_path.exists() and address:
            df_min = pd.read_parquet(minutes_path)
            # Find exact or partial address match in civic minutes
            # Civic minutes address format might vary slightly, but we'll use a direct check or contains
            hits = df_min[df_min["address"].astype(str).str.upper().str.contains(address, regex=False, na=False)]
            
            for _, row in hits.iterrows():
                md_str = row.get("metadata", "{}")
                try:
                    md = json.loads(md_str) if isinstance(md_str, str) else md_str
                except Exception:
                    md = {}
                entitlements.append(CivicEntitlement(
                    event_type=str(row.get("event_type", "")),
                    address=str(row.get("address", "")),
                    docket=str(row.get("docket")) if pd.notna(row.get("docket")) else None,
                    status=str(row.get("status", "")),
                    board=str(md.get("board", "")),
                    summary=str(md.get("summary", ""))
                ))

        return CivicBriefData(
            inputs=inputs,
            entitlements=entitlements,
            has_entitlements=len(entitlements) > 0
        )
