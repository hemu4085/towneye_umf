# [FILE PATH]: scrapers/planning_dockets_scraper.py
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
    extracted from a local Planning Board or Zoning Board of Appeals meeting minutes.
    
    Extract every hearing, docket, site plan review, variance, or special permit discussed.
    Return ONLY a JSON array of objects. Do not include markdown formatting.
    
    Each object must have:
    {
      "docket_number": "<e.g., 3816 or null if unnamed>",
      "address": "<e.g., 5-7 Belknap St>",
      "board_name": "<e.g., Arlington Redevelopment Board>",
      "decision_status": "<APPROVED | DENIED | CONTINUED | WITHDRAWN | UNDER_REVIEW>",
      "summary": "<1-2 sentence summary of what was requested and the outcome>"
    }
""").strip()

class ArlingtonDocketsScraper:
    def __init__(
        self,
        town_slug: str,
        config_base_dir: str = "configs",
    ) -> None:
        self._town_slug = town_slug
        
        loader = ConfigLoader(base_dir=config_base_dir)
        self._config = loader.get_town_config(town_slug)
        self._ssl_verify = self._config.get("http", {}).get("ssl_verify", True)
        
        # In production, this would scrape the civic portal for PDF links.
        # We will use a mock/example list for the blueprint.
        self._pdf_urls = [
            # Placeholder for actual Arlington MA meeting minutes PDFs
            # "https://www.arlingtonma.gov/example_minutes_sept_2024.pdf"
        ]

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
        
        user_prompt = f"Extract the dockets from the following meeting text:\n\n{raw_text}"
        
        try:
            # This calls Gemini/Anthropic based on your .env configuration
            raw_json = call_llm(system=_SYSTEM_PROMPT, user=user_prompt, n_tokens=4096)
            
            # Clean up any potential markdown fences returned by the LLM
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
                "address": "5-7 Belknap St",
                "board_name": "Arlington Redevelopment Board",
                "decision_status": "APPROVED",
                "summary": "Site Plan Review approved for construction of a new two-family townhouse."
            },
            {
                "docket_number": "3820",
                "address": "123 Mass Ave",
                "board_name": "Zoning Board of Appeals",
                "decision_status": "CONTINUED",
                "summary": "Request for variance on front setback continued to next meeting."
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
            logger.info("No PDF URLs configured. Using mock docket data for blueprint.")
            all_dockets = self.get_mock_data()
        
        if not all_dockets:
            logger.warning("No dockets extracted.")
            return ""

        # Map to our Universal Identity Graph format
        from datetime import datetime, timezone
        import uuid
        
        now = datetime.now(tz=timezone.utc)
        
        gold_records = []
        for d in all_dockets:
            gold_records.append({
                "te_id": str(uuid.uuid4()),
                "te_source": "arlington-ma-planning-dockets",
                "te_confidence": 0.9,
                "te_timestamp": now,
                "te_version": "1.0.0",
                "te_geo_hash": self._config.get("geo_hash", ""),
                "te_updated_by": "UMF_System",
                "te_event_pk": abs(hash(d.get("docket_number", "") + d.get("address", ""))) % (10 ** 9),
                
                # Payload fields
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
        out_path = save_gold_data(df, self._town_slug, "planning_dockets", output_dir=output_dir)
        logger.info(f"Saved {len(gold_records)} docket records to {out_path}")
        return out_path
