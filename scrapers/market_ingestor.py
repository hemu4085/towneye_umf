# [FILE PATH]: scrapers/market_ingestor.py
# Patch #185 (migrated from arlington_ma_market.py)
"""
ArlingtonMarketIngestor -- Domain 03: Market Dynamics / MLS Trends.
Generates synthetic or BigQuery-sourced market trend data for any town.
"""

import sys
import pathlib

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import logging
import random
from calendar import monthrange
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd

from core.config_loader import ConfigLoader
from core.factory import MedallionFactory
from core.identity_linker import PartyLinker, get_linker
from core.storage import save_gold_data

logger = logging.getLogger(__name__)


class ArlingtonMarketIngestor:

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
        self._te_source: str = self._config["source_mappings"]["market_dynamics"]

        md: Dict[str, Any] = self._config.get("market_dynamics", {})
        self._zip_codes: List[str] = md.get("zip_codes", [])
        self._geo_level: str = md.get("geo_level", "ZIPCODE")
        self._metrics: Dict[str, Dict[str, float]] = md.get("metrics", {})
        self._history_months: int = int(md.get("history_months", 12))
        self._random_seed: int = int(md.get("random_seed", 0))

        self._factory: MedallionFactory = factory or MedallionFactory(town_slug, config_base_dir)
        self._linker: Optional[PartyLinker] = linker

    def generate_synthetic_bronze(self) -> List[Dict[str, Any]]:
        rng = random.Random(self._random_seed)
        records: List[Dict[str, Any]] = []

        now = datetime.now(tz=timezone.utc)
        month_ends: List[datetime] = []
        year, month = now.year, now.month
        for _ in range(self._history_months):
            last_day = monthrange(year, month)[1]
            month_ends.append(datetime(year, month, last_day, 23, 59, 59, tzinfo=timezone.utc))
            month -= 1
            if month == 0:
                month, year = 12, year - 1
        month_ends.reverse()

        # Fall back to the town slug as a single geographic unit when no zip codes configured
        zip_codes = self._zip_codes if self._zip_codes else [self._town_slug]

        for zip_code in zip_codes:
            for metric_name, cfg in self._metrics.items():
                baseline: float = float(cfg["baseline"])
                drift: float = float(cfg["monthly_drift"])
                noise_sigma: float = baseline * 0.01

                value = baseline
                for obs_date in month_ends:
                    value = value * (1 + drift) + rng.gauss(0, noise_sigma)
                    value = max(0.0, value)
                    records.append({
                        "metric_name":      metric_name,
                        "metric_value":     round(value, 2),
                        "observation_date": obs_date,
                        "geo_level":        self._geo_level,
                        "geo_value":        zip_code,
                        "te_source":        self._te_source,
                        "te_geo_hash":      self._geo_hash,
                    })

        return records

    def _fetch_zillow_cache_bronze(self) -> List[Dict[str, Any]]:
        """Read the pre-built Zillow ZHVI cache CSV (if present).

        The cache is created by running:
            python scripts/download_zillow_cache.py --town <slug>

        Cache location: data/cache/{town_slug}/zillow_zhvi.csv
        Columns: zip_code, observation_date, median_home_value
        """
        import csv as _csv
        from datetime import timezone as _tz

        cache_path = (
            pathlib.Path(__file__).resolve().parent.parent
            / "data" / "cache" / self._town_slug / "zillow_zhvi.csv"
        )
        if not cache_path.exists():
            return []

        records: List[Dict[str, Any]] = []
        try:
            with open(cache_path, newline="", encoding="utf-8") as fh:
                reader = _csv.DictReader(fh)
                for row in reader:
                    try:
                        obs_date = datetime.fromisoformat(row["observation_date"] + "T00:00:00+00:00")
                        records.append({
                            "metric_name":      "MEDIAN_SALE_PRICE",
                            "metric_value":     float(row["median_home_value"]),
                            "observation_date": obs_date,
                            "geo_level":        self._geo_level,
                            "geo_value":        row["zip_code"],
                            "te_source":        "zillow-zhvi",
                            "te_geo_hash":      self._geo_hash,
                        })
                    except (ValueError, KeyError):
                        continue
            logger.info(
                "ArlingtonMarketIngestor | Zillow cache: %d rows for '%s'.",
                len(records), self._town_slug,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "ArlingtonMarketIngestor | Could not read Zillow cache for '%s': %s",
                self._town_slug, exc,
            )
        return records

    def fetch_bronze(self) -> List[Dict[str, Any]]:
        """Priority: BigQuery → Zillow ZHVI cache → synthetic.

        BQ config keys read from town config (all optional — absence triggers
        Zillow / synthetic fallback without error):
          market_dynamics.bigquery_dataset  : BQ dataset name (e.g. "market_dynamics")
          market_dynamics.bigquery_table    : BQ table name   (e.g. "mls_trends")
          market_dynamics.bigquery_project  : GCP project     (defaults to env/ADC project)
        """
        import os

        md_cfg = self._config.get("market_dynamics", {})
        bq_dataset = md_cfg.get("bigquery_dataset", "")
        bq_table   = md_cfg.get("bigquery_table", "")
        bq_project = md_cfg.get("bigquery_project", "")

        if not bq_dataset or not bq_table:
            logger.info(
                "ArlingtonMarketIngestor | No BQ table configured for '%s' "
                "(set market_dynamics.bigquery_dataset + bigquery_table in config). "
                "Trying Zillow cache next.",
                self._town_slug,
            )
            zillow = self._fetch_zillow_cache_bronze()
            if zillow:
                return zillow
            logger.info(
                "ArlingtonMarketIngestor | No Zillow cache for '%s'. "
                "Run: python scripts/download_zillow_cache.py --town %s  "
                "Falling back to synthetic data.",
                self._town_slug, self._town_slug,
            )
            return self.generate_synthetic_bronze()

        if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
            logger.warning(
                "ArlingtonMarketIngestor | GOOGLE_APPLICATION_CREDENTIALS not set for '%s'. "
                "Trying Zillow cache next.",
                self._town_slug,
            )
            zillow = self._fetch_zillow_cache_bronze()
            if zillow:
                return zillow
            logger.info(
                "ArlingtonMarketIngestor | No Zillow cache for '%s'. "
                "Run: python scripts/download_zillow_cache.py --town %s  "
                "Falling back to synthetic data.",
                self._town_slug, self._town_slug,
            )
            return self.generate_synthetic_bronze()

        try:
            from google.cloud import bigquery  # type: ignore[import]
        except ImportError:
            logger.warning(
                "ArlingtonMarketIngestor | google-cloud-bigquery not installed for '%s'. "
                "Using synthetic data.",
                self._town_slug,
            )
            return self.generate_synthetic_bronze()

        try:
            client = bigquery.Client(project=bq_project or None)
            full_table = f"{client.project}.{bq_dataset}.{bq_table}"
            zip_placeholders = ", ".join(f"'{z}'" for z in self._zip_codes) if self._zip_codes else "''"

            # The mls_trends table stores one row per (zipcode, period_begin)
            # with one column per metric.  We unpivot it here into the
            # (metric_name, metric_value, observation_date, geo_level, geo_value)
            # shape that _promote_to_gold() expects — keeping the rest of the
            # pipeline unchanged regardless of whether data is real or synthetic.
            query = f"""
                SELECT metric_name, metric_value, period_begin AS observation_date,
                       'ZIPCODE' AS geo_level, zipcode AS geo_value
                FROM `{full_table}`
                UNPIVOT (metric_value FOR metric_name IN (
                    median_sale_price  AS 'MEDIAN_SALE_PRICE',
                    median_list_price  AS 'MEDIAN_LIST_PRICE',
                    median_ppsf        AS 'PRICE_PER_SQFT',
                    months_of_supply   AS 'MONTHS_OF_SUPPLY',
                    median_dom         AS 'AVG_DAYS_ON_MARKET',
                    avg_sale_to_list   AS 'AVG_SALE_TO_LIST',
                    sold_above_list    AS 'SOLD_ABOVE_LIST'
                ))
                WHERE zipcode IN ({zip_placeholders})
                  AND period_begin IS NOT NULL
                ORDER BY period_begin DESC
                LIMIT 10000
            """
            logger.info(
                "ArlingtonMarketIngestor | Querying BQ table '%s' for '%s' ...",
                full_table,
                self._town_slug,
            )
            rows = list(client.query(query).result())
            if not rows:
                logger.warning(
                    "ArlingtonMarketIngestor | BQ returned 0 rows for '%s' (table=%s). "
                    "Using synthetic data.",
                    self._town_slug,
                    full_table,
                )
                return self.generate_synthetic_bronze()

            now_utc = datetime.now(tz=timezone.utc)
            records: List[Dict[str, Any]] = []
            for row in rows:
                obs = row.observation_date
                if isinstance(obs, str):
                    try:
                        obs = datetime.fromisoformat(obs)
                    except ValueError:
                        obs = now_utc
                # BQ DATE fields come back as datetime.date — promote to datetime
                if hasattr(obs, "year") and not isinstance(obs, datetime):
                    obs = datetime(obs.year, obs.month, obs.day, tzinfo=timezone.utc)
                elif isinstance(obs, datetime) and obs.tzinfo is None:
                    obs = obs.replace(tzinfo=timezone.utc)
                records.append({
                    "metric_name":      row.metric_name,
                    "metric_value":     float(row.metric_value),
                    "observation_date": obs or now_utc,
                    "geo_level":        row.geo_level,
                    "geo_value":        row.geo_value,
                    "te_source":        self._te_source,
                    "te_geo_hash":      self._geo_hash,
                })
            logger.info(
                "ArlingtonMarketIngestor | BQ returned %d rows for '%s'.",
                len(records),
                self._town_slug,
            )
            return records

        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "ArlingtonMarketIngestor | BQ query failed for '%s' (%s: %s). "
                "Trying Zillow cache next.",
                self._town_slug, type(exc).__name__, exc,
            )
            zillow = self._fetch_zillow_cache_bronze()
            if zillow:
                return zillow
            return self.generate_synthetic_bronze()

    def _promote_to_gold(self, bronze: Dict[str, Any], linker: PartyLinker) -> Dict[str, Any]:
        obs_date: datetime = bronze["observation_date"]
        date_str: str = obs_date.strftime("%Y-%m-%d")
        # Honour the source declared on the bronze record (e.g. "zillow-zhvi") so
        # that Zillow-sourced rows are distinguishable from BQ-sourced rows at query time.
        effective_source: str = bronze.get("te_source") or self._te_source
        source_id: str = f"{bronze['metric_name']}:{bronze['geo_value']}:{date_str}"
        te_trend_pk: int = linker.resolve(effective_source, source_id)

        raw_for_factory: Dict[str, Any] = {
            "te_trend_pk":      te_trend_pk,
            "metric_name":      bronze["metric_name"],
            "metric_value":     bronze["metric_value"],
            "observation_date": bronze["observation_date"],
            "geo_level":        bronze["geo_level"],
            "geo_value":        bronze["geo_value"],
            "te_source":        effective_source,
            "te_geo_hash":      self._geo_hash,
        }
        return self._factory.map_to_market_trend(raw_for_factory)

    def run(self, output_dir: str = "data/gold") -> pathlib.Path:
        bronze_records = self.fetch_bronze()

        if not bronze_records:
            raise ValueError(f"ArlingtonMarketIngestor | 0 Bronze records for '{self._town_slug}'.")

        effective_linker = self._linker or get_linker()
        gold_records = [self._promote_to_gold(b, effective_linker) for b in bronze_records]

        out_path = save_gold_data(
            pd.DataFrame(gold_records), self._town_slug, "market-trends",
            output_dir=output_dir,
        )
        logger.info("ArlingtonMarketIngestor | Wrote %d Gold records -> %s", len(gold_records), out_path)
        return out_path
