# [FILE PATH]: scrapers/town_profile_ingestor.py
# Patch #185 (migrated from arlington_ma_town_profile.py)
# Domain 11: Town Profile (LLM Synthesis)

import json
import logging
import pathlib
import re
import sys
import textwrap
import time
from hashlib import sha256
from typing import Any, Dict, Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core.config_loader import ConfigLoader
from core.factory import MedallionFactory
from core.identity_linker import get_linker
from core.llm_client import call_llm, select_provider
from core.storage import save_gold_data

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = textwrap.dedent("""
    You are a senior urban-analytics consultant helping TownEye build its
    civic-intelligence platform.

    Your task: synthesise a structured JSON profile for the specified US
    municipality based on your knowledge of its character, demographics,
    housing stock, politics, and local economy.

    Return ONLY a single JSON object (no markdown fences, no explanation)
    with exactly these fields:

    {{
      "neighborhood_vibes":  "<2-4 sentence narrative>",
      "major_employers":     ["<employer 1>", ...],
      "nimby_index":         <float 0.0-10.0>,
      "housing_character":   "<OWNER_DOMINATED|MIXED_TENURE|RENTER_MAJORITY>",
      "political_lean":      "<PROGRESSIVE|MODERATE|CONSERVATIVE|MIXED>",
      "walkability_score":   <int 0-100>,
      "transit_score":       <int 0-100>,
      "school_rating":       <float 1.0-10.0>,
      "sweet_spots":         ["<neighbourhood>", ...],
      "risks":               ["<risk>", ...],
      "summary":             "<one sentence executive summary>"
    }}

    Return ONLY the JSON object. No other text.
""").strip()

_USER_PROMPT_TEMPLATE = "Synthesise a town profile for {town_name}, {state}."
_MOCK_PROFILE_KEY = "town_profile_mock_data"


class ArlingtonTownProfileIngestor:
    """Town-agnostic Town Profile ingestor (Domain 11)."""

    def __init__(
        self,
        town_slug: str = "arlington-ma",
        linker=None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        self._town_slug = town_slug
        self._factory   = MedallionFactory(town_slug=town_slug)
        self._cfg        = ConfigLoader(town_slug=town_slug).load()
        self._linker     = linker or get_linker()
        self._provider   = provider
        self._model      = model
        self._source_key = self._cfg.get("source_mappings", {}).get(
            "town_profile", f"{town_slug}-town-profile"
        )

    def _fetch_profile_from_llm(self) -> Dict[str, Any]:
        town_name = self._cfg.get("town_name", self._town_slug)
        state     = self._cfg.get("state", "")
        prompt = _USER_PROMPT_TEMPLATE.format(town_name=town_name, state=state)
        prompt_hash = sha256((_SYSTEM_PROMPT + prompt).encode()).hexdigest()

        try:
            effective_provider = self._provider or select_provider()
        except RuntimeError:
            effective_provider = None

        if effective_provider is None:
            return self._load_mock_profile(prompt_hash)

        try:
            t0  = time.perf_counter()
            raw = call_llm(system=_SYSTEM_PROMPT, user=prompt, provider=effective_provider, model=self._model)
            logger.info("ArlingtonTownProfileIngestor | LLM responded in %.2fs", time.perf_counter() - t0)
        except Exception as exc:
            logger.warning("ArlingtonTownProfileIngestor | LLM failed (%s). Using mock.", exc)
            return self._load_mock_profile(prompt_hash)

        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return self._load_mock_profile(prompt_hash)

        parsed["_prompt_hash"] = prompt_hash
        parsed["_llm_provider"] = effective_provider
        return parsed

    def _load_mock_profile(self, prompt_hash: str) -> Dict[str, Any]:
        fixture = self._cfg.get(_MOCK_PROFILE_KEY)
        if fixture:
            fixture.setdefault("_prompt_hash", prompt_hash)
            fixture.setdefault("_llm_provider", "mock")
            return fixture
        town_name = self._cfg.get("town_name", self._town_slug)
        state     = self._cfg.get("state", "")
        return {
            "neighborhood_vibes":  f"[Mock] {town_name}, {state} profile not yet generated.",
            "major_employers":     ["[Mock] Employer A"],
            "nimby_index":         5.0,
            "housing_character":   "MIXED_TENURE",
            "political_lean":      "MODERATE",
            "walkability_score":   50,
            "transit_score":       50,
            "school_rating":       7.0,
            "sweet_spots":         ["[Mock] Downtown"],
            "risks":               ["[Mock] No live data"],
            "summary":             f"[Mock] {town_name} stub -- set an LLM API key.",
            "_prompt_hash":        prompt_hash,
            "_llm_provider":       "mock",
        }

    def _build_bronze(self, profile: Dict[str, Any], source_id: str) -> Dict[str, Any]:
        te_profile_pk = self._linker.resolve(self._source_key, source_id)
        return {
            "te_profile_pk":          te_profile_pk,
            "profile_type":           "FULL",
            "town_name":              self._cfg.get("town_name", self._town_slug),
            "state":                  self._cfg.get("state", ""),
            "neighborhood_vibes":     profile.get("neighborhood_vibes", ""),
            "major_employers":        profile.get("major_employers", []),
            "nimby_index":            float(profile.get("nimby_index", 5.0)),
            "housing_character":      profile.get("housing_character", "MIXED_TENURE"),
            "political_lean":         profile.get("political_lean", "MODERATE"),
            "llm_model":              str(profile.get("_llm_provider", "unknown")),
            "generation_prompt_hash": profile.get("_prompt_hash"),
            "metadata": {
                "walkability_score": profile.get("walkability_score"),
                "transit_score":     profile.get("transit_score"),
                "school_rating":     profile.get("school_rating"),
                "sweet_spots":       profile.get("sweet_spots", []),
                "risks":             profile.get("risks", []),
                "summary":           profile.get("summary", ""),
                "source_dataset":    self._source_key,
            },
        }

    def run(self, output_dir: str = "data/gold") -> pathlib.Path:
        import pandas as pd

        profile_raw = self._fetch_profile_from_llm()
        source_id = f"{self._town_slug}:town-profile:FULL"
        bronze    = self._build_bronze(profile_raw, source_id)
        gold      = self._factory.map_to_town_profile(bronze)

        df = pd.DataFrame([gold])
        for col in ("major_employers", "metadata"):
            if col in df.columns:
                df[col] = df[col].apply(lambda v: json.dumps(v) if not isinstance(v, str) else v)

        out_path = save_gold_data(df, self._town_slug, "town-profile", output_dir=output_dir)
        logger.info("ArlingtonTownProfileIngestor | Wrote 1 Gold record -> %s", out_path)
        return out_path
