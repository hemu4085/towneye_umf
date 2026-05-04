# [FILE PATH]: scrapers/equity_ingestor.py
# Patch #185 (migrated from arlington_ma_equity.py)
# Patch #194 (2025-02-05: EPA removed ejscreen.epa.gov — switch to local CSV cache)
"""
ArlingtonEquityIngestor -- Domain 10: Social Equity / EJScreen Burden Indices.

Data source priority:
  1. Local cached Parquet: data/bronze/ejscreen/ma_block_groups.parquet
     (populated by scripts/download_ejscreen_csv.py from gaftp.epa.gov)
  2. Synthetic fallback when cache is absent.

NOTE: The ejscreen.epa.gov ArcGIS REST API was permanently taken offline on
2025-02-05 by the Trump administration.  The domain no longer resolves in DNS.
The live-API path in fetch_from_ejscreen_api() is retained as dead-letter code
in case EPA reinstates the service, but it will never succeed until then.
"""

import sys
import pathlib

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import json as _json
import logging
import random
from typing import Any, Dict, List, Optional

import pandas as pd

from core.config_loader import ConfigLoader
from core.factory import MedallionFactory
from core.identity_linker import PartyLinker, get_linker
from core.storage import get_parquet_path, save_gold_data

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT_S: int = 30
_GEO_LEVEL = "CENSUS_TRACT"

# Path to the pre-downloaded EJScreen MA block-group cache.
# Run `python scripts/download_ejscreen_csv.py` to populate it.
_EJSCREEN_CACHE_PATH = _PROJECT_ROOT / "data" / "bronze" / "ejscreen" / "ma_block_groups.parquet"


class ArlingtonEquityIngestor:

    def __init__(
        self,
        town_slug: str,
        config_base_dir: str = "configs",
        linker: Optional[PartyLinker] = None,
        factory: Optional[MedallionFactory] = None,
    ) -> None:
        loader = ConfigLoader(base_dir=config_base_dir)
        self._config: Dict[str, Any] = loader.get_town_config(town_slug)

        self._town_slug: str = self._config["town_slug"]
        self._geo_hash: str = self._config.get("geo_hash", "")
        self._te_source: str = self._config["source_mappings"]["social_equity"]
        self._api_url: str = self._config["scraper_urls"]["ejscreen_api"]

        self._tracts: List[str] = self._config.get("equity_census_tracts", [])
        self._indicators: Dict[str, Dict[str, float]] = self._config.get("equity_indicators", {})
        self._threshold: float = float(self._config.get("equity_disadvantaged_threshold", 65.0))
        self._index_names: List[str] = self._config.get("equity_index_names", ["EPA_EJSCREEN"])
        self._random_seed: int = int(self._config.get("equity_random_seed", 42))

        _ssl_verify: bool = self._config.get("http", {}).get("ssl_verify", True)
        if not _ssl_verify:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self._ssl_verify = _ssl_verify

        self._factory: MedallionFactory = factory or MedallionFactory(town_slug, config_base_dir)
        self._linker: Optional[PartyLinker] = linker

    def _generate_synthetic_bronze(self) -> pd.DataFrame:
        rng = random.Random(self._random_seed)
        rows: List[Dict[str, Any]] = []
        # Fall back to the town slug as a single census tract when none are configured
        tracts = self._tracts if self._tracts else [self._town_slug]
        for tract in tracts:
            row: Dict[str, Any] = {"census_tract": tract}
            indicator_scores: List[float] = []
            for indicator, params in self._indicators.items():
                mean = float(params.get("mean", 50.0))
                std  = float(params.get("std", 10.0))
                score = max(0.0, min(100.0, rng.gauss(mean, std)))
                row[indicator] = round(score, 2)
                indicator_scores.append(score)
            composite = round(sum(indicator_scores) / len(indicator_scores), 2) if indicator_scores else 0.0
            row["burden_score"] = composite
            row["is_disadvantaged"] = composite >= self._threshold
            rows.append(row)
        return pd.DataFrame(rows)

    def fetch_from_ejscreen_cache(self) -> Optional[pd.DataFrame]:
        """
        Load environmental justice data from the local Parquet cache, filtered
        to only the census tracts configured for this town.

        The cache is built by `scripts/download_ejscreen_csv.py` from the
        CDC EJI 2024 dataset (preserved on Zenodo by EDGI).

        Column mapping from CDC EJI → internal schema:
            GEOID      → census_tract   (11-char census tract FIPS)
            RPL_EJI    → burden_score   (0–1 percentile rank, scaled to 0–100)
        """
        if not _EJSCREEN_CACHE_PATH.exists():
            logger.warning(
                "ArlingtonEquityIngestor | EJ cache not found at %s. "
                "Run `python scripts/download_ejscreen_csv.py` to build it.",
                _EJSCREEN_CACHE_PATH,
            )
            return None

        try:
            df_all = pd.read_parquet(_EJSCREEN_CACHE_PATH)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "ArlingtonEquityIngestor | Failed to read EJ cache: %s", exc
            )
            return None

        # Identify the GEOID column
        id_col = next((c for c in ("GEOID", "ID", "FIPS") if c in df_all.columns), None)
        if id_col is None:
            logger.warning(
                "ArlingtonEquityIngestor | EJ cache has no GEOID/ID column. "
                "Available columns: %s",
                list(df_all.columns[:20]),
            )
            return None

        if not self._tracts:
            logger.warning(
                "ArlingtonEquityIngestor | No equity_census_tracts configured for '%s'.",
                self._town_slug,
            )
            return None

        # CDC EJI uses 11-digit census tract GEOIDs — match exactly or by prefix
        mask = df_all[id_col].astype(str).str.strip().apply(
            lambda geoid: any(
                geoid == t or geoid.startswith(t) for t in self._tracts
            )
        )
        df = df_all[mask].copy()

        if df.empty:
            logger.warning(
                "ArlingtonEquityIngestor | EJ cache returned 0 rows for '%s' "
                "(tracts: %s). Cache has %d MA rows total.",
                self._town_slug, self._tracts[:4], len(df_all),
            )
            return None

        # Normalise GEOID → census_tract
        if "census_tract" not in df.columns:
            df["census_tract"] = df[id_col].astype(str).str.strip()

        # Derive burden_score from RPL_EJI (0–1 percentile rank → 0–100 scale)
        if "burden_score" not in df.columns:
            if "RPL_EJI" in df.columns:
                rpl = pd.to_numeric(df["RPL_EJI"], errors="coerce")
                # -999 is CDC EJI's null sentinel
                rpl = rpl.where(rpl >= 0, other=float("nan"))
                df["burden_score"] = (rpl * 100).round(2)
                logger.info(
                    "ArlingtonEquityIngestor | burden_score derived from RPL_EJI for '%s'.",
                    self._town_slug,
                )
            else:
                # Fallback: average all EPL_* percentile columns (already 0–1)
                epl_cols = [c for c in df.columns if c.startswith("EPL_")]
                if epl_cols:
                    df["burden_score"] = (
                        df[epl_cols]
                        .apply(pd.to_numeric, errors="coerce")
                        .replace(-999, float("nan"))
                        .mean(axis=1)
                        .mul(100)
                        .round(2)
                    )
                    logger.info(
                        "ArlingtonEquityIngestor | burden_score averaged from %d EPL_ columns.",
                        len(epl_cols),
                    )
                else:
                    df["burden_score"] = 50.0

        logger.info(
            "ArlingtonEquityIngestor | EJ cache: %d tracts matched for '%s' "
            "(burden_score range: %.1f – %.1f).",
            len(df),
            self._town_slug,
            df["burden_score"].min() if "burden_score" in df.columns else 0,
            df["burden_score"].max() if "burden_score" in df.columns else 0,
        )
        return df

    def fetch_from_ejscreen_api(self) -> Optional[pd.DataFrame]:
        """
        DEAD-LETTER: The ejscreen.epa.gov ArcGIS REST API was permanently taken
        offline on 2025-02-05.  This method is kept for the day EPA reinstates
        the service, but will always fail with NXDOMAIN until then.
        """
        try:
            import requests
        except ImportError:
            return None

        # ID is a STRING field (length 12) in ArcGIS — must be quoted.
        tract_list = ", ".join(f"'{t}'" for t in self._tracts)
        params: Dict[str, Any] = {
            "where":          f"ID IN ({tract_list})",
            "outFields":      "*",
            "f":              "json",
            "returnGeometry": "false",
        }
        try:
            resp = requests.get(
                self._api_url, params=params,
                timeout=_REQUEST_TIMEOUT_S, verify=self._ssl_verify,
            )
            resp.raise_for_status()
            payload = resp.json()
            logger.debug(
                "ArlingtonEquityIngestor | EJScreen raw response keys=%s | "
                "error=%s | feature_count=%s | url=%s",
                list(payload.keys()),
                payload.get("error"),
                len(payload.get("features", [])),
                resp.url,
            )
            features = payload.get("features", [])
            if not features:
                logger.warning(
                    "ArlingtonEquityIngestor | EJScreen API returned 0 features for '%s'. "
                    "Status: %s | Response keys: %s | error: %s | url: %s",
                    self._town_slug,
                    resp.status_code,
                    list(payload.keys()),
                    payload.get("error"),
                    resp.url,
                )
                return None
            df = pd.DataFrame([f["attributes"] for f in features])
            logger.info(
                "ArlingtonEquityIngestor | EJScreen API returned %d features for '%s'. Columns: %s",
                len(df), self._town_slug, list(df.columns),
            )
            return df
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "ArlingtonEquityIngestor | EJScreen API request failed for '%s': %s",
                self._town_slug,
                exc,
            )
            return None

    def fetch_bronze(self, bronze_dir: str = "data/bronze") -> pd.DataFrame:
        # Priority 1: local CSV cache (CDC EJI 2024 from Zenodo, built by download_ejscreen_csv.py)
        df = self.fetch_from_ejscreen_cache()
        # Priority 2: live API (dead since 2025-02-05, kept for future use)
        if df is None or df.empty:
            df = self.fetch_from_ejscreen_api()
        # Priority 3: synthetic
        if df is None or df.empty:
            df = self._generate_synthetic_bronze()
        else:
            # Normalise the GEOID/ID column to census_tract for _build_bronze_records.
            # EJScreen 2.22 CSV uses "ID" (12-char block-group GEOID).
            # The old API also used "ID"; some versions use "GEOID".
            id_col = next((c for c in ("ID", "GEOID", "FIPS") if c in df.columns), None)
            if id_col and "census_tract" not in df.columns:
                df["census_tract"] = df[id_col].astype(str).str.strip()

            # EJScreen percentile columns (P_LWINCPCT, P_MINORPCT, etc.) map
            # to our indicator names where configured.  If the config indicators
            # don't match the API columns, compute burden_score from whatever
            # numeric percentile columns are present (P_* prefix).
            if "burden_score" not in df.columns:
                ejscreen_pct_cols = [c for c in df.columns if c.startswith("P_") and df[c].dtype in ("float64", "int64")]
                config_cols = [c for c in df.columns if c in self._indicators]
                score_cols = config_cols if config_cols else ejscreen_pct_cols
                if score_cols:
                    df["burden_score"] = (
                        df[score_cols]
                        .apply(pd.to_numeric, errors="coerce")
                        .mean(axis=1)
                        .round(2)
                    )
                    logger.info(
                        "ArlingtonEquityIngestor | burden_score computed from %d EJScreen columns: %s",
                        len(score_cols), score_cols[:6],
                    )
                else:
                    df["burden_score"] = 50.0

        if "burden_score" not in df.columns:
            df["burden_score"] = 50.0

        if "is_disadvantaged" not in df.columns:
            df["is_disadvantaged"] = df["burden_score"] >= self._threshold

        bronze_path = get_parquet_path("bronze", self._town_slug, "equity-bronze")
        df.to_parquet(bronze_path, index=False, engine="pyarrow")
        return pd.read_parquet(bronze_path)

    def _build_bronze_records(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []
        indicator_cols = [c for c in df.columns if c in self._indicators]
        for _, row in df.iterrows():
            geo_value = str(row.get("census_tract", row.get("GEOID", ""))).strip()
            if not geo_value:
                continue
            burden = float(row.get("burden_score", 50.0))
            is_disadv = bool(row.get("is_disadvantaged", burden >= self._threshold))
            indicator_breakdown: Dict[str, float] = {
                col: round(float(row[col]), 2) for col in indicator_cols if pd.notna(row.get(col))
            }
            for index_name in self._index_names:
                is_disadv_for_index = burden >= (self._threshold - 5.0 if index_name == "MASS_EJ" else self._threshold)
                records.append({
                    "source_id":       f"{index_name}:{geo_value}",
                    "geo_level":       _GEO_LEVEL,
                    "geo_value":       geo_value,
                    "index_name":      index_name,
                    "burden_score":    burden,
                    "is_disadvantaged": is_disadv_for_index,
                    "metadata": {
                        "indicators":                 indicator_breakdown,
                        "disadvantaged_threshold":    self._threshold - 5.0 if index_name == "MASS_EJ" else self._threshold,
                        "reference_year":             2024,
                        "source_dataset":             self._te_source,
                    },
                    "te_source":   self._te_source,
                    "te_geo_hash": self._geo_hash,
                })
        return records

    def _promote_to_gold(self, bronze: Dict[str, Any], linker: PartyLinker) -> Dict[str, Any]:
        te_equity_pk: int = linker.resolve(self._te_source, bronze["source_id"])
        raw_for_factory: Dict[str, Any] = {
            "te_equity_pk":    te_equity_pk,
            "geo_level":       bronze["geo_level"],
            "geo_value":       bronze["geo_value"],
            "index_name":      bronze["index_name"],
            "burden_score":    bronze["burden_score"],
            "is_disadvantaged": bronze["is_disadvantaged"],
            "metadata":        bronze.get("metadata", {}),
            "te_source":       self._te_source,
            "te_geo_hash":     self._geo_hash,
        }
        return self._factory.map_to_equity_index(raw_for_factory)

    def run(self, bronze_dir: str = "data/bronze", output_dir: str = "data/gold") -> pathlib.Path:
        df_bronze = self.fetch_bronze(bronze_dir)
        bronze_records = self._build_bronze_records(df_bronze)

        if not bronze_records:
            raise ValueError(f"ArlingtonEquityIngestor | 0 Bronze records for '{self._town_slug}'.")

        effective_linker = self._linker or get_linker()
        gold_records = [self._promote_to_gold(b, effective_linker) for b in bronze_records]

        df_gold = pd.DataFrame(gold_records)
        df_gold["metadata"] = df_gold["metadata"].apply(_json.dumps)

        out_path = save_gold_data(df_gold, self._town_slug, "equity-index", output_dir=output_dir)
        logger.info("ArlingtonEquityIngestor | Wrote %d Gold records -> %s", len(gold_records), out_path)
        return out_path
