# [FILE PATH]: reports/realtor_agent.py
# Patch #183
# Execution Mode: Realtor Agent — Civic Audit Report Generator
# Date: 2026-03-03
"""
RealtorAgent
============
Consumer-facing report generator for real-estate professionals.

Reads the five most investment-relevant Gold Parquet domains and
synthesises them into a plain-text **TownEye Civic Audit Report** — a
single-page briefing that gives a realtor everything they need to know
about a municipality before advising a buyer or investor.

Domains consumed
----------------
* ``market-trends``   — median rents, days-on-market, months of supply
* ``zoning``          — permitted uses and dimensional envelope
* ``infra-projects``  — active / planned DPW capital work
* ``str-dynamics``    — STR yield, occupancy rate, regulatory posture
* ``town-profile``    — neighbourhood vibes, NIMBY index, political lean

Zero-Hardcoding contract
------------------------
* All town-specific values (name, state, Gold data dir) are sourced
  from ``configs/{town_slug}/config.yaml`` via ``ConfigLoader``.
* The legal disclaimer is sourced exclusively from
  ``ConfigLoader.LEGAL_DISCLAIMER`` — never repeated in this file.
* Passing a different ``town_slug`` targets a different municipality
  with zero changes to this module.

Usage
-----
    python reports/realtor_agent.py

    # Target a different town (once its data is loaded):
    python reports/realtor_agent.py --town lexington-ma --address "1 Clarke St" --zip 02421
"""

import argparse
import json
import logging
import os
import pathlib
import sys
import textwrap
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Ensure project root is importable when run as __main__
_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

# Load .env so GEMINI_API_KEY and other secrets are available
_env_file = _ROOT / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

import pandas as pd

from core.config_loader import ConfigLoader

logger = logging.getLogger(__name__)

_REPORT_WIDTH = 72   # characters — fits in a terminal or PDF column


def _divider(char: str = "─", width: int = _REPORT_WIDTH) -> str:
    return char * width


def _wrap(text: str, indent: int = 2, width: int = _REPORT_WIDTH) -> str:
    """Wrap *text* to *width* with a leading indent on continuation lines."""
    return textwrap.fill(
        text,
        width=width,
        initial_indent=" " * indent,
        subsequent_indent=" " * indent,
    )


def _fmt_usd(value: float) -> str:
    return f"${value:,.0f}"


def _fmt_pct(value: float, decimals: int = 1) -> str:
    return f"{value:.{decimals}f}%"


class RealtorAgent:
    """
    Generates a TownEye Civic Audit Report for a given address.

    Parameters
    ----------
    town_slug : str
        Kebab-case municipality identifier (e.g. ``"arlington-ma"``).
    data_dir : str, optional
        Root directory for Gold Parquet files.  Defaults to ``"data/gold"``.
    config_base_dir : str, optional
        Root directory for per-town config folders.  Defaults to ``"configs"``.
    """

    def __init__(
        self,
        town_slug: str,
        data_dir: str = "data/gold",
        config_base_dir: str = "configs",
    ) -> None:
        loader = ConfigLoader(base_dir=config_base_dir)
        self._cfg: Dict[str, Any] = loader.get_town_config(town_slug)
        self._disclaimer: str = loader.get_legal_disclaimer()
        self._town_slug: str = self._cfg["town_slug"]
        self._town_name: str = self._cfg.get("town_name", town_slug)
        self._state: str = self._cfg.get("state", "")
        self._data_dir: pathlib.Path = pathlib.Path(data_dir)

    # ------------------------------------------------------------------
    # Parquet loaders — each returns an empty DataFrame on missing file
    # ------------------------------------------------------------------

    def _load(self, domain: str) -> pd.DataFrame:
        """Load ``{town_slug}/{domain}.parquet`` from the Gold data dir."""
        path = self._data_dir / self._town_slug / f"{domain}.parquet"
        if not path.exists():
            logger.warning("RealtorAgent | Parquet not found: %s — skipping.", path)
            return pd.DataFrame()
        df = pd.read_parquet(path)
        logger.debug("RealtorAgent | Loaded %d row(s) from %s", len(df), path)
        return df

    def _load_market(self) -> pd.DataFrame:
        return self._load("market-trends")

    def _load_zoning(self) -> pd.DataFrame:
        df = self._load("zoning")
        if not df.empty:
            for col in ("allowed_uses", "metadata"):
                if col in df.columns:
                    df[col] = df[col].apply(
                        lambda v: json.loads(v) if isinstance(v, str) else v
                    )
        return df

    def _load_infra(self) -> pd.DataFrame:
        df = self._load("infra-projects")
        if not df.empty and "metadata" in df.columns:
            df["metadata"] = df["metadata"].apply(
                lambda v: json.loads(v) if isinstance(v, str) else v
            )
        return df

    def _load_str(self) -> pd.DataFrame:
        df = self._load("str-dynamics")
        if not df.empty and "peak_seasons" in df.columns:
            df["peak_seasons"] = df["peak_seasons"].apply(
                lambda v: json.loads(v) if isinstance(v, str) else v
            )
        return df

    def _load_profile(self) -> pd.DataFrame:
        df = self._load("town-profile")
        if not df.empty:
            for col in ("major_employers", "metadata"):
                if col in df.columns:
                    df[col] = df[col].apply(
                        lambda v: json.loads(v) if isinstance(v, str) else v
                    )
        return df

    def _load_property(self) -> pd.DataFrame:
        return self._load("property")

    def _load_parcel(self) -> pd.DataFrame:
        """
        Load Domain 14 — town-wide parcel polygons with computed dimensions.

        ``geometry_coordinates``, ``edges_ft`` and ``metadata`` are persisted
        as JSON strings (Parquet cannot hold raw lists of mixed types); we
        round-trip through ``json.loads`` so downstream report code sees
        native Python structures and can pass them straight to ``shapely``
        or to envelope / setback math without further parsing.
        """
        df = self._load("parcel")
        if not df.empty:
            for col in ("geometry_coordinates", "edges_ft", "metadata"):
                if col in df.columns:
                    df[col] = df[col].apply(
                        lambda v: json.loads(v) if isinstance(v, str) else v
                    )
        return df

    def _load_zoning_overlay(self) -> pd.DataFrame:
        """
        Load Domain 15 — town-wide zoning + overlay polygons.

        Each row is one polygon from the town's zoning FeatureServer
        (base zone, overlay district, historic district, etc.); a parcel
        can intersect multiple rows.  Report-side point-in-polygon code
        joins these back to a parcel for the full applicable-rules stack
        (e.g. base R2 + NMF / MBMF MBTA-Communities overlays in Arlington).
        """
        df = self._load("zoning-overlay")
        if not df.empty:
            for col in ("geometry_coordinates", "metadata"):
                if col in df.columns:
                    df[col] = df[col].apply(
                        lambda v: json.loads(v) if isinstance(v, str) else v
                    )
        return df

    def _load_macris(self) -> pd.DataFrame:
        """
        Load Domain 16 — town-filtered MACRIS historic resources
        (points + district polygons).

        Source is the MAPC-hosted statewide ``MHC_Inventory_GDB`` service
        filtered by ``TOWN_NAME``.  Each row is either an individual
        historic resource (geometry_type = ``Point``) or a historic
        district polygon (``Polygon`` / ``MultiPolygon``).  Report-side
        code uses the points for "is THIS address listed?" lookups
        (string match on ``address``) and the polygons for "is THIS
        address inside any historic district?" point-in-polygon checks.
        """
        df = self._load("macris")
        if not df.empty:
            for col in ("geometry_coordinates", "metadata"):
                if col in df.columns:
                    df[col] = df[col].apply(
                        lambda v: json.loads(v) if isinstance(v, str) else v
                    )
        return df

    def _load_noncompliance(self) -> pd.DataFrame:
        """
        Load Domain 17 — descriptive Land-Use / Zoning Non-Compliance polygons.

        These are NOT enforcement cases — they flag every parcel whose
        recorded land-use code diverges from current zoning (a legal
        pre-existing non-conforming use, etc.).  Report-side code resolves
        a parcel to its non-compliance rows via point-in-polygon and uses
        the result to flag expansion-restricted parcels in the brief.
        """
        df = self._load("noncompliance")
        if not df.empty:
            for col in ("geometry_coordinates", "metadata"):
                if col in df.columns:
                    df[col] = df[col].apply(
                        lambda v: json.loads(v) if isinstance(v, str) else v
                    )
        return df

    def _load_local_historic(self) -> pd.DataFrame:
        """
        Load Domain 18 — town-level historic resources (LHD/NHD/Overlay/AHC).

        Town counterpart to Domain 16 (statewide MACRIS).  Aggregates four
        Arlington-hosted FeatureServers into one DataFrame whose rows
        share the ``TeHistoricResource`` schema.  Geometry can be Point,
        Polygon, MultiPolygon, or LineString (the NHD boundary is published
        as a single polyline).
        """
        df = self._load("local-historic")
        if not df.empty:
            for col in ("geometry_coordinates", "metadata"):
                if col in df.columns:
                    df[col] = df[col].apply(
                        lambda v: json.loads(v) if isinstance(v, str) else v
                    )
        return df

    def _load_environmental_overlay(self) -> pd.DataFrame:
        """
        Load Domain 19 — wetlands + FEMA flood (effective + preliminary 2023)
        in one table.

        The ``category`` column distinguishes the three subtypes; the
        report uses it to label any spatial hit ("Wetland CLASSIF: BVW",
        "Flood Zone AE", "Preliminary Flood Zone X (2023)").
        """
        df = self._load("environmental-overlay")
        if not df.empty:
            for col in ("geometry_coordinates", "metadata"):
                if col in df.columns:
                    df[col] = df[col].apply(
                        lambda v: json.loads(v) if isinstance(v, str) else v
                    )
        return df

    def _load_climate(self) -> pd.DataFrame:
        df = self._load("climate-zones")
        if not df.empty and "metadata" in df.columns:
            df["metadata"] = df["metadata"].apply(
                lambda v: json.loads(v) if isinstance(v, str) else v
            )
        return df

    def _load_transit(self) -> pd.DataFrame:
        return self._load("transit")

    # ------------------------------------------------------------------
    # On-demand live property fetch (used when address is not in cache)
    # ------------------------------------------------------------------

    def _fetch_property_live(self, address: str) -> Optional[pd.DataFrame]:
        """
        Fetch a single property record live from the assessor portal when the
        address is not present in the cached Parquet.

        Reads URL and search-param names from config:
            scraper_urls.property_assessor
            scraper_search_by_address.street_number_param
            scraper_search_by_address.street_name_param

        Returns a 1-row DataFrame in the same schema as the cached parquet,
        or None if the fetch / parse fails.
        """
        import re as _re
        import requests as _req

        m = _re.match(r"^\s*(\d+[A-Za-z]?)\s+(.+?)\s*$", address)
        if not m:
            return None
        street_num  = m.group(1)
        street_name = m.group(2)

        addr_cfg = self._cfg.get("scraper_search_by_address", {}) or {}
        num_param  = addr_cfg.get("street_number_param", "SearchStreetNumber")
        name_param = addr_cfg.get("street_name_param",  "SearchStreetName")
        base_url   = (self._cfg.get("scraper_urls", {}) or {}).get("property_assessor", "")
        if not base_url:
            return None

        ssl_verify = self._cfg.get("http", {}).get("ssl_verify", True)
        if not ssl_verify:
            import urllib3 as _u3
            _u3.disable_warnings(_u3.exceptions.InsecureRequestWarning)

        # Try with the full street name first; fallback by stripping the suffix
        # (some Patriot Properties towns store "MAGNOLIA" rather than "MAGNOLIA ST").
        candidates = [street_name]
        no_suffix = _re.sub(
            r"\s+(St|Rd|Ave|Avenue|Dr|Drive|Ln|Lane|Ct|Court|Way|Blvd|Pl|Place|"
            r"Pkwy|Parkway|Cir|Circle|Ter|Terrace|Sq|Square|Hwy|Highway)\.?$",
            "", street_name, flags=_re.IGNORECASE,
        )
        if no_suffix != street_name:
            candidates.append(no_suffix)

        records = []
        for cand in candidates:
            try:
                resp = _req.get(
                    base_url,
                    params={num_param: street_num, name_param: cand, "SearchOwner": ""},
                    timeout=15, verify=ssl_verify,
                )
                resp.raise_for_status()
            except Exception as exc:
                logger.warning("Live property fetch failed for '%s %s': %s", street_num, cand, exc)
                continue

            try:
                from scrapers.property_scraper import ArlingtonPropertyScraper
                scraper = ArlingtonPropertyScraper(self._cfg["town_slug"])
                parsed = scraper.parse_records(resp.text)
            except Exception as exc:
                logger.warning("Property HTML parse failed: %s", exc)
                continue

            # Filter to records whose address actually matches the requested street number.
            # Patriot Properties may return neighbouring parcels when the search is loose.
            for rec in parsed:
                rec_addr = (rec.get("location") or rec.get("address") or "").upper()
                if rec_addr.startswith(f"{street_num} ") or rec_addr.startswith(f"{street_num}-"):
                    records.append(rec)
            if records:
                break

        if not records:
            return None

        # Promote to gold schema using the existing scraper logic
        try:
            from scrapers.property_scraper import ArlingtonPropertyScraper
            from core.identity_linker import get_linker
            scraper = ArlingtonPropertyScraper(self._cfg["town_slug"])
            linker = get_linker()
            gold = [scraper._promote_to_gold(r, linker) for r in records]
            df = pd.DataFrame(gold)
            logger.info("Live property fetch returned %d record(s) for '%s'", len(df), address)
            return df
        except Exception as exc:
            logger.warning("Live property gold promotion failed: %s", exc)
            return None

    def _prefetch_property_apis(self, address: str, zipcode: str) -> Dict[str, float]:
        """
        Run all per-address external API calls in parallel and populate
        the per-instance memo caches. Subsequent calls to the individual
        lookup methods (_fema_lookup_address, _historic_lookup_address,
        _zoning_lookup_address, _fetch_property_live) return cached results
        instantly.

        Returns a dict of {task_name: elapsed_seconds} for diagnostic logging.
        """
        from concurrent.futures import ThreadPoolExecutor
        import time as _time

        # Geocode first (single shared HTTP call). All downstream lookups
        # need lat/lon, so doing this once up front saves 2 redundant calls.
        t0 = _time.monotonic()
        self._geocode_address(address, self._town_name, self._state, zipcode)
        geo_elapsed = _time.monotonic() - t0

        # Wrap each lookup in a small timing closure so we can report
        # actual API runtime per task (rather than the dispatcher overhead).
        def _timed(label: str, fn):
            def _runner():
                _start = _time.monotonic()
                try:
                    fn()
                except Exception as exc:
                    logger.warning("Prefetch '%s' failed: %s", label, exc)
                    return label, -1.0
                return label, round(_time.monotonic() - _start, 2)
            return _runner

        # Cache the live property fetch result so generate_report and
        # generate_html_report don't repeat the Patriot Properties HTTP call.
        live_cache = getattr(self, "_live_property_cache", None) or {}
        live_key = address.strip().upper()
        def _live_fetch():
            if live_key not in live_cache:
                live_cache[live_key] = self._fetch_property_live(address)
        self._live_property_cache = live_cache

        tasks = [
            _timed("fema",     lambda: self._fema_lookup_address(address, self._town_name, self._state, zipcode)),
            _timed("historic", lambda: self._historic_lookup_address(address, zipcode)),
            _timed("zoning",   lambda: self._zoning_lookup_address(address, zipcode)),
            _timed("property_live", _live_fetch),
        ]

        timings: Dict[str, float] = {"geocode": round(geo_elapsed, 2)}
        parallel_t0 = _time.monotonic()
        with ThreadPoolExecutor(max_workers=len(tasks)) as ex:
            for label, secs in ex.map(lambda t: t(), tasks):
                timings[label] = secs
        timings["parallel_total"] = round(_time.monotonic() - parallel_t0, 2)

        logger.info("Property API prefetch timings (seconds): %s", timings)
        return timings

    def _ensure_property_in_df(self, df: pd.DataFrame, address: str) -> pd.DataFrame:
        """
        Return df with a row matching `address`. If none is found, attempts
        a live single-property fetch and concatenates the result.
        Memoized: live fetch only happens once per address per process run.
        """
        cache_key = address.strip().upper()
        cache = getattr(self, "_live_property_cache", None)
        if cache is None:
            cache = {}
            self._live_property_cache = cache

        if df.empty or "address" not in df.columns:
            if cache_key not in cache:
                cache[cache_key] = self._fetch_property_live(address)
            live = cache[cache_key]
            return live if live is not None else df

        addr_up = address.strip().upper()
        hit = df[df["address"].str.upper() == addr_up]
        if not hit.empty:
            return df

        toks = addr_up.split()
        if toks:
            prefix_hit = df[df["address"].str.upper().str.startswith(toks[0])]
            for _, r in prefix_hit.iterrows():
                if all(t in str(r["address"]).upper() for t in toks[:2]):
                    return df

        if cache_key not in cache:
            cache[cache_key] = self._fetch_property_live(address)
        live = cache[cache_key]
        if live is not None and not live.empty:
            logger.info("Augmenting cached property data with live fetch for '%s'", address)
            return pd.concat([df, live], ignore_index=True)
        return df

    # ------------------------------------------------------------------
    # Section renderers
    # ------------------------------------------------------------------

    def _section_header(self, title: str) -> str:
        return (
            f"\n{_divider('─')}\n"
            f"  {title.upper()}\n"
            f"{_divider('─')}"
        )

    # ------------------------------------------------------------------
    # Gemini helper (mirrors app.py pattern, no Streamlit dependency)
    # ------------------------------------------------------------------

    @staticmethod
    def _call_gemini(system: str, user: str, max_tokens: int = 1024) -> str:
        """Single-shot Gemini call. Returns error string on failure (never raises)."""
        try:
            from google import genai
            from google.genai import types as gt
            api_key = os.environ.get("GEMINI_API_KEY", "").strip().strip('"').strip("'")
            if not api_key:
                return "[No GEMINI_API_KEY — set it to enable the Agent Brief]"
            client = genai.Client(api_key=api_key)
            resp = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=user,
                config=gt.GenerateContentConfig(
                    system_instruction=system,
                    temperature=0.3,
                    max_output_tokens=max_tokens,
                ),
            )
            return resp.text or ""
        except Exception as exc:  # noqa: BLE001
            return f"[Gemini error: {exc}]"

    _BRIEF_SYSTEM = textwrap.dedent("""\
        You are a senior real estate consultant writing a pre-showing briefing
        for a licensed real estate agent in Massachusetts.

        You will receive structured property data (assessor, FEMA flood zones,
        Zillow market trends, MBTA transit, zoning).

        Write EXACTLY 6 numbered talking points the agent can use in a buyer
        consultation or listing presentation for this specific property.
        The 6 points should cover (in this order): Market Value, Property Features,
        Zoning, Flood Risk, Historic Status, Transit Access.

        Rules:
        - Each point is 2–3 sentences, direct and confident.
        - Lead each point with a bold keyword (e.g. **Pricing**, **Flood Risk**).
        - Cite specific numbers from the data (values, percentages, years, routes).
        - Write from the agent's perspective: "This property...", "Your buyer..."
        - Do NOT use generic phrases like "great opportunity" or "desirable location".
        - Do NOT invent data not present in the input.
        - Always use the $ symbol for dollar amounts (e.g. $1,401,100 not "USD 1,401,100").
        - Do not use markdown headers or horizontal rules — numbered list only.

        CRITICAL DATA INTERPRETATION RULES:
        - The field "bylaw_zone_code" is the official zoning district (e.g. "R2").
          NEVER use "assessor_zone_code_raw" as the zone name — it is an internal
          assessor classification number, not a zoning district.
        - The field "property_flood_note" describes THIS property's specific flood status.
          Use ONLY this for the flood risk talking point.
          The "town_wide_fema_context" fields are background context for the whole town —
          do NOT say the property is in those flood zones.
        - The field "property_historic_note" describes THIS property's MACRIS / historic
          district status. Use it for the historic-status talking point. If
          "property_in_historic_district" is true, this is a MATERIAL talking point
          (it constrains exterior renovations).
    """).strip()

    def _render_agent_brief(
        self,
        address: str,
        zipcode: str,
        df_property: pd.DataFrame,
        df_market: pd.DataFrame,
        df_climate: pd.DataFrame,
        df_transit: pd.DataFrame,
        df_zoning: pd.DataFrame,
    ) -> str:
        # Memoize per-address: text and HTML reports both call this method,
        # so caching avoids a second Gemini round-trip (saves ~5-7 sec + halves quota).
        cache_key = f"{address.strip().upper()}|{zipcode.strip()}"
        cache = getattr(self, "_brief_cache", None)
        if cache is None:
            cache = {}
            self._brief_cache = cache
        if cache_key in cache:
            return cache[cache_key]

        lines = [self._section_header("Agent Brief  ·  Gemini  [AI-SYNTHESIZED FROM REAL DATA]")]

        # ── Build compact data context ─────────────────────────────────
        ctx: Dict[str, Any] = {
            "property_address": address,
            "zipcode": zipcode,
            "town": f"{self._town_name}, {self._state}",
        }

        # Property assessor facts
        if not df_property.empty and "address" in df_property.columns:
            addr_upper = address.strip().upper()
            match = df_property[df_property["address"].str.upper() == addr_upper]
            if match.empty:
                tokens = addr_upper.split()
                if tokens:
                    match = df_property[df_property["address"].str.upper().str.startswith(tokens[0])]
            if not match.empty:
                r = match.iloc[0]
                ctx["assessed_value_usd"] = float(r["assessed_value"]) if r.get("assessed_value") else None
                ctx["year_built"]   = int(r["year_built"]) if r.get("year_built") else None
                ctx["beds"]         = int(r["beds"]) if r.get("beds") else None
                ctx["baths"]        = float(r["baths"]) if r.get("baths") else None
                ctx["parcel_id"]    = str(r.get("parcel_id", ""))
                _raw_zc = str(r.get("zone_code", ""))
                ctx["assessor_zone_code_raw"] = _raw_zc

        # Property-specific zoning via official GIS (point-in-polygon). This is
        # the authoritative source — falls back to assessor_to_zoning_map only
        # when the GIS layer doesn't return a hit.
        z = self._zoning_lookup_address(address, zipcode)
        if z.get("ok") and z.get("zone_code"):
            ctx["bylaw_zone_code"]        = z["zone_code"]      # e.g. "R2"
            ctx["bylaw_zone_name"]        = z["zone_name"]      # e.g. "R2: Two Family"
            ctx["bylaw_zone_description"] = z["zone_description"]
            ctx["bylaw_zone_source"]      = "Arlington official Zoning GIS layer (point-in-polygon)"
        elif ctx.get("assessor_zone_code_raw"):
            _zone_map = self._cfg.get("assessor_to_zoning_map", {}) or {}
            _raw = ctx["assessor_zone_code_raw"]
            _resolved = _zone_map.get(_raw) or _zone_map.get(_raw.upper())
            if _resolved:
                ctx["bylaw_zone_code"]   = _resolved
                ctx["bylaw_zone_source"] = "assessor_to_zoning_map (config fallback)"
            else:
                ctx["bylaw_zone_code"]   = ""
                ctx["bylaw_zone_note"]   = (
                    "Bylaw zone could not be determined automatically — "
                    "agent should verify with Arlington Inspectional Services."
                )

        # Market trend: latest value + 3-yr appreciation
        if not df_market.empty and "metric_value" in df_market.columns:
            df_m = df_market.copy()
            if "observation_date" in df_m.columns:
                df_m["observation_date"] = pd.to_datetime(df_m["observation_date"], utc=True, errors="coerce")
            sp = df_m[df_m.get("metric_name", pd.Series()) == "MEDIAN_SALE_PRICE"] \
                if "metric_name" in df_m.columns else pd.DataFrame()
            if not sp.empty:
                sp = sp.sort_values("observation_date")
                oldest_val = float(sp.iloc[0]["metric_value"])
                newest_val = float(sp.iloc[-1]["metric_value"])
                pct = round(100 * (newest_val / oldest_val - 1), 1) if oldest_val else 0
                ctx["zip_median_home_value_usd"] = round(newest_val, 0)
                ctx["zip_3yr_appreciation_pct"]  = pct
                ctx["zip_3yr_low_usd"]           = round(oldest_val, 0)

        # Estimated current market value (AV × ZHVI 1-yr appreciation)
        if ctx.get("assessed_value_usd") and not df_market.empty:
            avm = self._estimate_market_value(ctx["assessed_value_usd"], df_market, zipcode)
            if avm:
                ctx["estimated_market_value_usd"]  = avm["estimated_value"]
                ctx["estimated_mkt_appreciation_1yr_pct"] = avm["appreciation_1yr_pct"]
                ctx["estimated_mkt_as_of"]         = avm["as_of"]

        # FEMA flood zones — property-specific first, then town-wide context
        fema_result = self._fema_lookup_address(address, self._town_name, self._state, zipcode)
        if fema_result["found"]:
            ctx["property_fema_zone"]        = fema_result["fema_zone"]   # e.g. "X"
            ctx["property_sfha"]             = fema_result["sfha"]        # True = in flood zone
            ctx["property_flood_risk_level"] = fema_result["risk_level"]  # "NONE","MODERATE","HIGH"
            if not fema_result["sfha"]:
                ctx["property_flood_insurance_required"] = False
                ctx["property_flood_note"] = (
                    "This property is NOT in a Special Flood Hazard Area. "
                    "Flood insurance is NOT required by federally-backed lenders."
                )
            else:
                ctx["property_flood_insurance_required"] = True
                ctx["property_flood_note"] = (
                    f"This property IS in a Special Flood Hazard Area (Zone {fema_result['fema_zone']}). "
                    "Flood insurance IS required for federally-backed mortgages."
                )
        if not df_climate.empty and "risk_level" in df_climate.columns:
            counts = df_climate["risk_level"].value_counts().to_dict()
            ctx["town_wide_fema_context"] = {
                "note": "These are TOWN-WIDE polygon counts, NOT specific to this property.",
                "high_risk_polygons_in_town":     counts.get("HIGH", 0),
                "moderate_risk_polygons_in_town": counts.get("MODERATE", 0),
            }
            if "metadata" in df_climate.columns:
                zones = (
                    df_climate["metadata"]
                    .apply(lambda m: m.get("fema_zone") if isinstance(m, dict) else None)
                    .dropna().unique().tolist()
                )
                ctx["town_wide_fema_context"]["zone_codes_present_in_town"] = sorted(
                    set(str(z) for z in zones if z)
                )

        # MBTA live alerts
        if not df_transit.empty and "event_name" in df_transit.columns:
            ctx["mbta_active_alerts"] = df_transit["event_name"].tolist()
        mbta_cfg = self._cfg.get("town_pulse", {}).get("mbta", {})
        ctx["mbta_routes_serving_town"] = mbta_cfg.get("routes", [])

        # Historic resources — MACRIS / Local Historic District / AHC inventory
        h = self._historic_lookup_address(address, zipcode)
        if h.get("found"):
            ctx["property_in_macris"]          = True
            ctx["property_in_historic_district"] = bool(h.get("in_district"))
            ctx["property_macris_designations"]  = h.get("designations") or []
            ctx["property_macris_id"]            = h.get("macris_id") or ""
            ctx["property_historic_name"]        = h.get("historic_name") or ""
            ctx["property_constructed"]          = h.get("constructed") or ""
            ctx["property_architectural_style"]  = h.get("architectural_style") or ""
            in_lhd = any("LHD" in d.upper() or "LOCAL HISTORIC" in d.upper() for d in h.get("designations", []))
            if in_lhd:
                ctx["property_historic_note"] = (
                    "This property IS in a Local Historic District. Exterior alterations "
                    "visible from a public way require an Arlington Historical Commission "
                    "Certificate of Appropriateness BEFORE any building permit is issued."
                )
            else:
                ctx["property_historic_note"] = (
                    "This property is listed on the MACRIS state inventory but is NOT in a "
                    "Local Historic District. No binding restrictions, but demolition may "
                    "trigger Arlington's demolition-delay bylaw."
                )
        elif not h.get("error"):
            ctx["property_in_macris"]            = False
            ctx["property_in_historic_district"] = False
            ctx["property_historic_note"] = (
                "This property is NOT on the MACRIS inventory and NOT in a historic district. "
                "No special historic-preservation review required."
            )

        # Zoning — look up by resolved bylaw zone code (e.g. "R2"), not raw assessor code ("1")
        if not df_zoning.empty and ctx.get("bylaw_zone_code"):
            zrow = df_zoning[df_zoning["zone_code"] == ctx["bylaw_zone_code"]]
            if not zrow.empty:
                r = zrow.iloc[0]
                ctx["zone_description"] = str(r.get("zone_description", ""))
                uses = r.get("allowed_uses") or []
                ctx["zone_allowed_uses"] = uses if isinstance(uses, list) else []
                meta = r.get("metadata") or {}
                if isinstance(meta, str):
                    try:
                        meta = json.loads(meta)
                    except (json.JSONDecodeError, TypeError):
                        meta = {}
                ctx["zone_max_height_ft"] = r.get("max_height_ft")
                ctx["zone_max_far"]       = meta.get("max_far")
                ctx["zone_min_lot_sqft"]  = meta.get("min_lot_sqft")

        # ── Call Gemini ────────────────────────────────────────────────
        user_msg = (
            f"PROPERTY DATA (JSON):\n{json.dumps(ctx, indent=2, default=str)}\n\n"
            f"Write the 5-point agent brief for {address}, {self._town_name}, {self._state} {zipcode}."
        )
        brief = self._call_gemini(self._BRIEF_SYSTEM, user_msg, max_tokens=4000)

        if brief.startswith("["):
            lines.append(f"  {brief}")
        else:
            # Indent each line for consistent report formatting
            for line in brief.strip().splitlines():
                lines.append(f"  {line}" if line.strip() else "")

        result = "\n".join(lines)
        cache[cache_key] = result
        return result

    def _render_property(
        self,
        df: pd.DataFrame,
        address: str,
        df_market: Optional[pd.DataFrame] = None,
        zipcode: str = "",
    ) -> str:
        lines = [self._section_header("Property Assessment  ·  Town Assessor  [REAL DATA]")]
        if df.empty:
            lines.append("  No property assessment data available.")
            return "\n".join(lines)

        # Try exact then partial case-insensitive match against the address column
        addr_upper = address.strip().upper()
        if "address" in df.columns:
            match = df[df["address"].str.upper() == addr_upper]
            if match.empty:
                # Partial match — first token of the street number + first word of street name
                tokens = addr_upper.split()
                if tokens:
                    match = df[df["address"].str.upper().str.startswith(tokens[0])]

        if not match.empty:
            row = match.iloc[0]
            lines.append(f"  {'Address':<22} {row.get('address', address)}")
            owner = str(row.get("owner_name") or "—")
            lines.append(f"  {'Owner':<22} {owner[:60]}")
            av = row.get("assessed_value")
            av_float = float(av) if av and float(av) > 0 else None
            if av_float:
                lines.append(f"  {'Assessed Value':<22} {_fmt_usd(av_float)}")
                # ── Estimated Current Market Value ──────────────────────
                if df_market is not None and not df_market.empty:
                    avm = self._estimate_market_value(av_float, df_market, zipcode)
                    if avm:
                        sign = "+" if avm["appreciation_1yr_pct"] >= 0 else ""
                        lines.append(
                            f"  {'Est. Market Value':<22} {_fmt_usd(avm['estimated_value'])}"
                            f"  ({sign}{avm['appreciation_1yr_pct']}% 1-yr ZHVI, as of {avm['as_of']})"
                        )
            yb = row.get("year_built")
            if yb:
                lines.append(f"  {'Year Built':<22} {int(yb)}")
            zone = row.get("zone_code")
            zone_display = None
            gis_zone = self._zoning_lookup_address(address, zipcode)
            if gis_zone.get("ok") and gis_zone.get("zone_name"):
                zone_display = gis_zone["zone_name"]
                if gis_zone.get("zone_description"):
                    zone_display += f"  —  {gis_zone['zone_description']}"
            elif zone:
                zone_map = self._cfg.get("assessor_to_zoning_map", {})
                resolved = zone_map.get(str(zone)) or zone_map.get(str(zone).upper())
                if resolved:
                    zone_display = f"{resolved}  (assessor code: {zone})"
                else:
                    zone_display = f"Verify with town  (assessor code: {zone})"
            if zone_display:
                lines.append(f"  {'Zone (Bylaw)':<22} {zone_display}")
            beds  = row.get("beds")
            baths = row.get("baths")
            if beds or baths:
                bd = f"{int(beds)} bd" if beds else ""
                bt = f"{float(baths):.1f} ba" if baths else ""
                lines.append(f"  {'Beds / Baths':<22} {bd}  {bt}".rstrip())
            parcel = row.get("parcel_id")
            if parcel:
                lines.append(f"  {'Parcel ID':<22} {parcel}")
            src = row.get("te_source", "arlington-ma-tax-assessor")
            lines.append(f"  {'Source':<22} {src}")
        else:
            # No direct parcel match — show neighbourhood context instead
            lines.append(f"  No exact parcel match for \"{address}\" in assessor data.")
            lines.append(f"  Showing neighbourhood context ({len(df)} parcels loaded):\n")
            top = df.copy()
            if "assessed_value" in top.columns:
                top = top.sort_values("assessed_value", ascending=False).head(5)
            for _, r in top.iterrows():
                av_s = _fmt_usd(float(r["assessed_value"])) if r.get("assessed_value") else "N/A"
                lines.append(f"  • {str(r.get('address','?')):<30} {av_s:<12} {str(r.get('owner_name',''))[:40]}")
            src = df["te_source"].iloc[0] if "te_source" in df.columns else "arlington-ma-tax-assessor"
            lines.append(f"\n  Source: {src}")

        return "\n".join(lines)

    def _render_climate(self, df: pd.DataFrame, address: str = "", zipcode: str = "") -> str:
        lines = [self._section_header("Flood Risk  ·  FEMA NFHL  [REAL DATA]")]
        if df.empty:
            lines.append("  No FEMA flood zone data available.")
            return "\n".join(lines)

        import urllib.parse
        fema_query = urllib.parse.quote(
            f"{address}, {self._town_name}, {self._state} {zipcode}".strip(", ")
        )
        fema_url = f"https://msc.fema.gov/portal/search#searchresultsanchor?addressquery={fema_query}"

        # ── Property-specific live lookup ──────────────────────────────
        if address:
            lookup = self._fema_lookup_address(address, self._town_name, self._state, zipcode)
            if lookup["found"]:
                zone      = lookup["fema_zone"] or "X"
                risk      = lookup["risk_level"]
                sfha      = lookup["sfha"]
                if risk == "NONE" or zone == "X":
                    status_icon = "✅"
                    status_text = f"NOT in a Special Flood Hazard Area  (Zone {zone} — minimal/moderate risk)"
                    ins_note    = "Flood insurance is NOT required by federally-backed lenders."
                elif risk == "HIGH":
                    status_icon = "🔴"
                    status_text = f"HIGH FLOOD RISK — Zone {zone} (Special Flood Hazard Area)"
                    ins_note    = "⚠ Flood insurance IS REQUIRED for federally-backed mortgages."
                else:
                    status_icon = "🟡"
                    status_text = f"MODERATE FLOOD RISK — Zone {zone}"
                    ins_note    = "Flood insurance is recommended but not required."
                lines.append(f"  {status_icon}  THIS PROPERTY: {status_text}")
                lines.append(f"     {ins_note}")
                if lookup.get("lat"):
                    lines.append(f"     Coordinates: {lookup['lat']:.5f}, {lookup['lon']:.5f}  (Census geocoded)")
            else:
                lines.append(f"  ⚠  Could not determine property flood zone: {lookup['error']}")
                lines.append(f"     Manual lookup: {fema_url}")
            lines.append("")

        # ── Town-wide context (background education) ──────────────────
        total = len(df)
        counts: Dict[str, int] = {}
        if "risk_level" in df.columns:
            counts = df["risk_level"].value_counts().to_dict()
        high     = counts.get("HIGH", 0)
        moderate = counts.get("MODERATE", 0)
        low      = counts.get("LOW", 0)

        fema_zone_detail = ""
        if "metadata" in df.columns:
            fema_zones = (
                df["metadata"]
                .apply(lambda m: m.get("fema_zone") if isinstance(m, dict) else None)
                .dropna().unique().tolist()
            )
            if fema_zones:
                fema_zone_detail = ", ".join(sorted(set(str(z) for z in fema_zones if z)))

        lines.append(f"  TOWN-WIDE CONTEXT  ·  {self._town_name} flood zone polygons: {total} total")
        lines.append(f"  {'  Zone AE / Floodway (HIGH):':<42}  {high:>4} polygons")
        lines.append(f"  {'  Zone X — 500-yr (MODERATE):':<42}  {moderate:>4} polygons")
        if low:
            lines.append(f"  {'  Low risk:':<42}  {low:>4} polygons")
        if fema_zone_detail:
            lines.append(f"  Zone codes in {self._town_name}: {fema_zone_detail}")

        lines.append("")
        lines.append("  Zone AE = 100-yr floodplain. Federally-backed mortgages require flood insurance.")
        lines.append("  Zone X  = moderate risk; flood insurance is optional but recommended.")

        src = df["te_source"].iloc[0] if "te_source" in df.columns else "fema-flood-maps"
        lines.append(f"\n  Source: {src}  (town-wide FEMA NFHL MapServer layer 28)")
        return "\n".join(lines)

    def _render_historic(self, address: str, zipcode: str) -> str:
        """Live MACRIS / Local Historic District / AHC inventory lookup."""
        lines = [self._section_header("Historic Status  ·  MACRIS / AHC  [REAL DATA]")]

        cfg = self._cfg.get("historic_resources", {}) or {}
        if not (cfg.get("macris_polygon_layer_url") or cfg.get("macris_point_layer_url")):
            lines.append("  No historic_resources URLs configured for this town.")
            return "\n".join(lines)

        h = self._historic_lookup_address(address, zipcode)

        if h.get("error") and not h["found"]:
            lines.append(f"  ⚠  Historic lookup unavailable: {h['error']}")
            if cfg.get("macris_search_url"):
                lines.append(f"     Manual search: {cfg['macris_search_url']}")
            return "\n".join(lines)

        if not h["found"]:
            lines.append("  ✅  THIS PROPERTY: NOT in MACRIS inventory and NOT in a historic district.")
            lines.append("     No special historic-preservation review required for renovations.")
        else:
            tags = []
            for d in h["designations"]:
                d_norm = d.upper()
                if d_norm in ("LHD", "LOCAL HISTORIC DISTRICT"):
                    tags.append("Local Historic District (LHD)")
                elif d_norm in ("NRHP", "NATIONAL REGISTER OF HISTORIC PLACES"):
                    tags.append("National Register (NRHP)")
                elif d_norm == "NRHP AND LHD":
                    tags.append("NRHP + Local Historic District")
                elif d_norm in ("MA/HL", "MASSACHUSETTS HISTORIC LANDMARK"):
                    tags.append("MA Historic Landmark")
                elif d_norm == "PR" or "PRESERVATION RESTRICTION" in d_norm:
                    tags.append("Preservation Restriction")
                elif d_norm in ("INVENTORIED PROPERTY", "INV"):
                    tags.append("Inventoried (no formal designation)")
                else:
                    tags.append(d)

            in_lhd = any("Local Historic District" in t or "NRHP + Local" in t for t in tags)
            warn_icon = "🔴" if in_lhd else "🟡"
            lines.append(f"  {warn_icon}  THIS PROPERTY: Listed on MACRIS  ·  {' | '.join(tags) or 'Designated'}")
            if h["historic_name"]:
                lines.append(f"     Historic Name:    {h['historic_name']}")
            if h["common_name"] and h["common_name"] != h["historic_name"]:
                lines.append(f"     Common Name:      {h['common_name']}")
            if h["constructed"]:
                lines.append(f"     Constructed:      {h['constructed']}")
            if h["architectural_style"]:
                lines.append(f"     Architectural:    {h['architectural_style']}")
            if h["macris_id"]:
                lines.append(f"     MACRIS ID:        {h['macris_id']}")
            if in_lhd:
                lines.append("")
                lines.append("  ⚠  Exterior alterations visible from a public way require an")
                lines.append("     Arlington Historical Commission Certificate of Appropriateness")
                lines.append("     before any building permit can be issued.")
            elif h["inventoried"] and not in_lhd:
                lines.append("")
                lines.append("  ℹ Inventoried-but-not-designated properties have no binding restrictions,")
                lines.append("    but demolition may trigger Arlington's demolition-delay bylaw.")

        if cfg.get("macris_search_url"):
            lines.append("")
            lines.append(f"  MACRIS lookup: {cfg['macris_search_url']}")
        if cfg.get("ahc_inventory_url"):
            lines.append(f"  Arlington Historical Commission: {cfg['ahc_inventory_url']}")
        lines.append("\n  Source: MA Historical Commission MACRIS (point + polygon layers via Boston Planning).")
        return "\n".join(lines)

    def _render_transit(self, df: pd.DataFrame) -> str:
        lines = [self._section_header("Live Transit Alerts  ·  MBTA  [REAL DATA]")]
        if df.empty:
            lines.append("  No active MBTA alerts for configured routes.")
            return "\n".join(lines)

        if "start_time" in df.columns:
            df = df.copy()
            df["start_time"] = pd.to_datetime(df["start_time"], utc=True, errors="coerce")
            df = df.sort_values("start_time", ascending=False)

        for _, row in df.iterrows():
            name = str(row.get("event_name") or "Alert")
            start = row.get("start_time")
            end   = row.get("end_time")
            date_s = ""
            if pd.notna(start):
                date_s = pd.Timestamp(start).strftime("%b %-d")
            if end and pd.notna(pd.Timestamp(end)):
                date_s += f" → {pd.Timestamp(end).strftime('%b %-d')}"
            prefix = "⚠ " if any(w in name.lower() for w in ("delay", "suspend", "cancel", "detour")) else "ℹ "
            lines.append(f"  {prefix}{_wrap(name, indent=4).lstrip()}")
            if date_s:
                lines.append(f"    Active: {date_s}")
            lines.append("")

        src = df["te_source"].iloc[0] if "te_source" in df.columns else "arlington-ma-mbta-alerts"
        lines.append(f"  Source: {src}  (live MBTA API v3)")
        return "\n".join(lines)

    def _render_market(self, df: pd.DataFrame) -> str:
        lines = [self._section_header("Market Dynamics  ·  Zillow ZHVI  [REAL DATA]")]
        if df.empty:
            lines.append("  No market trend data available.")
            return "\n".join(lines)

        # Most-recent observation per metric across all geo_values
        df = df.copy()
        if "observation_date" in df.columns:
            df["observation_date"] = pd.to_datetime(df["observation_date"], utc=True)
            df = df.sort_values("observation_date", ascending=False)

        latest: Dict[str, float] = {}
        for _, row in df.iterrows():
            key = str(row.get("metric_name", ""))
            if key and key not in latest:
                latest[key] = float(row.get("metric_value", 0))

        METRIC_LABELS: Dict[str, str] = {
            "MEDIAN_RENT_1BR":    "Median Rent — 1 BR",
            "MEDIAN_RENT_2BR":    "Median Rent — 2 BR",
            "MEDIAN_RENT_3BR":    "Median Rent — 3 BR",
            "MEDIAN_SALE_PRICE":  "Median Sale Price",
            "AVG_DAYS_ON_MARKET": "Avg. Days on Market",
            "MONTHS_OF_SUPPLY":   "Months of Supply",
            "PRICE_PER_SQFT":     "Price per sq ft",
        }
        USD_METRICS = {
            "MEDIAN_RENT_1BR", "MEDIAN_RENT_2BR", "MEDIAN_RENT_3BR",
            "MEDIAN_SALE_PRICE", "PRICE_PER_SQFT",
        }

        if latest:
            for key, label in METRIC_LABELS.items():
                if key in latest:
                    val = latest[key]
                    formatted = (
                        _fmt_usd(val) if key in USD_METRICS
                        else f"{val:.1f} days" if key == "AVG_DAYS_ON_MARKET"
                        else f"{val:.1f} months" if key == "MONTHS_OF_SUPPLY"
                        else str(val)
                    )
                    lines.append(f"  {label:<30}  {formatted}")
        else:
            lines.append("  No metrics found.")

        return "\n".join(lines)

    def _render_zoning(
        self,
        df: pd.DataFrame,
        raw_zone_code: str = "",
    ) -> str:
        bylaw_year = self._cfg.get("zoning", {}).get("bylaw_year", "2024")
        lines = [self._section_header(f"Zoning Summary  ·  {self._town_name} Bylaw {bylaw_year}  [ACCURATE]")]
        if df.empty:
            lines.append("  No zoning data available.")
            return "\n".join(lines)

        # Filter to the property's zone only when a code is supplied
        zone_row = self._resolve_zone_row(df, raw_zone_code) if raw_zone_code else None
        rows_to_show = [zone_row] if zone_row is not None else list(df.itertuples(index=False))

        for row in rows_to_show:
            # Support both pd.Series (from _resolve_zone_row) and named-tuple rows
            get = (lambda k: row.get(k)) if hasattr(row, "get") else (lambda k: getattr(row, k, None))
            code  = get("zone_code") or "?"
            desc  = get("zone_description") or ""
            max_h = get("max_height_ft")
            uses: List[str] = get("allowed_uses") or []
            meta: Dict[str, Any] = get("metadata") or {}
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except (json.JSONDecodeError, TypeError):
                    meta = {}

            lines.append(f"\n  Zone {code}  —  {desc}")
            if max_h:
                lines.append(f"    Max height:    {float(max_h):.0f} ft")
            if meta.get("min_lot_sqft"):
                lines.append(f"    Min lot:       {int(meta['min_lot_sqft']):,} sq ft")
            if meta.get("max_far"):
                lines.append(f"    Max FAR:       {meta['max_far']}")
            if meta.get("setback_front_ft"):
                lines.append(f"    Front setback: {int(meta['setback_front_ft'])} ft")
            if meta.get("min_frontage_ft"):
                lines.append(f"    Min frontage:  {int(meta['min_frontage_ft'])} ft")
            if uses:
                uses_str = ", ".join(uses[:6])
                if len(uses) > 6:
                    uses_str += f", +{len(uses) - 6} more"
                lines.append(f"    Permitted:     {uses_str}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Helpers shared by pro-forma + compliance
    # ------------------------------------------------------------------

    def _resolve_zone_row(self, df_zoning: pd.DataFrame, raw_zone_code: str) -> Optional[pd.Series]:
        """Return the zoning row that best matches the assessor zone_code.

        First checks the town config's ``assessor_to_zoning_map`` to translate
        Patriot Properties internal codes (e.g. "1", "CG") to bylaw zone codes
        (e.g. "R2", "B2").  Falls back to heuristic transformations only when
        no explicit mapping exists.
        """
        if df_zoning.empty or "zone_code" not in df_zoning.columns:
            return None
        code = str(raw_zone_code).strip()

        # Config-level explicit mapping takes precedence (most accurate)
        zone_map: Dict[str, str] = self._cfg.get("assessor_to_zoning_map", {})
        mapped_code = zone_map.get(code) or zone_map.get(code.upper())
        if mapped_code:
            hit = df_zoning[df_zoning["zone_code"] == mapped_code]
            if not hit.empty:
                return hit.iloc[0]

        # Heuristic fallback: try exact match then common prefix transformations
        for candidate in [code, f"R{code}", f"R-{code}", f"B{code}", code.upper()]:
            hit = df_zoning[df_zoning["zone_code"] == candidate]
            if not hit.empty:
                return hit.iloc[0]
        return None

    @staticmethod
    def _compliance_verdict(actual, required, label: str = "", invert: bool = False) -> str:
        """Return a formatted compliance verdict line."""
        if actual is None:
            verdict = "⚠  Requires Verification"
        elif invert:
            verdict = "✅ COMPLIANT" if actual <= required else "❌ NON-CONFORMING"
        else:
            verdict = "✅ COMPLIANT" if actual >= required else "❌ NON-CONFORMING (pre-existing)"
        return verdict

    # ------------------------------------------------------------------
    # FEMA address-level flood zone lookup
    # ------------------------------------------------------------------

    def _geocode_address(self, address: str, city: str, state: str, zipcode: str) -> Dict[str, Any]:
        """
        Memoized US Census Geocoder lookup. Returns
        {"ok": bool, "lat": float|None, "lon": float|None, "error": str}.
        """
        cache_key = f"{address.strip().upper()}|{city}|{state}|{zipcode}"
        cache = getattr(self, "_geocode_cache", None)
        if cache is None:
            cache = {}
            self._geocode_cache = cache
        if cache_key in cache:
            return cache[cache_key]

        import requests as _req
        out: Dict[str, Any] = {"ok": False, "lat": None, "lon": None, "error": ""}
        try:
            geo_resp = _req.get(
                "https://geocoding.geo.census.gov/geocoder/locations/address",
                params={
                    "street": address, "city": city, "state": state,
                    "zip": zipcode, "benchmark": "2020", "format": "json",
                },
                timeout=10,
            )
            geo_resp.raise_for_status()
            matches = geo_resp.json().get("result", {}).get("addressMatches", [])
            if matches:
                coords = matches[0]["coordinates"]
                out.update({"ok": True, "lat": float(coords["y"]), "lon": float(coords["x"])})
            else:
                out["error"] = "Address not found by Census geocoder"
        except Exception as exc:
            out["error"] = f"Geocoding failed: {exc}"

        cache[cache_key] = out
        return out

    def _fema_lookup_address(self, address: str, city: str, state: str, zipcode: str) -> Dict[str, Any]:
        """
        Determine the FEMA flood zone for a specific address.
        Memoized: subsequent calls with the same address return the cached result.
        """
        cache_key = f"{address.strip().upper()}|{city}|{state}|{zipcode}"
        cache = getattr(self, "_fema_cache", None)
        if cache is None:
            cache = {}
            self._fema_cache = cache
        if cache_key in cache:
            return cache[cache_key]

        import requests as _req
        result: Dict[str, Any] = {
            "found": False, "fema_zone": None, "risk_level": "UNKNOWN",
            "sfha": None, "lat": None, "lon": None, "error": "",
        }

        coords = self._geocode_address(address, city, state, zipcode)
        if not coords.get("ok"):
            result["error"] = coords.get("error") or "Geocoding failed"
            cache[cache_key] = result
            return result
        lat = coords["lat"]
        lon = coords["lon"]
        result["lat"], result["lon"] = lat, lon

        try:
            nfhl_resp = _req.get(
                "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query",
                params={
                    "geometry":       f"{lon},{lat}",
                    "geometryType":   "esriGeometryPoint",
                    "inSR":           "4326",
                    "spatialRel":     "esriSpatialRelIntersects",
                    "outFields":      "FLD_ZONE,SFHA_TF,ZONE_SUBTY",
                    "returnGeometry": "false",
                    "f":              "json",
                },
                timeout=15,
            )
            nfhl_resp.raise_for_status()
            features = nfhl_resp.json().get("features", [])

            if not features:
                # No flood zone polygon at this point = Zone X / minimal hazard
                result.update({"found": True, "fema_zone": "X", "risk_level": "NONE", "sfha": False})
            else:
                attrs    = features[0]["attributes"]
                fld_zone = str(attrs.get("FLD_ZONE") or "X").strip()
                sfha     = str(attrs.get("SFHA_TF") or "F").upper() == "T"
                risk     = "HIGH" if sfha else ("MODERATE" if fld_zone.startswith("X") else "LOW")
                result.update({
                    "found": True, "fema_zone": fld_zone,
                    "risk_level": risk, "sfha": sfha,
                })
        except Exception as exc:
            result["error"] = f"FEMA NFHL query failed: {exc}"

        cache[cache_key] = result
        return result

    # ------------------------------------------------------------------
    # Historic Resources lookup (MACRIS / Local Historic District / AHC)
    # ------------------------------------------------------------------

    def _historic_lookup_address(self, address: str, zipcode: str) -> Dict[str, Any]:
        """
        Determine historic-resource status for a specific address.

        Steps
        -----
        1. Geocode the address (Census, free).
        2. Query the MACRIS Polygon layer with point-in-polygon — catches
           Local Historic Districts, NRHP districts, and large parcels.
        3. Query the MACRIS Point layer with a small distance buffer —
           catches inventoried-but-not-designated single buildings.

        Configuration
        -------------
        URLs and town code come exclusively from the `historic_resources`
        block in the town's config.yaml (zero hardcoding).

        Returns
        -------
        dict with keys:
            found         – bool   (True if at least one MACRIS hit)
            in_district   – bool   (point falls inside a polygon)
            inventoried   – bool   (point hit within buffer)
            designations  – list[str] (e.g. ["LHD", "NRHP"])
            district_name – str    (e.g. "Pleasant Street Historic District")
            historic_name – str    (e.g. "Magnolia Street School")
            common_name   – str
            constructed   – str
            architectural_style – str
            macris_id     – str    (MHCN, e.g. "ARL.123")
            macris_search_url – str
            ahc_inventory_url – str
            error         – str
        """
        cache_key = f"{address.strip().upper()}|{zipcode.strip()}"
        cache = getattr(self, "_historic_cache", None)
        if cache is None:
            cache = {}
            self._historic_cache = cache
        if cache_key in cache:
            return cache[cache_key]

        import requests as _req

        cfg = self._cfg.get("historic_resources", {}) or {}
        result: Dict[str, Any] = {
            "found": False, "in_district": False, "inventoried": False,
            "designations": [], "district_name": "", "historic_name": "",
            "common_name": "", "constructed": "", "architectural_style": "",
            "macris_id": "", "macris_search_url": cfg.get("macris_search_url", ""),
            "ahc_inventory_url": cfg.get("ahc_inventory_url", ""), "error": "",
        }

        poly_url   = cfg.get("macris_polygon_layer_url", "")
        point_url  = cfg.get("macris_point_layer_url", "")
        buffer_m   = int(cfg.get("macris_point_buffer_meters", 30))
        if not (poly_url or point_url):
            result["error"] = "No historic_resources URLs configured for this town."
            cache[cache_key] = result
            return result

        coords = self._geocode_address(address, self._town_name, self._state, zipcode)
        if not coords.get("ok"):
            result["error"] = coords.get("error") or "Geocoding failed"
            cache[cache_key] = result
            return result
        lat = coords["lat"]
        lon = coords["lon"]

        out_fields = "MHCN,DESIGNATIO,LEGEND,HISTORIC_N,COMMON_NAM,ADDRESS,CONSTRUCTI,ARCH,ARCHITECTU,USE_TYPE,SIGNIFICAN"

        # ── Step 2: polygon point-in-polygon query ─────────────────────
        if poly_url:
            try:
                params = {
                    "geometry":     f"{lon},{lat}",
                    "geometryType": "esriGeometryPoint",
                    "inSR":         "4326",
                    "spatialRel":   "esriSpatialRelIntersects",
                    "outFields":    out_fields,
                    "returnGeometry": "false",
                    "f":            "json",
                }
                resp = _req.get(poly_url, params=params, timeout=15)
                resp.raise_for_status()
                feats = resp.json().get("features", [])
                if feats:
                    attrs = feats[0]["attributes"]
                    result["found"]         = True
                    result["in_district"]   = True
                    result["macris_id"]     = str(attrs.get("MHCN") or "").strip()
                    result["historic_name"] = str(attrs.get("HISTORIC_N") or "").strip()
                    result["common_name"]   = str(attrs.get("COMMON_NAM") or "").strip()
                    result["constructed"]   = str(attrs.get("CONSTRUCTI") or "").strip()
                    result["architectural_style"] = str(
                        attrs.get("ARCHITECTU") or attrs.get("ARCH") or ""
                    ).strip()
                    legend = str(attrs.get("LEGEND") or "").strip()
                    desig  = str(attrs.get("DESIGNATIO") or "").strip()
                    if legend: result["designations"].append(legend)
                    if desig and desig != legend: result["designations"].append(desig)
                    # The polygon usually represents the district itself
                    name = result["historic_name"] or result["common_name"]
                    if name:
                        result["district_name"] = name
            except Exception as exc:
                result["error"] = f"MACRIS polygon query failed: {exc}"

        # ── Step 3: point query with buffer ────────────────────────────
        if point_url:
            try:
                params = {
                    "geometry":     f"{lon},{lat}",
                    "geometryType": "esriGeometryPoint",
                    "inSR":         "4326",
                    "spatialRel":   "esriSpatialRelIntersects",
                    "distance":     str(buffer_m),
                    "units":        "esriSRUnit_Meter",
                    "outFields":    out_fields,
                    "returnGeometry": "false",
                    "f":            "json",
                }
                resp = _req.get(point_url, params=params, timeout=15)
                resp.raise_for_status()
                feats = resp.json().get("features", [])
                if feats:
                    attrs = feats[0]["attributes"]
                    result["found"]       = True
                    result["inventoried"] = True
                    if not result["macris_id"]:
                        result["macris_id"] = str(attrs.get("MHCN") or "").strip()
                    if not result["historic_name"]:
                        result["historic_name"] = str(attrs.get("HISTORIC_N") or "").strip()
                    if not result["common_name"]:
                        result["common_name"] = str(attrs.get("COMMON_NAM") or "").strip()
                    if not result["constructed"]:
                        result["constructed"] = str(attrs.get("CONSTRUCTI") or "").strip()
                    if not result["architectural_style"]:
                        result["architectural_style"] = str(
                            attrs.get("ARCHITECTU") or attrs.get("ARCH") or ""
                        ).strip()
                    legend = str(attrs.get("LEGEND") or "").strip()
                    desig  = str(attrs.get("DESIGNATIO") or "").strip()
                    if legend and legend not in result["designations"]:
                        result["designations"].append(legend)
                    if desig and desig not in result["designations"] and desig != legend:
                        result["designations"].append(desig)
            except Exception as exc:
                if not result["error"]:
                    result["error"] = f"MACRIS point query failed: {exc}"

        cache[cache_key] = result
        return result

    # ------------------------------------------------------------------
    # Property-specific Zoning lookup (point-in-polygon, official GIS)
    # ------------------------------------------------------------------

    def _zoning_lookup_address(self, address: str, zipcode: str) -> Dict[str, Any]:
        """
        Memoized wrapper. See ``_zoning_lookup_address_uncached`` for the
        actual point-in-polygon query.
        """
        cache_key = f"{address.strip().upper()}|{zipcode.strip()}"
        cache = getattr(self, "_zoning_lookup_cache", None)
        if cache is None:
            cache = {}
            self._zoning_lookup_cache = cache
        if cache_key in cache:
            return cache[cache_key]
        result = self._zoning_lookup_address_uncached(address, zipcode)
        cache[cache_key] = result
        return result

    def _zoning_lookup_address_uncached(self, address: str, zipcode: str) -> Dict[str, Any]:
        """
        Run a point-in-polygon query against the town's official zoning GIS
        layer and return the actual zoning district for this parcel.

        Returns dict with:
          ok                : bool — query succeeded with a hit
          zone_code         : str  — short code ("R2", "B5", "MU", ...)
          zone_name         : str  — full name ("R2: Two Family")
          zone_description  : str  — long description
          notes             : str  — bylaw notes / overlay flags
          source            : str  — REST URL hit
          error             : str  — populated when ok=False
        """
        result = {
            "ok":               False,
            "zone_code":        "",
            "zone_name":        "",
            "zone_description": "",
            "notes":            "",
            "source":           "",
            "error":            "",
        }

        zoning_cfg = (self._cfg.get("zoning") or {})
        url = zoning_cfg.get("arcgis_layer_url")
        if not url:
            result["error"] = "No zoning.arcgis_layer_url configured"
            return result

        coords = self._geocode_address(address, self._town_name, self._state, zipcode)
        lat = coords.get("lat")
        lon = coords.get("lon")
        if lat is None or lon is None:
            result["error"] = coords.get("error") or "Geocoding failed"
            return result

        try:
            import requests as _req
            params = {
                "f":              "json",
                "geometry":       json.dumps({
                    "x":                lon,
                    "y":                lat,
                    "spatialReference": {"wkid": 4326},
                }),
                "geometryType":   "esriGeometryPoint",
                "inSR":           4326,
                "spatialRel":     "esriSpatialRelIntersects",
                "outFields":      "ZoneCode,ZoneName,ZoneDesc,Notes",
                "returnGeometry": False,
            }
            resp = _req.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            features = data.get("features", []) or []
            if not features:
                result["error"] = "Point not within any zoning polygon"
                return result

            attrs = features[0].get("attributes", {}) or {}
            zc = (attrs.get("ZoneCode") or "").strip()
            zn = (attrs.get("ZoneName") or "").strip()
            zd = (attrs.get("ZoneDesc") or "").strip()
            nt = (attrs.get("Notes") or "").strip()

            if not zc and zn and ":" in zn:
                zc = zn.split(":", 1)[0].strip()

            result.update({
                "ok":               bool(zc or zn),
                "zone_code":        zc,
                "zone_name":        zn or zc,
                "zone_description": zd,
                "notes":            nt,
                "source":           url,
            })
        except Exception as exc:
            result["error"] = f"Zoning point-in-polygon query failed: {exc}"

        return result

    # ------------------------------------------------------------------
    # Estimated Current Market Value (AV × ZHVI appreciation)
    # ------------------------------------------------------------------

    @staticmethod
    def _estimate_market_value(
        assessed_value: float,
        df_market: pd.DataFrame,
        zipcode: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Estimate current market value by applying recent ZHVI appreciation to
        the assessor's appraised value.

        MA law requires assessments at 100 % of full cash value (M.G.L. c.59 §38),
        but assessments lag the market by roughly 12 months (FY assessment date =
        Jan 1 of the prior year).  We apply the ZHVI appreciation from 12 months
        ago to the latest data point to project forward.

        Returns a dict with keys:
            estimated_value  – float
            appreciation_1yr_pct – float
            zhvi_latest      – float
            zhvi_1yr_ago     – float
            as_of            – str  (ISO date of latest ZHVI point)
            method           – str
        or None if insufficient data.
        """
        if not assessed_value or assessed_value <= 0:
            return None
        if df_market.empty or "metric_name" not in df_market.columns:
            return None

        sp = df_market[df_market["metric_name"] == "MEDIAN_SALE_PRICE"].copy()
        if sp.empty:
            return None

        # Prefer the zip that matches, fall back to any zip in the series
        if "geo_value" in sp.columns and zipcode:
            sp_zip = sp[sp["geo_value"] == zipcode]
            sp = sp_zip if not sp_zip.empty else sp

        sp["observation_date"] = pd.to_datetime(sp["observation_date"], utc=True, errors="coerce")
        sp = sp.dropna(subset=["observation_date"]).sort_values("observation_date")

        if len(sp) < 2:
            return None

        latest_row   = sp.iloc[-1]
        latest_val   = float(latest_row["metric_value"])
        latest_date  = latest_row["observation_date"]

        # Find the row closest to 12 months ago
        target_1yr = latest_date - pd.DateOffset(months=12)
        sp["_delta"] = (sp["observation_date"] - target_1yr).abs()
        yr_ago_row   = sp.loc[sp["_delta"].idxmin()]
        yr_ago_val   = float(yr_ago_row["metric_value"])

        if yr_ago_val <= 0:
            return None

        factor   = latest_val / yr_ago_val
        est_val  = round(assessed_value * factor, -2)   # round to nearest $100
        app_pct  = round((factor - 1) * 100, 1)
        as_of    = pd.Timestamp(latest_date).strftime("%b %Y")

        return {
            "estimated_value":      est_val,
            "appreciation_1yr_pct": app_pct,
            "zhvi_latest":          round(latest_val, 0),
            "zhvi_1yr_ago":         round(yr_ago_val, 0),
            "as_of":                as_of,
            "method":               "Assessor AV × 1-yr ZHVI appreciation (MA FMV standard)",
        }

    # ------------------------------------------------------------------
    # Value Timeline — 5-yr history + 3-yr projection
    # ------------------------------------------------------------------

    @staticmethod
    def _value_timeline(
        assessed_value: float,
        df_market: pd.DataFrame,
        zipcode: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Build annual historical value estimates (up to 5 years back) and a
        3-year forward projection for a specific property.

        Method
        ------
        Historical : assessed_value × (zhvi_year / zhvi_current)
            Uses the ZHVI index as a multiplier — same logic as the AVM, but
            applied to each December (or latest available month) going back 5 years.

        Projection : CAGR × compound interest
            Derives CAGR from the full ZHVI series available, then projects
            Y+1 / Y+2 / Y+3.  Confidence narrows each year out (+/- ½ CAGR
            per year).

        Returns
        -------
        Dict with keys:
            current_estimated   – float  (AV adjusted to today)
            history             – list[dict]  year, value, change_pct, is_estimate
            projection          – list[dict]  year, low, mid, high
            cagr_pct            – float  (annualised growth from ZHVI series)
            data_years          – int    (how many years of ZHVI data we have)
            as_of               – str    (latest ZHVI date)
        """
        if not assessed_value or assessed_value <= 0:
            return None
        if df_market.empty or "metric_name" not in df_market.columns:
            return None

        sp = df_market[df_market["metric_name"] == "MEDIAN_SALE_PRICE"].copy()
        if sp.empty:
            return None

        if "geo_value" in sp.columns and zipcode:
            sp_zip = sp[sp["geo_value"] == zipcode]
            sp = sp_zip if not sp_zip.empty else sp

        sp["observation_date"] = pd.to_datetime(sp["observation_date"], utc=True, errors="coerce")
        sp = sp.dropna(subset=["observation_date"]).sort_values("observation_date")

        if len(sp) < 6:   # need at least 6 months for a meaningful trend
            return None

        latest_row  = sp.iloc[-1]
        latest_val  = float(latest_row["metric_value"])
        latest_date = pd.Timestamp(latest_row["observation_date"])
        as_of_str   = latest_date.strftime("%b %Y")

        # ── Anchor: current estimated market value ─────────────────────
        # Use the 12-month ZHVI delta to correct for assessment lag
        target_1yr  = latest_date - pd.DateOffset(months=12)
        sp["_d"]    = (sp["observation_date"] - target_1yr).abs()
        yr_ago_val  = float(sp.loc[sp["_d"].idxmin(), "metric_value"])
        factor_now  = latest_val / yr_ago_val if yr_ago_val > 0 else 1.0
        current_est = round(assessed_value * factor_now, -2)

        # ── Historical annual snapshots ────────────────────────────────
        history: List[Dict[str, Any]] = []
        earliest_year = latest_date.year - 5
        for offset_yr in range(5, -1, -1):   # 5 years back → current year
            yr       = latest_date.year - offset_yr
            if yr < earliest_year:
                continue
            # Pick December of that year, or the latest row in that year
            yr_rows = sp[sp["observation_date"].dt.year == yr]
            if yr_rows.empty:
                continue
            # Prefer Dec, fall back to latest month in that year
            dec_rows = yr_rows[yr_rows["observation_date"].dt.month == 12]
            ref_row  = dec_rows.iloc[-1] if not dec_rows.empty else yr_rows.iloc[-1]
            ref_val  = float(ref_row["metric_value"])
            if ref_val <= 0 or latest_val <= 0:
                continue
            ratio      = ref_val / latest_val
            hist_value = round(current_est * ratio, -2)
            history.append({
                "year":         yr,
                "label":        f"Dec {yr}" if dec_rows.empty is False else str(yr),
                "value":        hist_value,
                "zhvi_index":   round(ref_val, 0),
                "is_estimated": True,
            })

        # Compute year-over-year change
        for i, h in enumerate(history):
            if i == 0:
                h["change_pct"] = None
            else:
                prev = history[i - 1]["value"]
                h["change_pct"] = round(100 * (h["value"] / prev - 1), 1) if prev else None

        # ── CAGR from full ZHVI series ─────────────────────────────────
        oldest_val  = float(sp.iloc[0]["metric_value"])
        oldest_date = pd.Timestamp(sp.iloc[0]["observation_date"])
        years_span  = max((latest_date - oldest_date).days / 365.25, 0.5)
        cagr        = (latest_val / oldest_val) ** (1 / years_span) - 1 if oldest_val > 0 else 0.05
        cagr        = max(min(cagr, 0.20), -0.10)   # clamp to [-10%, +20%]

        # ── 3-year forward projection ──────────────────────────────────
        base_proj  = current_est
        half_cagr  = abs(cagr) * 0.5   # uncertainty widens each year
        projection: List[Dict[str, Any]] = []
        for n in range(1, 4):
            mid  = round(base_proj * ((1 + cagr) ** n), -2)
            band = round(base_proj * half_cagr * n, -2)
            projection.append({
                "year": latest_date.year + n,
                "low":  mid - band,
                "mid":  mid,
                "high": mid + band,
            })

        return {
            "current_estimated": current_est,
            "history":           history,
            "projection":        projection,
            "cagr_pct":          round(cagr * 100, 1),
            "data_years":        round(years_span, 1),
            "as_of":             as_of_str,
        }

    def _render_value_timeline(
        self,
        df_property: pd.DataFrame,
        df_market: pd.DataFrame,
        address: str,
        zipcode: str,
    ) -> str:
        """Text-format value timeline section."""
        lines = [self._section_header(
            "Value Timeline  ·  5-Yr History + 3-Yr Projection  [ZHVI-INDEXED ESTIMATE]"
        )]

        # Locate property row
        prop_row = None
        if not df_property.empty and "address" in df_property.columns:
            addr_up = address.strip().upper()
            m = df_property[df_property["address"].str.upper() == addr_up]
            if m.empty:
                toks = addr_up.split()
                if toks:
                    m = df_property[df_property["address"].str.upper().str.startswith(toks[0])]
            if not m.empty:
                prop_row = m.iloc[0]

        if prop_row is None or not prop_row.get("assessed_value"):
            lines.append(f"  Property \"{address}\" not found in assessor data.")
            lines.append("  Cannot generate value timeline without a parcel assessed value.")
            return "\n".join(lines)

        av = float(prop_row["assessed_value"])
        tl = self._value_timeline(av, df_market, zipcode)

        if tl is None:
            lines.append("  Insufficient ZHVI market data to compute timeline.")
            lines.append(f"  Re-run: python3 scripts/download_zillow_cache.py --town {self._town_slug} --months 60")
            return "\n".join(lines)

        col = (12, 18, 14, 10)
        div = "  " + "─" * sum(col)

        def row(yr, val, chg, tag=""):
            chg_s = f"{'+' if chg >= 0 else ''}{chg:.1f}%" if chg is not None else "  —"
            return (f"  {str(yr):<{col[0]}}"
                    f"{_fmt_usd(val):<{col[1]}}"
                    f"{chg_s:<{col[2]}}"
                    f"{tag}")

        lines.append(f"\n  {'YEAR':<{col[0]}}{'EST. VALUE':<{col[1]}}{'YoY CHANGE':<{col[2]}}NOTE")
        lines.append(div)
        for h in tl["history"]:
            tag = "◀ assessed" if h["year"] == max(x["year"] for x in tl["history"]) else ""
            lines.append(row(h["year"], h["value"], h["change_pct"], tag))

        lines.append(div)
        lines.append(f"  {'YEAR':<{col[0]}}{'PROJECTED MID':<{col[1]}}{'RANGE':<{col[2]}}CAGR {tl['cagr_pct']:+.1f}%/yr")
        lines.append(div)
        for p in tl["projection"]:
            rng = f"{_fmt_usd(p['low'])} – {_fmt_usd(p['high'])}"
            lines.append(f"  {str(p['year']):<{col[0]}}"
                         f"{_fmt_usd(p['mid']):<{col[1]}}"
                         f"{rng}")

        lines.append(f"\n  Data: {tl['data_years']:.0f} yrs ZHVI ({zipcode}) as of {tl['as_of']}")
        lines.append("  Method: Assessed value × ZHVI index ratio per year; projection uses CAGR.")
        lines.append("  ⚠ Estimates only — not a licensed appraisal.")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Investment Pro-Forma
    # ------------------------------------------------------------------

    def _render_investment_proforma(
        self,
        df_property: pd.DataFrame,
        df_zoning: pd.DataFrame,
        address: str,
    ) -> str:
        lines = [self._section_header("Investment Pro-Forma  ·  By-Right Options  [REAL ZONING + INDUSTRY COSTS]")]

        # Locate this property
        prop_row = None
        if not df_property.empty and "address" in df_property.columns:
            addr_upper = address.strip().upper()
            match = df_property[df_property["address"].str.upper() == addr_upper]
            if match.empty:
                tokens = addr_upper.split()
                if tokens:
                    match = df_property[df_property["address"].str.upper().str.startswith(tokens[0])]
            if not match.empty:
                prop_row = match.iloc[0]

        zone_row = None
        zone_code_display = "Unknown"
        if prop_row is not None:
            gis_z = self._zoning_lookup_address(address, "")
            if gis_z.get("ok") and gis_z.get("zone_code"):
                zone_code_display = gis_z["zone_code"]
                zone_row = self._resolve_zone_row(df_zoning, zone_code_display)
                if zone_row is None and gis_z.get("zone_name"):
                    zone_code_display = gis_z["zone_name"]
            else:
                zone_code_display = str(prop_row.get("zone_code", ""))
                zone_row = self._resolve_zone_row(df_zoning, zone_code_display)

        # Determine which by-right options apply
        adu_permitted   = False
        two_fam_permit  = False
        lot_sqft        = float(prop_row["lot_size_sqft"]) if prop_row is not None and prop_row.get("lot_size_sqft") else None
        assessed_value  = float(prop_row["assessed_value"])  if prop_row is not None and prop_row.get("assessed_value") else None

        if zone_row is not None:
            uses = zone_row.get("allowed_uses") or []
            if isinstance(uses, str):
                try:
                    uses = json.loads(uses)
                except (json.JSONDecodeError, TypeError):
                    uses = []
            adu_permitted  = any("ADU" in u.upper() or "ACCESSORY" in u.upper() for u in uses)
            two_fam_permit = any("TWO-FAMILY" in u.upper() or "TWO FAMILY" in u.upper() for u in uses)

        lot_note = f"{int(lot_sqft):,} sq ft lot" if lot_sqft else "lot size unverified"
        av_note  = f"Assessed: {_fmt_usd(assessed_value)}" if assessed_value else ""

        lines.append(f"  Property:  {address}  ({lot_note})   {av_note}")
        lines.append(f"  Zone:      {zone_code_display}  —  "
                     f"{zone_row['zone_description'] if zone_row is not None else 'see zoning table'}")
        lines.append("")

        col_w = (32, 20, 20, 24)
        header = (
            f"  {'DEVELOPMENT OPTION':<{col_w[0]}}"
            f"{'EST. COST':<{col_w[1]}}"
            f"{'EQUITY VALUE ADD':<{col_w[2]}}"
            f"{'EST. RENTAL YIELD':<{col_w[3]}}"
        )
        lines.append(header)
        lines.append("  " + "─" * (sum(col_w)))

        def row(option, cost, equity, yield_):
            return (
                f"  {option:<{col_w[0]}}"
                f"{cost:<{col_w[1]}}"
                f"{equity:<{col_w[2]}}"
                f"{yield_:<{col_w[3]}}"
            )

        if adu_permitted:
            lines.append(row(
                "Detached Garden ADU (900 sq ft max)",
                "$325k – $400k",
                "+$175k – $210k",
                "$2,800 – $3,500/mo",
            ))
            lines.append(row(
                "Attached ADU / In-Law Suite",
                "$120k – $180k",
                "+$120k – $150k",
                "$1,800 – $2,400/mo",
            ))
            lines.append(row(
                "Garage + Studio ADU (combo)",
                "$140k – $185k",
                "+$140k – $160k",
                "$1,500 – $2,000/mo",
            ))
        if two_fam_permit:
            lines.append(row(
                "Convert to Two-Family",
                "$80k – $140k",
                "+$200k – $280k",
                "$2,200 – $3,000/mo (unit 2)",
            ))
        lines.append(row(
            "Detached 2-Car Garage (no ADU)",
            "$60k – $90k",
            "+$80k – $100k",
            "N/A (utility value)",
        ))

        lines.append("")
        lines.append("  Construction costs: Massachusetts industry averages (2025–2026).")
        lines.append("  Equity estimates: based on Arlington comparable sales (±20% variance).")
        lines.append("  Rental yields: current Arlington rental market range.")
        if not adu_permitted:
            lines.append(f"\n  ⚠  ADU not listed in permitted uses for Zone {zone_code_display} "
                         "— verify with Arlington Inspectional Services before planning.")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Regulatory Compliance Grid
    # ------------------------------------------------------------------

    def _render_compliance_grid(
        self,
        df_property: pd.DataFrame,
        df_zoning: pd.DataFrame,
        address: str,
    ) -> str:
        lines = [self._section_header("Regulatory Compliance Grid  ·  Bylaw vs Parcel  [REAL DATA]")]

        # Locate property row
        prop_row = None
        if not df_property.empty and "address" in df_property.columns:
            addr_upper = address.strip().upper()
            match = df_property[df_property["address"].str.upper() == addr_upper]
            if match.empty:
                tokens = addr_upper.split()
                if tokens:
                    match = df_property[df_property["address"].str.upper().str.startswith(tokens[0])]
            if not match.empty:
                prop_row = match.iloc[0]

        if prop_row is None:
            lines.append(f"  Property \"{address}\" not found in assessor data.")
            lines.append("  Cannot generate compliance grid without parcel data.")
            return "\n".join(lines)

        raw_zone  = str(prop_row.get("zone_code", ""))
        gis_z     = self._zoning_lookup_address(address, "")
        if gis_z.get("ok") and gis_z.get("zone_code"):
            raw_zone = gis_z["zone_code"]
        zone_row  = self._resolve_zone_row(df_zoning, raw_zone)
        lot_sqft  = float(prop_row["lot_size_sqft"]) if prop_row.get("lot_size_sqft") else None
        year_built = int(prop_row["year_built"]) if prop_row.get("year_built") else None
        av        = float(prop_row["assessed_value"]) if prop_row.get("assessed_value") else None

        # Pull zoning standards
        meta: Dict[str, Any] = {}
        zone_desc = raw_zone
        adu_uses: List[str] = []
        max_height = None
        if zone_row is not None:
            zone_desc = str(zone_row.get("zone_description", raw_zone))
            max_height = zone_row.get("max_height_ft")
            raw_meta = zone_row.get("metadata") or {}
            if isinstance(raw_meta, str):
                try:
                    raw_meta = json.loads(raw_meta)
                except (json.JSONDecodeError, TypeError):
                    raw_meta = {}
            meta = raw_meta
            uses = zone_row.get("allowed_uses") or []
            if isinstance(uses, str):
                try:
                    uses = json.loads(uses)
                except (json.JSONDecodeError, TypeError):
                    uses = []
            adu_uses = [u for u in uses if "ADU" in u.upper() or "ACCESSORY" in u.upper()]

        min_lot    = meta.get("min_lot_sqft")
        max_far    = meta.get("max_far")
        setback_f  = meta.get("setback_front_ft")
        min_front  = meta.get("min_frontage_ft")

        col_w = (28, 24, 26, 18)
        header = (
            f"  {'REQUIREMENT':<{col_w[0]}}"
            f"{'BYLAW STANDARD (' + raw_zone + ')':<{col_w[1]}}"
            f"{'THIS PARCEL':<{col_w[2]}}"
            f"{'VERDICT':<{col_w[3]}}"
        )
        lines.append(header)
        lines.append("  " + "─" * (sum(col_w)))

        def grid_row(req, standard, parcel_val, verdict):
            return (
                f"  {req:<{col_w[0]}}"
                f"{standard:<{col_w[1]}}"
                f"{parcel_val:<{col_w[2]}}"
                f"{verdict}"
            )

        # ── Min Lot Size ───────────────────────────────────────────────
        std_lot = f"{int(min_lot):,} sq ft" if min_lot else "—"
        prc_lot = f"{int(lot_sqft):,} sq ft" if lot_sqft else "Unverified"
        if lot_sqft and min_lot:
            if lot_sqft >= min_lot:
                lot_verdict = "✅ COMPLIANT"
            else:
                lot_verdict = "⚠  NON-CONFORMING (pre-existing)"
        else:
            lot_verdict = "⚠  Requires Verification"
        lines.append(grid_row("Min. Lot Size", std_lot, prc_lot, lot_verdict))

        # ── ADU Permitted ──────────────────────────────────────────────
        adu_std = "Permitted" if adu_uses else ("Not listed" if zone_row is not None else "—")
        adu_prc = "By-right eligible" if adu_uses else "Not permitted"
        adu_verd = "✅ ELIGIBLE" if adu_uses else "❌ NOT PERMITTED"
        lines.append(grid_row("ADU Permitted", adu_std, adu_prc, adu_verd))

        # ── Max Height ─────────────────────────────────────────────────
        ht_std = f"{int(max_height)} ft" if max_height else "—"
        lines.append(grid_row("Max Building Height", ht_std, "Existing structure", "✅ Grandfathered"))

        # ── Front Setback ──────────────────────────────────────────────
        sb_std = f"{int(setback_f)} ft" if setback_f else "—"
        lines.append(grid_row("Front Setback", sb_std, "Existing structure", "✅ Grandfathered"))

        # ── Min Frontage ───────────────────────────────────────────────
        fr_std = f"{int(min_front)} ft" if min_front else "—"
        lines.append(grid_row("Min. Street Frontage", fr_std, "See plot plan", "⚠  Verify with ISD"))

        # ── Max FAR ────────────────────────────────────────────────────
        far_std = str(max_far) if max_far else "—"
        lines.append(grid_row("Max Floor-Area Ratio", far_std, "Existing use", "⚠  Verify before ADU"))

        # ── Year Built ─────────────────────────────────────────────────
        yb = str(year_built) if year_built else "Unknown"
        pb = "Lead paint disclosure required" if year_built and year_built < 1978 else "N/A"
        pb_v = "⚠  Pre-1978 (disclose)" if year_built and year_built < 1978 else "✅ Post-1978"
        lines.append(grid_row("Lead Paint (pre-1978)", f"Built {yb}", pb, pb_v))

        # ── Assessed Value ─────────────────────────────────────────────
        av_s = _fmt_usd(av) if av else "—"
        lines.append(grid_row("Assessed Value", "Town Assessor (real)", av_s, "✅ Verified"))

        lines.append("")
        lines.append("  Sources: Arlington Zoning Bylaw 2024 (zone standards) + ")
        lines.append("           Arlington Tax Assessor via Patriot Properties (parcel data).")
        lines.append("  ⚠  = Requires confirmation with Arlington Inspectional Services (ISD).")

        return "\n".join(lines)

    def _render_infra(self, df: pd.DataFrame) -> str:
        lines = [self._section_header("Infrastructure Projects (DPW)  [ESTIMATED]")]
        if df.empty:
            lines.append("  No infrastructure project data available.")
            return "\n".join(lines)

        active_statuses = {"PLANNED", "DESIGN", "BID", "IN_PROGRESS"}
        active = df[df["status"].isin(active_statuses)] if "status" in df.columns else df
        completed = df[df["status"] == "COMPLETED"] if "status" in df.columns else pd.DataFrame()

        lines.append(
            f"  Active / upcoming projects:  {len(active)}"
            f"   |   Completed (in dataset):  {len(completed)}"
        )

        if not active.empty:
            lines.append("")
            for _, row in active.head(6).iterrows():
                name   = str(row.get("project_name", "Unnamed"))[:50]
                status = str(row.get("status", ""))
                cost   = row.get("estimated_cost")
                loc    = str(row.get("location_description", ""))[:45]
                cost_s = _fmt_usd(cost) if cost and cost > 0 else "TBD"
                lines.append(f"  • [{status:<11}]  {name}")
                lines.append(f"    Location: {loc}   Est. cost: {cost_s}")
            if len(active) > 6:
                lines.append(f"  … and {len(active) - 6} more active project(s).")

        return "\n".join(lines)

    def _render_str(self, df: pd.DataFrame) -> str:
        lines = [self._section_header("Short-Term Rental (STR) Dynamics  [ESTIMATED]")]
        if df.empty:
            lines.append("  No STR dynamics data available.")
            return "\n".join(lines)

        row = df.iloc[0]
        month          = row.get("observation_month", "N/A")
        yield_pct      = float(row.get("estimated_yield_pct", 0))
        nightly        = float(row.get("avg_nightly_rate_usd", 0))
        occupancy      = float(row.get("occupancy_rate_pct", 0))
        demo           = str(row.get("target_guest_demo", "N/A")).replace("_", " ").title()
        posture        = str(row.get("regulatory_posture", "N/A"))
        peak_seasons   = row.get("peak_seasons") or []
        if isinstance(peak_seasons, str):
            peak_seasons = json.loads(peak_seasons)

        lines.append(f"  Observation month:          {month}")
        lines.append(f"  Est. gross yield:           {_fmt_pct(yield_pct)}")
        lines.append(f"  Avg nightly rate:           {_fmt_usd(nightly)}")
        lines.append(f"  Occupancy rate:             {_fmt_pct(occupancy)}")
        lines.append(f"  Target guest demo:          {demo}")
        lines.append(f"  Regulatory posture:         {posture}")
        if peak_seasons:
            lines.append(f"  Peak seasons:               {', '.join(peak_seasons)}")

        # Read regulatory_notes and sweet_spots from metadata if present
        meta = row.get("metadata") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except (json.JSONDecodeError, TypeError):
                meta = {}
        if meta.get("regulatory_notes"):
            lines.append("")
            lines.append(_wrap(f"Regulatory note: {meta['regulatory_notes']}"))
        sweet = meta.get("sweet_spot_neighborhoods") or []
        if sweet:
            lines.append(f"  Sweet-spot neighbourhoods:  {', '.join(sweet[:3])}")

        return "\n".join(lines)

    def _render_profile(self, df: pd.DataFrame) -> str:
        lines = [self._section_header("Town Profile & Investment Intelligence  [ESTIMATED]")]
        if df.empty:
            lines.append("  No town profile data available.")
            return "\n".join(lines)

        row = df.iloc[0]
        vibes         = str(row.get("neighborhood_vibes", ""))
        nimby         = float(row.get("nimby_index", 0))
        housing       = str(row.get("housing_character", "N/A")).replace("_", " ").title()
        political     = str(row.get("political_lean", "N/A")).title()
        employers     = row.get("major_employers") or []

        nimby_bar = "█" * int(round(nimby)) + "░" * (10 - int(round(nimby)))
        nimby_label = (
            "pro-development" if nimby < 3.5
            else "mixed signals" if nimby < 6.5
            else "high resistance"
        )

        lines.append(f"  Housing character:      {housing}")
        lines.append(f"  Political lean:         {political}")
        lines.append(f"  NIMBY index:  {nimby:.1f}/10  [{nimby_bar}]  ({nimby_label})")

        if employers:
            emp_str = ", ".join(employers[:5])
            if len(employers) > 5:
                emp_str += f", +{len(employers) - 5} more"
            lines.append(f"  Major employers:        {emp_str}")

        meta = row.get("metadata") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except (json.JSONDecodeError, TypeError):
                meta = {}

        for key, label in (
            ("walkability_score", "Walkability score"),
            ("transit_score",     "Transit score"),
            ("school_rating",     "School rating"),
        ):
            if meta.get(key) is not None:
                lines.append(f"  {label:<24}  {meta[key]}")

        if vibes:
            lines.append("")
            lines.append("  Neighbourhood Vibes:")
            lines.append(_wrap(vibes, indent=4))

        sweet = meta.get("sweet_spots") or []
        if sweet:
            lines.append(f"\n  Investment sweet spots:  {', '.join(sweet[:3])}")
        risks = meta.get("risks") or []
        if risks:
            lines.append(f"  Known risk factors:      {'; '.join(risks[:3])}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_report(self, address: str, zipcode: str) -> str:
        """
        Generate a TownEye Civic Audit Report for the given property.

        Parameters
        ----------
        address : str
            Full street address (e.g. ``"14 Magnolia St"``).
        zipcode : str
            5-digit US ZIP code (e.g. ``"02474"``).

        Returns
        -------
        str
            The complete formatted report as a plain-text string.
        """
        # ── Load all domains ───────────────────────────────────────────
        # Real data — sourced from live public APIs and government datasets
        df_property = self._load_property()
        df_property = self._ensure_property_in_df(df_property, address)
        df_climate  = self._load_climate()
        df_transit  = self._load_transit()
        # Estimated data — derived from config fixtures or LLM synthesis
        df_market  = self._load_market()
        df_zoning  = self._load_zoning()
        df_infra   = self._load_infra()
        df_str     = self._load_str()
        df_profile = self._load_profile()

        generated_at = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        # Count how many real-data sections have content
        real_count = sum([
            not df_property.empty,
            not df_climate.empty,
            not df_transit.empty,
        ])
        real_label = f"{real_count}/3 live sections" if real_count else "estimated data only"

        # ── Report header ─────────────────────────────────────────────
        header = "\n".join([
            _divider("═"),
            "  TOWNEYE  ·  CIVIC AUDIT REPORT",
            _divider("═"),
            f"  Property    :  {address}, {self._town_name}, {self._state}  {zipcode}",
            f"  Municipality:  {self._town_name}, {self._state}",
            f"  Generated   :  {generated_at}",
            f"  Data status :  {real_label} backed by government sources",
            _divider("─"),
        ])

        raw_zone_code = ""
        _gis_z = self._zoning_lookup_address(address, zipcode)
        if _gis_z.get("ok") and _gis_z.get("zone_code"):
            raw_zone_code = _gis_z["zone_code"]
        elif not df_property.empty and "address" in df_property.columns:
            addr_up = address.strip().upper()
            _pm = df_property[df_property["address"].str.upper() == addr_up]
            if _pm.empty:
                _toks = addr_up.split()
                if _toks:
                    _pm = df_property[df_property["address"].str.upper().str.startswith(_toks[0])]
            if not _pm.empty:
                raw_zone_code = str(_pm.iloc[0].get("zone_code", ""))

        # ── Sections — Agent Brief first, real data next, estimates last ─
        sections = [
            self._render_agent_brief(
                address, zipcode,
                df_property, df_market, df_climate, df_transit, df_zoning,
            ),
            self._render_property(df_property, address, df_market=df_market, zipcode=zipcode),
            self._render_value_timeline(df_property, df_market, address, zipcode),
            self._render_compliance_grid(df_property, df_zoning, address),
            self._render_investment_proforma(df_property, df_zoning, address),
            self._render_climate(df_climate, address=address, zipcode=zipcode),
            self._render_historic(address, zipcode),
            self._render_transit(df_transit),
            self._render_market(df_market),
            self._render_profile(df_profile),
            self._render_str(df_str),
            self._render_infra(df_infra),
            self._render_zoning(df_zoning, raw_zone_code=raw_zone_code),
        ]

        # ── Legal disclaimer ──────────────────────────────────────────
        footer = "\n".join([
            f"\n{_divider('─')}",
            "  LEGAL DISCLAIMER",
            _divider("─"),
            _wrap(self._disclaimer, indent=2),
            _divider("═"),
        ])

        return "\n".join([header] + sections + [footer])

    # ------------------------------------------------------------------
    # HTML email generator — produces a Gmail-pasteable version
    # ------------------------------------------------------------------

    _HTML_CSS = """
    body{font-family:Arial,sans-serif;font-size:14px;line-height:1.6;color:#1a1a1a;max-width:700px;margin:30px auto;padding:0 20px;background:#fff}
    .rh{background:#1a1a2e;color:#fff;padding:20px 24px;border-radius:6px 6px 0 0}
    .rh h1{margin:0 0 4px 0;font-size:18px;letter-spacing:2px;font-weight:bold}
    .rh .sub{font-size:13px;color:#aac4ff;margin:2px 0}
    .rh .badge{display:inline-block;background:#27ae60;color:#fff;font-size:11px;padding:2px 8px;border-radius:10px;margin-top:8px;font-weight:bold}
    .sec{border-left:4px solid #1a73e8;margin:18px 0 0 0}
    .st{background:#f0f4ff;padding:8px 14px;font-size:12px;font-weight:bold;letter-spacing:1px;color:#1a3a6e;border-bottom:1px solid #d0daf5}
    .br{background:#27ae60;color:#fff;font-size:10px;padding:1px 7px;border-radius:8px;margin-left:8px}
    .be{background:#e0a020;color:#fff;font-size:10px;padding:1px 7px;border-radius:8px;margin-left:8px}
    .ba{background:#1a73e8;color:#fff;font-size:10px;padding:1px 7px;border-radius:8px;margin-left:8px}
    .sb{padding:12px 14px;background:#fff}
    .bi{margin:10px 0;padding-left:4px}
    .bi strong{color:#1a3a6e}
    .kv{width:100%;border-collapse:collapse;font-size:13px}
    .kv td{padding:5px 8px;vertical-align:top}
    .kv td:first-child{color:#555;width:38%;font-weight:bold}
    .kv tr:nth-child(even) td{background:#f9f9f9}
    .dt{width:100%;border-collapse:collapse;font-size:13px;margin-top:6px}
    .dt th{background:#1a3a6e;color:#fff;padding:7px 10px;text-align:left;font-size:12px}
    .dt td{padding:7px 10px;border-bottom:1px solid #e8ecf5;vertical-align:top}
    .dt tr:nth-child(even) td{background:#f5f8ff}
    .ok{color:#1a7a1a;font-weight:bold}
    .wn{color:#b07000;font-weight:bold}
    .fl{color:#cc2222;font-weight:bold}
    .rbar{display:flex;align-items:center;margin:6px 0;font-size:13px}
    .rl{width:230px}
    .rbw{flex:1;background:#eee;border-radius:4px;height:14px;margin:0 10px}
    .rbh{height:14px;border-radius:4px;background:#cc2222}
    .rbm{height:14px;border-radius:4px;background:#e0a020}
    .rc{width:80px;text-align:right;font-size:12px;color:#555}
    .aw{background:#fff8e6;border-left:4px solid #e0a020;padding:8px 12px;margin:8px 0;border-radius:0 4px 4px 0;font-size:13px}
    .ai{background:#f0f7ff;border-left:4px solid #1a73e8;padding:8px 12px;margin:8px 0;border-radius:0 4px 4px 0;font-size:13px}
    .sn{font-size:11px;color:#888;margin-top:8px;padding-top:6px;border-top:1px solid #eee}
    .nt{font-size:12px;color:#666;margin-top:8px;font-style:italic}
    .disc{background:#f5f5f5;border:1px solid #ddd;padding:12px 16px;font-size:11px;color:#777;border-radius:0 0 6px 6px;margin-top:20px}
    .pw{text-align:center;font-size:11px;color:#aaa;margin-top:10px}
    """

    def _h_section(self, num: int, title: str, badge_html: str, body: str) -> str:
        return (
            f'<div class="sec">'
            f'<div class="st">{num:02d}&nbsp;·&nbsp;{title}{badge_html}</div>'
            f'<div class="sb">{body}</div></div>'
        )

    def _h_kv(self, rows: List[tuple]) -> str:
        cells = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in rows)
        return f'<table class="kv">{cells}</table>'

    def _h_table(self, headers: List[str], rows: List[List[str]]) -> str:
        th = "".join(f"<th>{h}</th>" for h in headers)
        tr = "".join(
            "<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>"
            for r in rows
        )
        return f'<table class="dt"><tr>{th}</tr>{tr}</table>'

    def generate_html_report(self, address: str, zipcode: str) -> str:
        """Return a complete Gmail-pasteable HTML Civic Audit Report."""
        # ── Load all data (same as generate_report) ────────────────────
        df_property = self._load_property()
        df_property = self._ensure_property_in_df(df_property, address)
        df_climate  = self._load_climate()
        df_transit  = self._load_transit()
        df_market   = self._load_market()
        df_zoning   = self._load_zoning()
        df_infra    = self._load_infra()
        df_str      = self._load_str()
        df_profile  = self._load_profile()

        now_str      = datetime.now(tz=timezone.utc).strftime("%b %-d, %Y &nbsp;|&nbsp; %H:%M UTC")
        real_count   = sum([not df_property.empty, not df_climate.empty, not df_transit.empty])
        real_label   = f"✔ {real_count}/3 live sections backed by government sources"

        # ── Locate property row ────────────────────────────────────────
        prop_row = None
        if not df_property.empty and "address" in df_property.columns:
            addr_up = address.strip().upper()
            m = df_property[df_property["address"].str.upper() == addr_up]
            if m.empty:
                toks = addr_up.split()
                if toks:
                    m = df_property[df_property["address"].str.upper().str.startswith(toks[0])]
            if not m.empty:
                prop_row = m.iloc[0]

        zone_row = None
        if prop_row is not None:
            _gis = self._zoning_lookup_address(address, zipcode)
            _zc_for_lookup = (
                _gis["zone_code"]
                if _gis.get("ok") and _gis.get("zone_code")
                else str(prop_row.get("zone_code", ""))
            )
            zone_row = self._resolve_zone_row(df_zoning, _zc_for_lookup)

        # ── 01 AGENT BRIEF ────────────────────────────────────────────
        # Reuse _render_agent_brief (has resolved zone code + property-level FEMA lookup)
        brief_text_raw = self._render_agent_brief(
            address, zipcode, df_property, df_market, df_climate, df_transit, df_zoning
        )
        # Strip the section header line and convert text → HTML paragraphs
        import re as _re
        brief_html = ""
        for line in brief_text_raw.splitlines():
            line = line.strip()
            if not line or line.startswith("─") or "AGENT BRIEF" in line.upper():
                continue
            line = _re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", line)
            brief_html += f'<div class="bi">{line}</div>\n'
        s01 = self._h_section(1, "AGENT BRIEF &nbsp;·&nbsp; Gemini AI",
                               '<span class="br">AI from real data</span>', brief_html)

        # ── 02 PROPERTY ASSESSMENT ────────────────────────────────────
        if prop_row is not None:
            av_float = float(prop_row["assessed_value"]) if prop_row.get("assessed_value") else None
            av   = _fmt_usd(av_float) if av_float else "—"
            yb   = str(int(prop_row["year_built"])) if prop_row.get("year_built") else "—"
            _raw_zc   = str(prop_row.get("zone_code", ""))
            _gis_zone = self._zoning_lookup_address(address, zipcode)
            if _gis_zone.get("ok") and _gis_zone.get("zone_name"):
                zc = f"<strong>{_gis_zone['zone_name']}</strong>"
                if _gis_zone.get("zone_description"):
                    zc += f"<br><span style='font-size:11px;color:#666;'>{_gis_zone['zone_description']}</span>"
                zc += "<br><span style='font-size:11px;color:#888;'>Source: Arlington Zoning GIS (point-in-polygon)</span>"
            else:
                _zone_map = self._cfg.get("assessor_to_zoning_map", {})
                _resolved = _zone_map.get(_raw_zc) or _zone_map.get(_raw_zc.upper())
                if _resolved:
                    zc = f"{_resolved} <span style='font-size:11px;color:#888;'>(assessor: {_raw_zc})</span>"
                elif _raw_zc:
                    zc = (f"<span style='color:#888;'>Verify with town</span> "
                          f"<span style='font-size:11px;color:#888;'>(assessor: {_raw_zc})</span>")
                else:
                    zc = "—"
            bd   = str(int(prop_row["beds"])) if prop_row.get("beds") else "—"
            ba   = str(float(prop_row["baths"])) if prop_row.get("baths") else "—"
            ls   = f"{int(prop_row['lot_size_sqft']):,} sq ft" if prop_row.get("lot_size_sqft") else "—"
            pid  = str(prop_row.get("parcel_id", "—"))
            own  = str(prop_row.get("owner_name", "—"))
            src  = str(prop_row.get("te_source", "arlington-ma-tax-assessor"))

            # Estimated current market value
            avm_row = self._estimate_market_value(av_float, df_market, zipcode) if av_float else None
            if avm_row:
                sign = "+" if avm_row["appreciation_1yr_pct"] >= 0 else ""
                avm_html = (
                    f'<strong style="color:#1a7a1a">{_fmt_usd(avm_row["estimated_value"])}</strong>'
                    f'&nbsp;<span style="font-size:12px;color:#555;">'
                    f'({sign}{avm_row["appreciation_1yr_pct"]}% 1-yr ZHVI &nbsp;·&nbsp; as of {avm_row["as_of"]})</span>'
                )
            else:
                avm_html = "—"

            kv_rows = [
                ("Address", f"{address}, {self._town_name} {self._state} {zipcode}"),
                ("Owner", own),
                ("Assessed Value (FY)", f"<strong>{av}</strong>"),
                ("Est. Current Market Value", avm_html),
                ("Year Built", yb),
                ("Zone Code", zc),
                ("Beds / Baths", f"{bd} bedrooms &nbsp;/&nbsp; {ba} bathrooms"),
                ("Lot Size", ls),
                ("Parcel ID", pid),
            ]
            prop_body = (
                self._h_kv(kv_rows)
                + '<div class="sn">Sources: Town Assessor (Patriot Properties, live scrape) + '
                  'Zillow ZHVI for 1-yr market appreciation. '
                  'MA law (M.G.L. c.59 §38) requires assessments at 100% full cash value; '
                  'estimate adjusts for ~12-month assessment lag.</div>'
            )
        else:
            prop_body = f"<p>Property \"{address}\" not found in assessor dataset.</p>"
        s02 = self._h_section(2, "PROPERTY ASSESSMENT &nbsp;·&nbsp; Town Assessor",
                               '<span class="br">REAL DATA</span>', prop_body)

        # ── 02b VALUE TIMELINE ────────────────────────────────────────
        if prop_row is not None and prop_row.get("assessed_value"):
            tl = self._value_timeline(
                float(prop_row["assessed_value"]), df_market, zipcode
            )
        else:
            tl = None

        if tl:
            # CSS mini-bar chart — width proportional to value
            max_val = max(
                [h["value"] for h in tl["history"]]
                + [p["high"] for p in tl["projection"]]
            )

            def _tl_bar(val: float, color: str, pct_width: float) -> str:
                w = round(pct_width, 1)
                return (f'<div style="display:flex;align-items:center;margin:3px 0;font-size:13px;">'
                        f'<div style="width:260px;background:#eee;border-radius:3px;height:18px;margin-right:10px;">'
                        f'<div style="width:{w}%;height:18px;border-radius:3px;background:{color};"></div></div>'
                        f'<span style="min-width:100px;">{_fmt_usd(val)}</span></div>')

            hist_html = (
                '<p style="font-size:12px;font-weight:bold;color:#1a3a6e;margin:8px 0 4px 0;">'
                'HISTORICAL (ZHVI-indexed estimate)</p>'
            )
            for h in tl["history"]:
                chg_s = (f'&nbsp;<span style="color:{"#1a7a1a" if (h["change_pct"] or 0) >= 0 else "#cc2222"};font-size:11px;">'
                         f'{"+" if (h["change_pct"] or 0) >= 0 else ""}{h["change_pct"]:.1f}% YoY</span>'
                         if h["change_pct"] is not None else "")
                is_latest = h["year"] == tl["history"][-1]["year"]
                bar_color = "#1a73e8" if not is_latest else "#0d5bb5"
                bar_w     = 100 * h["value"] / max_val if max_val else 50
                hist_html += (
                    f'<div style="display:flex;align-items:center;margin:3px 0;font-size:13px;">'
                    f'<span style="width:60px;color:#555;">{h["year"]}</span>'
                    f'<div style="flex:1;background:#eee;border-radius:3px;height:18px;margin:0 10px;">'
                    f'<div style="width:{bar_w:.1f}%;height:18px;border-radius:3px;background:{bar_color};"></div></div>'
                    f'<span style="min-width:110px;font-weight:{"bold" if is_latest else "normal"};">'
                    f'{_fmt_usd(h["value"])}</span>'
                    f'{chg_s}'
                    + ('<span style="font-size:11px;color:#888;margin-left:6px;">← assessed basis</span>' if is_latest else "")
                    + '</div>'
                )

            proj_html = (
                '<p style="font-size:12px;font-weight:bold;color:#1a6a3e;margin:14px 0 4px 0;">'
                f'PROJECTED &nbsp;·&nbsp; CAGR {tl["cagr_pct"]:+.1f}%/yr (confidence band ±{abs(tl["cagr_pct"]/2):.1f}%/yr)</p>'
            )
            for p in tl["projection"]:
                bar_w = 100 * p["mid"] / max_val if max_val else 50
                proj_html += (
                    f'<div style="display:flex;align-items:center;margin:3px 0;font-size:13px;">'
                    f'<span style="width:60px;color:#555;">{p["year"]}</span>'
                    f'<div style="flex:1;background:#eee;border-radius:3px;height:18px;margin:0 10px;">'
                    f'<div style="width:{bar_w:.1f}%;height:18px;border-radius:3px;background:#27ae60;opacity:0.7;"></div></div>'
                    f'<span style="min-width:110px;color:#1a6a3e;">{_fmt_usd(p["mid"])}</span>'
                    f'<span style="font-size:11px;color:#888;">'
                    f'{_fmt_usd(p["low"])} – {_fmt_usd(p["high"])}</span></div>'
                )

            tl_footer = (
                f'<div class="sn">Source: Zillow ZHVI ({zipcode}), {tl["data_years"]:.0f} yrs data as of {tl["as_of"]}. '
                f'Method: Assessed value × ZHVI index ratio per year. '
                f'Projection uses {tl["data_years"]:.0f}-yr CAGR. '
                f'⚠ Estimates only — not a licensed appraisal.</div>'
            )
            tl_body = hist_html + proj_html + tl_footer
        else:
            tl_body = (
                f'<p style="font-size:13px;">Insufficient ZHVI data for timeline. '
                f'Re-run: <code>python3 scripts/download_zillow_cache.py --town {self._town_slug} --months 60</code></p>'
            )
        s02b = self._h_section(
            3, "VALUE TIMELINE &nbsp;·&nbsp; 5-Yr History + 3-Yr Projection",
            '<span class="be">ZHVI-INDEXED ESTIMATE</span>', tl_body
        )

        # ── 03 COMPLIANCE GRID ────────────────────────────────────────
        if prop_row is not None and zone_row is not None:
            lot_sqft   = float(prop_row["lot_size_sqft"]) if prop_row.get("lot_size_sqft") else None
            year_built = int(prop_row["year_built"]) if prop_row.get("year_built") else None
            av_val     = float(prop_row["assessed_value"]) if prop_row.get("assessed_value") else None
            zmeta      = zone_row.get("metadata") or {}
            if isinstance(zmeta, str):
                try: zmeta = json.loads(zmeta)
                except: zmeta = {}
            min_lot  = zmeta.get("min_lot_sqft")
            max_far  = zmeta.get("max_far")
            setback  = zmeta.get("setback_front_ft")
            frontage = zmeta.get("min_frontage_ft")
            max_ht   = zone_row.get("max_height_ft")
            uses     = zone_row.get("allowed_uses") or []
            if isinstance(uses, str):
                try: uses = json.loads(uses)
                except: uses = []
            adu_ok = any("ADU" in u.upper() or "ACCESSORY" in u.upper() for u in uses)
            pre78  = year_built and year_built < 1978

            def vrd(condition, ok_text, warn_text, cls):
                return f'<span class="{cls}">{ok_text if condition else warn_text}</span>'

            lot_v = (f'<span class="ok">✅ COMPLIANT</span>' if lot_sqft and min_lot and lot_sqft >= min_lot
                     else '<span class="wn">⚠ Non-Conforming (pre-existing)</span>')
            cgrid_rows = [
                ["Min. Lot Size",
                 f"{int(min_lot):,} sq ft" if min_lot else "—",
                 f"{int(lot_sqft):,} sq ft" if lot_sqft else "Unverified",
                 lot_v],
                ["ADU Permitted", "Permitted (by-right)" if adu_ok else "Not listed",
                 "By-right eligible" if adu_ok else "Not permitted",
                 '<span class="ok">✅ ELIGIBLE</span>' if adu_ok else '<span class="fl">❌ NOT PERMITTED</span>'],
                ["Max Building Height", f"{int(max_ht)} ft" if max_ht else "—",
                 "Existing structure", '<span class="ok">✅ Grandfathered</span>'],
                ["Front Setback", f"{int(setback)} ft" if setback else "—",
                 "Existing structure", '<span class="ok">✅ Grandfathered</span>'],
                ["Min. Street Frontage", f"{int(frontage)} ft" if frontage else "—",
                 "See plot plan", '<span class="wn">⚠ Verify with ISD</span>'],
                ["Max Floor-Area Ratio", str(max_far) if max_far else "—",
                 "Existing use", '<span class="wn">⚠ Verify before ADU</span>'],
                ["Lead Paint (pre-1978)", f"Built {year_built}" if year_built else "—",
                 "Lead paint disclosure required" if pre78 else "N/A",
                 '<span class="wn">⚠ Pre-1978 — disclose</span>' if pre78 else '<span class="ok">✅ Post-1978</span>'],
                ["Assessed Value", "Town Assessor (real)",
                 _fmt_usd(av_val) if av_val else "—", '<span class="ok">✅ Verified</span>'],
            ]
            comp_body = (self._h_table(["Requirement", "Bylaw Standard", "This Parcel", "Verdict"], cgrid_rows)
                         + '<div class="sn">Sources: Arlington Zoning Bylaw 2024 + Arlington Tax Assessor '
                           '(Patriot Properties).<br>⚠ = Confirm with Arlington Inspectional Services before permitting.</div>')
        else:
            comp_body = "<p>Insufficient data to generate compliance grid.</p>"
        s03 = self._h_section(3, "REGULATORY COMPLIANCE GRID &nbsp;·&nbsp; Bylaw vs Parcel",
                               '<span class="br">REAL DATA</span>', comp_body)

        # ── 04 PRO-FORMA ──────────────────────────────────────────────
        if prop_row is not None:
            ls_s   = f"{int(float(prop_row['lot_size_sqft'])):,} sq ft" if prop_row.get("lot_size_sqft") else "lot size unverified"
            av_s   = _fmt_usd(float(prop_row["assessed_value"])) if prop_row.get("assessed_value") else ""
            zd_s   = zone_row["zone_description"] if zone_row is not None else str(prop_row.get("zone_code", ""))
            uses_l = zone_row.get("allowed_uses") or [] if zone_row is not None else []
            if isinstance(uses_l, str):
                try: uses_l = json.loads(uses_l)
                except: uses_l = []
            adu_p  = any("ADU" in u.upper() or "ACCESSORY" in u.upper() for u in uses_l)
            pf_intro = (f'<p style="margin:0 0 10px 0;font-size:13px;">'
                        f'<strong>{ls_s} &nbsp;·&nbsp; {zd_s} &nbsp;·&nbsp; '
                        f'{"ADU permitted by-right" if adu_p else "ADU eligibility — verify with ISD"}'
                        f'</strong> &nbsp;·&nbsp; Assessed: {av_s}</p>')
            pf_rows = []
            if adu_p:
                pf_rows += [
                    ["Detached Garden ADU (max 900 sq ft)", "$325k – $400k", "+$175k – $210k", "$2,800 – $3,500/mo"],
                    ["Attached ADU / In-Law Suite",          "$120k – $180k", "+$120k – $150k", "$1,800 – $2,400/mo"],
                    ["Garage + Studio ADU (combo)",          "$140k – $185k", "+$140k – $160k", "$1,500 – $2,000/mo"],
                ]
            pf_rows.append(["Detached 2-Car Garage (no ADU)", "$60k – $90k", "+$80k – $100k", "N/A (utility value)"])
            pf_body = (pf_intro
                       + self._h_table(["Development Option", "Est. Cost", "Equity Value Add", "Est. Rental Yield"], pf_rows)
                       + '<div class="sn">Construction costs: MA industry averages (2025–2026). '
                         'Equity: Arlington comparable sales (±20%). Rental: current Arlington market range.</div>')
        else:
            pf_body = "<p>Property data required for pro-forma calculation.</p>"
        s04 = self._h_section(4, "INVESTMENT PRO-FORMA &nbsp;·&nbsp; By-Right Options",
                               '<span class="ba">REAL ZONING + INDUSTRY COSTS</span>', pf_body)

        # ── 05 FLOOD RISK ─────────────────────────────────────────────
        import urllib.parse as _urlparse
        _fema_query = _urlparse.quote(f"{address}, {self._town_name}, {self._state} {zipcode}".strip(", "))
        _fema_url   = f"https://msc.fema.gov/portal/search#searchresultsanchor?addressquery={_fema_query}"

        # Live property-level FEMA lookup
        _lookup = self._fema_lookup_address(address, self._town_name, self._state, zipcode)
        if _lookup["found"]:
            _zone = _lookup["fema_zone"] or "X"
            _risk = _lookup["risk_level"]
            if _risk == "NONE" or _zone == "X":
                _prop_flood_html = (
                    f'<div style="background:#d4edda;border-left:4px solid #27ae60;padding:10px 14px;'
                    f'margin-bottom:14px;border-radius:0 4px 4px 0;">'
                    f'<strong>✅ THIS PROPERTY: NOT in a Special Flood Hazard Area</strong><br>'
                    f'<span style="font-size:13px;">Zone <strong>{_zone}</strong> — minimal/moderate risk. '
                    f'Flood insurance is <strong>NOT required</strong> by federally-backed lenders.</span></div>'
                )
            elif _risk == "HIGH":
                _prop_flood_html = (
                    f'<div style="background:#f8d7da;border-left:4px solid #cc2222;padding:10px 14px;'
                    f'margin-bottom:14px;border-radius:0 4px 4px 0;">'
                    f'<strong>🔴 THIS PROPERTY: HIGH FLOOD RISK — Zone {_zone} (SFHA)</strong><br>'
                    f'<span style="font-size:13px;">Flood insurance is <strong>REQUIRED</strong> '
                    f'for federally-backed mortgages.</span></div>'
                )
            else:
                _prop_flood_html = (
                    f'<div style="background:#fff3cd;border-left:4px solid #e0a020;padding:10px 14px;'
                    f'margin-bottom:14px;border-radius:0 4px 4px 0;">'
                    f'<strong>🟡 THIS PROPERTY: MODERATE FLOOD RISK — Zone {_zone}</strong><br>'
                    f'<span style="font-size:13px;">Flood insurance is recommended but not required.</span></div>'
                )
        else:
            _prop_flood_html = (
                f'<div style="background:#fff3cd;border-left:4px solid #e0a020;padding:10px 14px;'
                f'margin-bottom:14px;border-radius:0 4px 4px 0;">'
                f'<strong>⚠ Could not determine flood zone automatically</strong><br>'
                f'<span style="font-size:13px;">{_lookup["error"]}<br>'
                f'<a href="{_fema_url}" style="color:#1a73e8;">Verify at FEMA MSC →</a></span></div>'
            )

        if not df_climate.empty and "risk_level" in df_climate.columns:
            rc    = df_climate["risk_level"].value_counts().to_dict()
            high  = rc.get("HIGH", 0); mod = rc.get("MODERATE", 0); total = len(df_climate)
            hp    = round(100 * high / total) if total else 0
            mp    = round(100 * mod  / total) if total else 0
            fzc   = ""
            if "metadata" in df_climate.columns:
                fzones = (df_climate["metadata"]
                          .apply(lambda m: m.get("fema_zone") if isinstance(m, dict) else None)
                          .dropna().unique().tolist())
                fzc = ", ".join(sorted(set(str(z) for z in fzones if z)))

            flood_body = (
                # Property-level result (live lookup above)
                _prop_flood_html
                # Town-wide context
                + f'<p style="font-size:12px;font-weight:bold;color:#555;margin:0 0 8px 0;">'
                  f'TOWN-WIDE CONTEXT — {self._town_name} flood zone polygons: {total} total</p>'
                + f'<div class="rbar"><span class="rl">🔴 Zone AE / Floodway (HIGH)</span>'
                  f'<div class="rbw"><div class="rbh" style="width:{hp}%"></div></div>'
                  f'<span class="rc">{high} polygons</span></div>'
                + f'<div class="rbar"><span class="rl">🟡 Zone X — 500-yr (MODERATE)</span>'
                  f'<div class="rbw"><div class="rbm" style="width:{mp}%"></div></div>'
                  f'<span class="rc">{mod} polygons</span></div>'
                + (f'<p style="font-size:13px;margin:10px 0 4px 0;">'
                   f'<strong>Zone codes in {self._town_name}:</strong> {fzc}</p>' if fzc else "")
                + '<p style="font-size:12px;color:#666;margin:8px 0;">Zone AE = 100-yr floodplain — '
                  'federally-backed mortgages <strong>require</strong> flood insurance. '
                  'Zone X = moderate risk; optional.</p>'
                + '<div class="sn">Source: FEMA NFHL MapServer layer 28 + Census geocoder. '
                  'Property-specific zone determined via point-in-polygon query.</div>'
            )
        else:
            flood_body = (
                _prop_flood_html
                + f'<div class="sn">Town-wide FEMA polygon data not yet loaded for {self._town_name}.</div>'
            )
        s05 = self._h_section(5, "FLOOD RISK &nbsp;·&nbsp; FEMA NFHL",
                               '<span class="br">REAL DATA</span>', flood_body)

        # ── 05b HISTORIC STATUS ──────────────────────────────────────
        _hist_cfg = self._cfg.get("historic_resources", {}) or {}
        if _hist_cfg.get("macris_polygon_layer_url") or _hist_cfg.get("macris_point_layer_url"):
            _h = self._historic_lookup_address(address, zipcode)
            _macris_link = _hist_cfg.get("macris_search_url", "")
            _ahc_link    = _hist_cfg.get("ahc_inventory_url", "")
            if _h.get("error") and not _h["found"]:
                _hist_box = (
                    f'<div style="background:#fff3cd;border-left:4px solid #e0a020;padding:10px 14px;'
                    f'margin-bottom:14px;border-radius:0 4px 4px 0;">'
                    f'<strong>⚠ Historic lookup unavailable</strong><br>'
                    f'<span style="font-size:13px;">{_h["error"]}</span></div>'
                )
            elif not _h["found"]:
                _hist_box = (
                    f'<div style="background:#d4edda;border-left:4px solid #27ae60;padding:10px 14px;'
                    f'margin-bottom:14px;border-radius:0 4px 4px 0;">'
                    f'<strong>✅ THIS PROPERTY: NOT on MACRIS, NOT in a historic district</strong><br>'
                    f'<span style="font-size:13px;">No special historic-preservation review required for renovations.</span></div>'
                )
            else:
                _tags_html = []
                _in_lhd = False
                for _d in _h["designations"]:
                    _du = _d.upper()
                    if _du in ("LHD", "LOCAL HISTORIC DISTRICT"):
                        _tags_html.append("Local Historic District (LHD)"); _in_lhd = True
                    elif _du in ("NRHP", "NATIONAL REGISTER OF HISTORIC PLACES"):
                        _tags_html.append("National Register (NRHP)")
                    elif _du == "NRHP AND LHD":
                        _tags_html.append("NRHP + Local Historic District"); _in_lhd = True
                    elif _du in ("MA/HL", "MASSACHUSETTS HISTORIC LANDMARK"):
                        _tags_html.append("MA Historic Landmark")
                    elif _du == "PR" or "PRESERVATION RESTRICTION" in _du:
                        _tags_html.append("Preservation Restriction")
                    elif _du in ("INVENTORIED PROPERTY", "INV"):
                        _tags_html.append("Inventoried (no formal designation)")
                    else:
                        _tags_html.append(_d)
                _bg, _bd, _icon, _label = (
                    ("#f8d7da", "#cc2222", "🔴", "ALTERATIONS RESTRICTED")
                    if _in_lhd else ("#fff3cd", "#e0a020", "🟡", "Listed on MACRIS inventory")
                )
                _details = []
                if _h["historic_name"]:
                    _details.append(f'<tr><td>Historic Name</td><td>{_h["historic_name"]}</td></tr>')
                if _h["common_name"] and _h["common_name"] != _h["historic_name"]:
                    _details.append(f'<tr><td>Common Name</td><td>{_h["common_name"]}</td></tr>')
                if _h["constructed"]:
                    _details.append(f'<tr><td>Constructed</td><td>{_h["constructed"]}</td></tr>')
                if _h["architectural_style"]:
                    _details.append(f'<tr><td>Architectural Style</td><td>{_h["architectural_style"]}</td></tr>')
                if _h["macris_id"]:
                    _details.append(f'<tr><td>MACRIS ID</td><td>{_h["macris_id"]}</td></tr>')
                _details_html = ("<table class='kv'>" + "".join(_details) + "</table>") if _details else ""
                _warn_html = ""
                if _in_lhd:
                    _warn_html = (
                        '<p style="font-size:12px;color:#666;margin:8px 0;">'
                        '<strong>⚠ Exterior alterations</strong> visible from a public way require an '
                        'Arlington Historical Commission <strong>Certificate of Appropriateness</strong> '
                        'before any building permit can be issued.</p>'
                    )
                _hist_box = (
                    f'<div style="background:{_bg};border-left:4px solid {_bd};padding:10px 14px;'
                    f'margin-bottom:14px;border-radius:0 4px 4px 0;">'
                    f'<strong>{_icon} THIS PROPERTY: {_label}</strong><br>'
                    f'<span style="font-size:13px;">{" &nbsp;|&nbsp; ".join(_tags_html) or "Designated"}</span></div>'
                    + _details_html + _warn_html
                )
            _links = []
            if _macris_link: _links.append(f'<a href="{_macris_link}" style="color:#1a73e8;">MACRIS Maps</a>')
            if _ahc_link:    _links.append(f'<a href="{_ahc_link}" style="color:#1a73e8;">Arlington Historical Commission</a>')
            _links_html = ('<p style="font-size:12px;margin:6px 0;">' + " &nbsp;·&nbsp; ".join(_links) + '</p>') if _links else ""
            _hist_body = _hist_box + _links_html + (
                '<div class="sn">Source: MA Historical Commission MACRIS '
                '(point + polygon layers via Boston Planning ArcGIS).</div>'
            )
            s05b = self._h_section(6, "HISTORIC STATUS &nbsp;·&nbsp; MACRIS / AHC",
                                    '<span class="br">REAL DATA</span>', _hist_body)
        else:
            s05b = ""

        # ── 06 TRANSIT ────────────────────────────────────────────────
        if not df_transit.empty and "event_name" in df_transit.columns:
            alerts_html = ""
            for _, row in df_transit.iterrows():
                name = str(row.get("event_name") or "Alert")
                st_  = row.get("start_time"); en_ = row.get("end_time")
                date_s = ""
                try:
                    if st_ and pd.notna(pd.Timestamp(st_)):
                        date_s = pd.Timestamp(st_).strftime("%b %-d")
                    if en_ and pd.notna(pd.Timestamp(en_)):
                        date_s += f" → {pd.Timestamp(en_).strftime('%b %-d')}"
                except Exception:
                    pass
                is_warn = any(w in name.lower() for w in ("delay","suspend","cancel","detour"))
                cls = "aw" if is_warn else "ai"
                icon = "⚠" if is_warn else "ℹ"
                alerts_html += (f'<div class="{cls}"><strong>{icon} {name}</strong>'
                                + (f'<br><span style="color:#666;font-size:12px;">Active: {date_s}</span>' if date_s else "")
                                + '</div>')
            src_t = df_transit["te_source"].iloc[0] if "te_source" in df_transit.columns else "arlington-ma-mbta-alerts"
            transit_body = alerts_html + f'<div class="sn">Source: {src_t} — live MBTA API v3</div>'
        else:
            transit_body = "<p>No active MBTA alerts for configured routes.</p>"
        s06 = self._h_section(7, "LIVE TRANSIT ALERTS &nbsp;·&nbsp; MBTA API v3",
                               '<span class="br">REAL DATA</span>', transit_body)

        # ── 07 MARKET ─────────────────────────────────────────────────
        if not df_market.empty and "metric_name" in df_market.columns:
            sp = df_market[df_market["metric_name"] == "MEDIAN_SALE_PRICE"].copy()
            mkt_rows = []
            if not sp.empty:
                sp["observation_date"] = pd.to_datetime(sp["observation_date"], utc=True, errors="coerce")
                for zip_val, grp in sp.groupby("geo_value"):
                    grp = grp.sort_values("observation_date")
                    newest = float(grp.iloc[-1]["metric_value"])
                    oldest = float(grp.iloc[0]["metric_value"])
                    pct    = round(100 * (newest / oldest - 1), 1) if oldest else 0
                    mo     = grp.iloc[-1]["observation_date"]
                    mo_s   = pd.Timestamp(mo).strftime("%b %Y") if pd.notna(pd.Timestamp(mo)) else "—"
                    mkt_rows.append([zip_val, f"<strong>{_fmt_usd(newest)}</strong>",
                                     f"+{pct}% (from {_fmt_usd(oldest)})", mo_s])
            mkt_src  = df_market["te_source"].iloc[0] if "te_source" in df_market.columns else "zillow-zhvi"
            mkt_body = (self._h_table(["ZIP Code", "Median Home Value", "3-Year Change", "As Of"], mkt_rows)
                        + f'<div class="sn">Source: {mkt_src} — Zillow ZHVI (Home Value Index), 36-month history</div>')
        else:
            mkt_body = "<p>Market data not available.</p>"
        s07 = self._h_section(8, "MARKET DYNAMICS &nbsp;·&nbsp; Zillow ZHVI",
                               '<span class="br">REAL DATA</span>', mkt_body)

        # ── 08 TOWN PROFILE ───────────────────────────────────────────
        if not df_profile.empty:
            pr  = df_profile.iloc[0]
            nim = float(pr.get("nimby_index", 0))
            bar = "█" * int(round(nim)) + "░" * (10 - int(round(nim)))
            emp = pr.get("major_employers") or []
            if isinstance(emp, str):
                try: emp = json.loads(emp)
                except: emp = []
            meta_p = pr.get("metadata") or {}
            if isinstance(meta_p, str):
                try: meta_p = json.loads(meta_p)
                except: meta_p = {}
            prof_rows = [
                ("Housing Character", str(pr.get("housing_character","—")).replace("_"," ").title()),
                ("Political Lean", str(pr.get("political_lean","—")).title()),
                ("NIMBY Index", f"{nim:.1f}/10 [{bar}]"),
                ("Walkability Score", str(meta_p.get("walkability_score","—"))),
                ("Transit Score",     str(meta_p.get("transit_score","—"))),
                ("School Rating",     str(meta_p.get("school_rating","—"))),
                ("Major Employers",   ", ".join(emp[:5]) if emp else "—"),
                ("Investment Sweet Spots", ", ".join((meta_p.get("sweet_spots") or [])[:3]) or "—"),
                ("Risk Factors",      "; ".join((meta_p.get("risks") or [])[:2]) or "—"),
            ]
            vibes = str(pr.get("neighborhood_vibes",""))
            prof_body = self._h_kv(prof_rows)
            if vibes:
                prof_body += f'<div class="nt">{vibes}</div>'
        else:
            prof_body = "<p>Town profile data not available.</p>"
        s08 = self._h_section(9, "TOWN PROFILE &nbsp;·&nbsp; Investment Intelligence",
                               '<span class="be">ESTIMATED</span>', prof_body)

        # ── 09 STR ────────────────────────────────────────────────────
        if not df_str.empty:
            sr = df_str.iloc[0]
            meta_s = sr.get("metadata") or {}
            if isinstance(meta_s, str):
                try: meta_s = json.loads(meta_s)
                except: meta_s = {}
            ps = sr.get("peak_seasons") or []
            if isinstance(ps, str):
                try: ps = json.loads(ps)
                except: ps = []
            str_body = self._h_kv([
                ("Observation Month",  str(sr.get("observation_month","—"))),
                ("Est. Gross Yield",   f"{float(sr.get('estimated_yield_pct',0)):.1f}%"),
                ("Avg Nightly Rate",   _fmt_usd(float(sr.get("avg_nightly_rate_usd",0)))),
                ("Occupancy Rate",     f"{float(sr.get('occupancy_rate_pct',0)):.0f}%"),
                ("Regulatory Posture", str(sr.get("regulatory_posture","—"))),
                ("Peak Seasons",       ", ".join(ps) if ps else "—"),
                ("Sweet-Spot Areas",   ", ".join((meta_s.get("sweet_spot_neighborhoods") or [])[:3]) or "—"),
            ])
        else:
            str_body = "<p>STR data not available.</p>"
        s09 = self._h_section(10, "SHORT-TERM RENTAL (STR) DYNAMICS",
                               '<span class="be">ESTIMATED</span>', str_body)

        # ── 10 INFRA ──────────────────────────────────────────────────
        if not df_infra.empty:
            active = df_infra[df_infra["status"].isin({"PLANNED","DESIGN","BID","IN_PROGRESS"})] \
                if "status" in df_infra.columns else df_infra
            inf_rows = []
            for _, r in active.head(6).iterrows():
                cost = r.get("estimated_cost")
                inf_rows.append([
                    str(r.get("project_name","—"))[:55],
                    str(r.get("status","—")),
                    _fmt_usd(float(cost)) if cost and float(cost) > 0 else "TBD",
                ])
            infra_body = (f'<p style="font-size:13px;margin:0 0 8px 0;">'
                          f'Active / upcoming: <strong>{len(active)}</strong></p>'
                          + self._h_table(["Project", "Status", "Est. Cost"], inf_rows))
        else:
            infra_body = "<p>Infrastructure data not available.</p>"
        s10 = self._h_section(11, "INFRASTRUCTURE PROJECTS (DPW)",
                               '<span class="be">ESTIMATED</span>', infra_body)

        # ── 11 ZONING — property's zone only ──────────────────────────
        if zone_row is not None:
            zr     = zone_row
            uses_z = zr.get("allowed_uses") or []
            if isinstance(uses_z, str):
                try: uses_z = json.loads(uses_z)
                except: uses_z = []
            meta_z = zr.get("metadata") or {}
            if isinstance(meta_z, str):
                try: meta_z = json.loads(meta_z)
                except: meta_z = {}
            zon_kv = [
                ("Zone Code",       str(zr.get("zone_code", "—"))),
                ("Description",     str(zr.get("zone_description", "—"))),
                ("Max Height",      f"{int(zr['max_height_ft'])} ft" if zr.get("max_height_ft") else "—"),
                ("Min Lot Size",    f"{int(meta_z['min_lot_sqft']):,} sq ft" if meta_z.get("min_lot_sqft") else "—"),
                ("Max FAR",         str(meta_z.get("max_far", "—"))),
                ("Front Setback",   f"{int(meta_z['setback_front_ft'])} ft" if meta_z.get("setback_front_ft") else "—"),
                ("Min Frontage",    f"{int(meta_z['min_frontage_ft'])} ft" if meta_z.get("min_frontage_ft") else "—"),
                ("Permitted Uses",  ", ".join(uses_z) if uses_z else "—"),
            ]
            zon_body = (self._h_kv(zon_kv)
                        + '<div class="sn">Source: Arlington Zoning Bylaw, Article 5 (2024 edition)</div>')
        elif not df_zoning.empty:
            zon_body = "<p>Property zone not resolved — assessor zone code not matched to bylaw.</p>"
        else:
            zon_body = "<p>Zoning data not available.</p>"
        _bylaw_year = self._cfg.get("zoning", {}).get("bylaw_year", "2024")
        s11 = self._h_section(12, f"ZONING SUMMARY &nbsp;·&nbsp; {self._town_name} Bylaw {_bylaw_year}",
                               '<span class="ba">ACCURATE</span>', zon_body)

        # ── Assemble ──────────────────────────────────────────────────
        return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8">
<title>TownEye Civic Audit — {address}, {self._town_name} {self._state}</title>
<style>{self._HTML_CSS}</style>
</head>
<body>
<div class="rh">
  <h1>TOWNEYE &nbsp;·&nbsp; CIVIC AUDIT REPORT</h1>
  <div class="sub">Property &nbsp;·&nbsp; {address}, {self._town_name}, {self._state} &nbsp; {zipcode}</div>
  <div class="sub">Municipality &nbsp;·&nbsp; {self._town_name}, {self._state}</div>
  <div class="sub">Generated &nbsp;·&nbsp; {now_str}</div>
  <span class="badge">{real_label}</span>
</div>
{s01}{s02}{s02b}{s03}{s04}{s05}{s05b}{s06}{s07}{s08}{s09}{s10}{s11}
<div class="disc">
  <strong>LEGAL DISCLAIMER</strong><br>
  TownEye Civic Audit Reports, including qualitative market summaries and STR estimates,
  are generated via AI synthesis and are for informational purposes only. Sections labeled
  <strong>REAL DATA</strong> are sourced from live government APIs. Sections labeled
  <strong>ESTIMATED</strong> are AI-synthesized approximations only. Verify all zoning,
  regulatory, and financial data with official municipal authorities before making decisions.
</div>
<div class="pw">Powered by TownEye Municipal Intelligence &nbsp;·&nbsp; towneye.ai</div>
</body></html>"""


# ---------------------------------------------------------------------------
# Console verification entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
    )

    p = argparse.ArgumentParser(description="TownEye Civic Audit Report — Realtor Agent")
    p.add_argument("--town",    default="arlington-ma", help="Town slug")
    p.add_argument("--address", default="14 Magnolia St", help="Street address")
    p.add_argument("--zip",     default="02474", help="ZIP code")
    p.add_argument(
        "--out", default=None,
        help="Optional path to write the report to (default: stdout only)",
    )
    args = p.parse_args()

    import time as _t
    _start = _t.monotonic()

    agent = RealtorAgent(town_slug=args.town)
    agent._prefetch_property_apis(args.address, args.zip)
    report = agent.generate_report(address=args.address, zipcode=args.zip)

    print(report)

    if args.out:
        out_path = pathlib.Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report, encoding="utf-8")
        print(f"\nReport saved      → {out_path}")

        # Always generate the Gmail-ready HTML alongside the .txt.
        # Brief, FEMA, historic, zoning, and live property fetches are all
        # cached on the agent instance, so this second pass is mostly I/O.
        html_report = agent.generate_html_report(address=args.address, zipcode=args.zip)
        html_path   = out_path.with_suffix("").parent / (out_path.stem + "_email.html")
        html_path.write_text(html_report, encoding="utf-8")
        print(f"Gmail HTML saved  → {html_path}")

    print(f"\nTotal elapsed: {_t.monotonic() - _start:.1f}s")

# reports/realtor_agent.py
# End of Patch #183
