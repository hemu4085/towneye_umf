# [FILE PATH]: scrapers/str_ingestor.py
# Patch #185 (migrated from arlington_ma_str.py)
# Domain 12: STR Dynamics (LLM Synthesis)

import json
import logging
import pathlib
import re
import sys
import textwrap
import time
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core.config_loader import ConfigLoader
from core.factory import MedallionFactory
from core.identity_linker import get_linker
from core.llm_client import call_llm, select_provider
from core.storage import save_gold_data

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = textwrap.dedent("""
    You are a short-term rental (STR) market analyst helping TownEye model
    Airbnb / VRBO dynamics for US municipalities.

    Your task: produce a structured JSON snapshot of the STR market for the
    specified municipality in the specified month.

    Return ONLY a single JSON object (no markdown fences, no explanation)
    with exactly these fields:

    {{
      "estimated_yield_pct":   <float>,
      "avg_nightly_rate_usd":  <float>,
      "occupancy_rate_pct":    <float>,
      "target_guest_demo":     "<WEEKEND_TRIPPER|REMOTE_WORKER|FAMILY_VACATION|SNOWBIRD|MIXED>",
      "regulatory_posture":    "<PERMISSIVE|MODERATE|RESTRICTIVE|BANNED>",
      "peak_seasons":          ["<season>", ...],
      "active_listings_est":   <int>,
      "yoy_yield_change_pct":  <float>,
      "sweet_spot_neighborhoods": ["<neighbourhood>", ...],
      "regulatory_notes":      "<1-2 sentences>",
      "summary":               "<one sentence executive summary>"
    }}

    Return ONLY the JSON object. No other text.
""").strip()

_USER_PROMPT_TEMPLATE = (
    "Generate a short-term rental market snapshot for {town_name}, {state} "
    "for the month of {observation_month}."
)

_MOCK_STR_KEY = "str_dynamics_mock_data"


class ArlingtonStrDynamicsIngestor:
    """Town-agnostic STR Dynamics ingestor (Domain 12)."""

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
            "str_dynamics", f"{town_slug}-str-dynamics"
        )

    def _fetch_str_from_llm(self, observation_month: str) -> Dict[str, Any]:
        town_name = self._cfg.get("town_name", self._town_slug)
        state     = self._cfg.get("state", "")
        prompt = _USER_PROMPT_TEMPLATE.format(
            town_name=town_name, state=state, observation_month=observation_month,
        )
        prompt_hash = sha256((_SYSTEM_PROMPT + prompt).encode()).hexdigest()

        try:
            effective_provider = self._provider or select_provider()
        except RuntimeError:
            effective_provider = None

        if effective_provider is None:
            return self._load_mock_str(prompt_hash, observation_month)

        try:
            t0  = time.perf_counter()
            raw = call_llm(system=_SYSTEM_PROMPT, user=prompt, provider=effective_provider, model=self._model)
            logger.info("ArlingtonStrDynamicsIngestor | LLM responded in %.2fs", time.perf_counter() - t0)
        except Exception as exc:
            logger.warning("ArlingtonStrDynamicsIngestor | LLM failed (%s). Using mock.", exc)
            return self._load_mock_str(prompt_hash, observation_month)

        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return self._load_mock_str(prompt_hash, observation_month)

        parsed["_prompt_hash"]       = prompt_hash
        parsed["_llm_provider"]      = effective_provider
        parsed["_observation_month"] = observation_month
        return parsed

    def _load_mock_str(self, prompt_hash: str, observation_month: str) -> Dict[str, Any]:
        fixture = self._cfg.get(_MOCK_STR_KEY)
        if fixture:
            fixture.setdefault("_prompt_hash", prompt_hash)
            fixture.setdefault("_llm_provider", "mock")
            fixture.setdefault("_observation_month", observation_month)
            return fixture
        town_name = self._cfg.get("town_name", self._town_slug)
        state     = self._cfg.get("state", "")
        return {
            "estimated_yield_pct":       6.5,
            "avg_nightly_rate_usd":      185.0,
            "occupancy_rate_pct":        62.0,
            "target_guest_demo":         "MIXED",
            "regulatory_posture":        "MODERATE",
            "peak_seasons":              ["SUMMER", "FALL"],
            "active_listings_est":       80,
            "yoy_yield_change_pct":      1.2,
            "sweet_spot_neighborhoods":  ["[Mock] Downtown"],
            "regulatory_notes":          f"[Mock] {town_name}, {state} STR regulations not yet loaded.",
            "summary":                   f"[Mock] {town_name} STR stub -- set an LLM API key.",
            "_prompt_hash":              prompt_hash,
            "_llm_provider":             "mock",
            "_observation_month":        observation_month,
        }

    def _build_bronze(self, snapshot: Dict[str, Any], observation_month: str) -> Dict[str, Any]:
        source_id  = f"{self._town_slug}:str-dynamics:{observation_month}"
        te_str_pk  = self._linker.resolve(self._source_key, source_id)
        llm_model  = snapshot.get("_llm_provider", "unknown")
        return {
            "te_str_pk":            te_str_pk,
            "observation_month":    observation_month,
            "estimated_yield_pct":  float(snapshot.get("estimated_yield_pct", 0.0)),
            "avg_nightly_rate_usd": float(snapshot.get("avg_nightly_rate_usd", 0.0)),
            "occupancy_rate_pct":   float(snapshot.get("occupancy_rate_pct", 0.0)),
            "target_guest_demo":    str(snapshot.get("target_guest_demo", "MIXED")),
            "regulatory_posture":   str(snapshot.get("regulatory_posture", "MODERATE")),
            "peak_seasons":         list(snapshot.get("peak_seasons", [])),
            "llm_model":            str(llm_model),
            "metadata": {
                "active_listings_est":      snapshot.get("active_listings_est"),
                "yoy_yield_change_pct":     snapshot.get("yoy_yield_change_pct"),
                "sweet_spot_neighborhoods": snapshot.get("sweet_spot_neighborhoods", []),
                "regulatory_notes":         snapshot.get("regulatory_notes", ""),
                "summary":                  snapshot.get("summary", ""),
                "generation_prompt_hash":   snapshot.get("_prompt_hash"),
                "source_dataset":           self._source_key,
            },
        }

    def run(self, observation_month: Optional[str] = None, output_dir: str = "data/gold") -> pathlib.Path:
        import pandas as pd

        if observation_month is None:
            observation_month = datetime.now(tz=timezone.utc).strftime("%Y-%m")

        snapshot_raw = self._fetch_str_from_llm(observation_month)
        bronze       = self._build_bronze(snapshot_raw, observation_month)
        gold         = self._factory.map_to_str_dynamics(bronze)

        df = pd.DataFrame([gold])
        for col in ("peak_seasons", "metadata"):
            if col in df.columns:
                df[col] = df[col].apply(lambda v: json.dumps(v) if not isinstance(v, str) else v)

        out_path = save_gold_data(df, self._town_slug, "str-dynamics", output_dir=output_dir)
        logger.info("ArlingtonStrDynamicsIngestor | Wrote 1 Gold record -> %s", out_path)
        return out_path
