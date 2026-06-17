# [FILE PATH]: scrapers/civic_minutes_scraper.py
import json
import logging
import textwrap
import io
import requests
import pandas as pd

from typing import Any, Dict, List, Optional
from core.config_loader import ConfigLoader
from core.llm_client import call_llm
from core.storage import save_gold_data

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

logger = logging.getLogger(__name__)

# The System Prompt is the "Moat"
_SYSTEM_PROMPT = textwrap.dedent("""
    You are a municipal real estate entitlement expert. You are reading raw text 
    extracted from a local civic board meeting minutes (Planning Board, Zoning Board of Appeals,
    Conservation Commission, Historical Commission, Board of Health, etc.).
    
    Extract every hearing, docket, site plan review, variance, wetland approval,
    demolition delay, health permit, or special permit discussed.
    Return ONLY a JSON array of objects. Do not include markdown formatting.
    
    Each object must have:
    {
      "docket_number": "<e.g., 3816, NOI-123, or null if unnamed>",
      "address": "<e.g., 5-7 Belknap St>",
      "board_name": "<e.g., Arlington Redevelopment Board, Conservation Commission>",
      "decision_status": "<APPROVED | DENIED | CONTINUED | WITHDRAWN | UNDER_REVIEW>",
      "summary": "<1-2 sentence summary of what was requested and the outcome>"
    }
""").strip()

class CivicMinutesScraper:
    def __init__(
        self,
        town_slug: str,
        config_base_dir: str = "configs",
    ) -> None:
        self._town_slug = town_slug
        
        loader = ConfigLoader(base_dir=config_base_dir)
        self._config = loader.get_town_config(town_slug)
        self._ssl_verify = self._config.get("http", {}).get("ssl_verify", True)
        
        self._pdf_urls = []

    def fetch_and_parse_pdf(self, url: str) -> str:
        """Download PDF and extract all text."""
        if not pdfplumber:
            logger.warning("pdfplumber not installed. Cannot parse PDFs.")
            return ""
            
        logger.info(f"Downloading minutes from {url}")
        try:
            resp = requests.get(url, timeout=20, verify=self._ssl_verify)
            resp.raise_for_status()
            
            full_text = []
            with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        full_text.append(text)
                        
            return "\n".join(full_text)
        except Exception as e:
            logger.error(f"Failed to fetch or parse {url}: {e}")
            return ""

    def extract_with_llm(self, raw_text: str) -> List[Dict[str, Any]]:
        """Pass the messy PDF text to the LLM for structured extraction."""
        if not raw_text.strip():
            return []
            
        logger.info(f"Sending {len(raw_text)} chars to LLM for extraction...")
        
        user_prompt = f"Extract the civic board decisions from the following meeting text:\n\n{raw_text}"
        
        try:
            raw_json = call_llm(system=_SYSTEM_PROMPT, user=user_prompt, n_tokens=4096)
            clean_json = raw_json.replace("```json", "").replace("```", "").strip()
            return json.loads(clean_json)
        except Exception as e:
            logger.error(f"LLM extraction failed: {e}")
            return []

    def get_mock_data(self) -> List[Dict[str, Any]]:
        """Provide fallback mock data when PDF fetching isn't configured."""
        return [
            {
                "docket_number": "3816",
                "address": "5-7 BELKNAP ST",
                "board_name": "Arlington Redevelopment Board",
                "decision_status": "APPROVED",
                "summary": "Site Plan Review approved for construction of a new two-family townhouse."
            },
            {
                "docket_number": "NOI-998",
                "address": "29 WALNUT ST",
                "board_name": "Conservation Commission",
                "decision_status": "CONTINUED",
                "summary": "Notice of Intent for development near flood zone continued pending updated drainage plan."
            },
            {
                "docket_number": "HIST-2025-04",
                "address": "166 MYSTIC ST",
                "board_name": "Historical Commission",
                "decision_status": "APPROVED",
                "summary": "Imposed 12-month Demolition Delay due to historic significance."
            },
            {
                "docket_number": "BOH-2025-11",
                "address": "123 MASS AVE",
                "board_name": "Board of Health",
                "decision_status": "APPROVED",
                "summary": "Hazardous waste removal permit approved for old commercial site."
            }
        ]

    def run(self, output_dir: str = "data/gold") -> str:
        """Execute the scraper pipeline."""
        all_dockets = []
        
        if self._pdf_urls:
            for url in self._pdf_urls:
                raw_text = self.fetch_and_parse_pdf(url)
                dockets = self.extract_with_llm(raw_text)
                all_dockets.extend(dockets)
        else:
            logger.info("No PDF URLs configured. Using mock civic minutes data for blueprint.")
            all_dockets = self.get_mock_data()
        
        if not all_dockets:
            logger.warning("No civic minutes extracted.")
            return ""

        from datetime import datetime, timezone
        import uuid
        
        now = datetime.now(tz=timezone.utc)
        
        gold_records = []
        for d in all_dockets:
            gold_records.append({
                "te_id": str(uuid.uuid4()),
                "te_source": f"{self._town_slug}-civic-minutes",
                "te_confidence": 0.9,
                "te_timestamp": now,
                "te_version": "1.0.0",
                "te_geo_hash": self._config.get("geo_hash", ""),
                "te_updated_by": "UMF_System",
                "te_event_pk": abs(hash(d.get("docket_number", "") + d.get("address", ""))) % (10 ** 9),
                "event_type": "BOARD_DECISION",
                "address": d.get("address", ""),
                "docket": d.get("docket_number", ""),
                "status": d.get("decision_status", ""),
                "metadata": json.dumps({
                    "board": d.get("board_name", ""),
                    "summary": d.get("summary", "")
                })
            })
            
        df = pd.DataFrame(gold_records)
        out_path = save_gold_data(df, self._town_slug, "civic_minutes", output_dir=output_dir)
        logger.info(f"Saved {len(gold_records)} civic minutes records to {out_path}")
        return out_path
