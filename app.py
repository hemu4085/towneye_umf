"""
TownEye — Municipal Intelligence Terminal
==========================================
B2B analytical terminal for real estate developers and contractors.
Powered by a DuckDB SQL agent:

  1. Gemini 2.5 Flash generates a DuckDB SQL query from the schema context.
  2. DuckDB executes the query directly against Gold Parquet files.
  3. Gemini synthesises a concise analytical summary.
  4. The raw result grid is displayed below the summary.

Address questions also trigger a live MassGIS zoning lookup
(Nominatim geocoding → MassGIS ArcGIS REST API).

Run:
    streamlit run app.py
"""

from __future__ import annotations

import os
import pathlib
import re
import textwrap
import time
from typing import Iterator

import duckdb
import pandas as pd
import requests
import streamlit as st

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent
_GOLD_DIR = _PROJECT_ROOT / "data" / "gold"
_GEMINI_MODEL = "gemini-2.5-flash"
_MAX_RESULT_ROWS = 500          # cap rows sent to LLM for synthesis
_MAX_RESULT_CHARS = 12_000      # cap chars in result string sent to LLM

# MassGIS public zoning ArcGIS REST — no API key required.
_MASSGIS_ZONING_URL = (
    "https://massgis.maps.arcgis.com/arcgis/rest/services/"
    "OpenData/GISDATA_ZONING_POLY_GEN1/MapServer/0/query"
)
_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_NOMINATIM_HEADERS = {"User-Agent": "TownEye/1.0 (towneye.com)"}
_REQUEST_TIMEOUT = 10

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_SQL_SYSTEM = textwrap.dedent("""\
    You are an expert DuckDB SQL Data Engineer.
    You will receive a SCHEMA CONTEXT listing available Parquet files and their
    columns, followed by a USER QUESTION.

    Rules:
    - Return ONLY one single valid DuckDB SQL statement — no markdown, no explanations,
      no code fences, NO semicolons, no multiple statements.
    - If the question asks about two separate things, combine them into ONE query using
      UNION ALL with a literal 'source_table' column to identify each row's origin.
    - Reference each Parquet file using read_parquet('absolute/path.parquet').
    - Use meaningful column aliases for clarity.
    - If a cross-file JOIN is needed, use read_parquet() for both sides.
    - Use only column names that appear in the SCHEMA CONTEXT — never invent columns.
    - If the question asks for a join between tables but no shared key column exists
      in the schema, answer using only the most relevant single table instead of
      returning NO_DATA.
    - The 'property' table now contains parcel_id, address, zone_code, assessed_value,
      year_built, building_type, beds, baths, owner_name — use these for property queries.
    - If the question truly cannot be answered from any available file, return exactly:
          SELECT 'NO_DATA' AS reason
""")

_SQL_FIX_SYSTEM = textwrap.dedent("""\
    You are an expert DuckDB SQL Data Engineer performing error correction.
    You will receive:
      • ORIGINAL QUESTION
      • FAILING SQL
      • ERROR MESSAGE
      • SCHEMA CONTEXT

    Return ONLY the corrected SQL query — no markdown, no explanations.
    If the error is unrecoverable (e.g. referenced column does not exist in any
    schema), return exactly:
        SELECT 'NO_DATA' AS reason
""")

_SYNTHESIS_SYSTEM = textwrap.dedent("""\
    You are the TownEye Analytical Agent — a concise, data-driven assistant
    for real estate developers and municipal contractors.

    You will receive:
      • USER QUERY: the analyst's original question.
      • QUERY RESULT: data from a DuckDB query against live Gold-tier Parquet files.
      • ADDRESS LOOKUP (optional): a live zoning result for a specific address.

    Respond with a tight analytical summary (3–6 bullet points or short paragraphs).
    Lead with the key insight. Cite specific numbers from the data.
    If QUERY RESULT is empty or "NO_DATA", state that clearly and suggest next steps.
    Do not invent data not present in the result.

    FORMATTING RULES:
    - Always write dollar amounts as plain text: write "1,487,800" or "USD 1,487,800", never "$1,487,800" (the dollar sign breaks rendering).
    - Do not use LaTeX or math notation.
    - Use plain markdown only: bullet points, bold (**text**), and inline code (`value`).
""")

# ---------------------------------------------------------------------------
# Run-Analysis presets
# ---------------------------------------------------------------------------

_ANALYSIS_PRESETS: list[tuple[str, str]] = [
    (
        "🏗️ Zoning Arbitrage",
        "Show the top 10 highest assessed-value properties with their address, "
        "owner name, zone code, and assessed value.",
    ),
    (
        "🔧 Recent Permits",
        "Show the most recent building permits, including permit number, type, status, "
        "application date, and estimated value.",
    ),
    (
        "🚧 Upcoming Infra Projects",
        "List all DPW infrastructure projects with their status, estimated cost, "
        "start date, and end date.",
    ),
    (
        "⏱️ Avg Permit Approval Time",
        "What is the average number of days between application_date and approval_date for building permits?",
    ),
    (
        "⚖️ High Equity Burden",
        "Show census tracts with the highest equity burden scores, including the geo value, "
        "burden score, and whether each is flagged as disadvantaged.",
    ),
]

# ---------------------------------------------------------------------------
# DuckDB helpers
# ---------------------------------------------------------------------------

def _parquet_map(town_slug: str) -> dict[str, pathlib.Path]:
    """Return {domain_stem: absolute_path} for all Parquet files in the town dir."""
    town_dir = _GOLD_DIR / town_slug
    if not town_dir.exists():
        return {}
    return {
        p.stem: p.resolve()
        for p in sorted(town_dir.glob("*.parquet"))
    }


@st.cache_data(show_spinner=False)
def get_schema_context(town_slug: str) -> str:
    """
    DuckDB-introspect every Parquet file and return a schema string the LLM
    can use to write accurate queries.
    """
    pmap = _parquet_map(town_slug)
    if not pmap:
        return f"No Gold Parquet files found for '{town_slug}'."

    lines: list[str] = [
        f"Gold Parquet files available for {town_slug}",
        "Reference each with: read_parquet('<absolute_path>')",
        "",
    ]
    con = duckdb.connect()
    for domain, path in pmap.items():
        try:
            schema_df = con.execute(
                f"DESCRIBE SELECT * FROM read_parquet('{path}')"
            ).df()
            col_parts = [
                f"{r['column_name']} {r['column_type']}"
                for _, r in schema_df.iterrows()
            ]
            lines.append(f"TABLE: {domain}")
            lines.append(f"PATH:  {path}")
            lines.append(f"COLS:  {', '.join(col_parts)}")
        except Exception as exc:  # noqa: BLE001
            lines.append(f"TABLE: {domain}  [unreadable: {exc}]")
        lines.append("")
    con.close()
    return "\n".join(lines)


def _run_sql(sql: str) -> tuple[pd.DataFrame | None, str | None]:
    """Execute DuckDB SQL. Returns (df, None) on success or (None, error) on failure."""
    try:
        con = duckdb.connect()
        df = con.execute(sql).df()
        con.close()
        return df, None
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)


def _df_to_result_str(df: pd.DataFrame) -> str:
    """Convert a result DataFrame to a compact string for LLM synthesis."""
    if df.empty:
        return "Query returned no rows."
    clipped = df.head(_MAX_RESULT_ROWS)
    text = clipped.to_string(index=False, max_colwidth=120)
    if len(text) > _MAX_RESULT_CHARS:
        text = text[:_MAX_RESULT_CHARS] + f"\n[... truncated at {_MAX_RESULT_CHARS} chars]"
    return text


# ---------------------------------------------------------------------------
# Address / zoning live lookup
# ---------------------------------------------------------------------------

def _geocode_address(address: str, town: str, state: str = "MA") -> tuple[float, float] | None:
    """Geocode via Nominatim. Returns (lat, lon) or None."""
    try:
        resp = requests.get(
            _NOMINATIM_URL,
            params={"q": f"{address}, {town}, {state}, USA",
                    "format": "json", "limit": 1, "addressdetails": 0},
            headers=_NOMINATIM_HEADERS,
            timeout=_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        results = resp.json()
        if results:
            return float(results[0]["lat"]), float(results[0]["lon"])
    except Exception:  # noqa: BLE001
        pass
    return None


def _lookup_zoning_massgis(lat: float, lon: float) -> dict | None:
    """Spatial zoning lookup via MassGIS public ArcGIS REST API."""
    try:
        resp = requests.get(
            _MASSGIS_ZONING_URL,
            params={
                "geometry": f"{lon},{lat}", "geometryType": "esriGeometryPoint",
                "inSR": "4326", "spatialRel": "esriSpatialRelIntersects",
                "outFields": "TOWN,ZONE_,ZONING_CODE,USE_DESC",
                "returnGeometry": "false", "f": "json",
            },
            timeout=_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        features = resp.json().get("features", [])
        if not features:
            return None
        attrs = features[0].get("attributes", {})
        return {
            "zone_code":        attrs.get("ZONING_CODE") or attrs.get("ZONE_", ""),
            "zone_description": attrs.get("USE_DESC", ""),
            "town":             attrs.get("TOWN", ""),
            "source":           "MassGIS Zoning Layer (public)",
        }
    except Exception:  # noqa: BLE001
        return None


def _address_zoning_lookup(question: str, town_slug: str) -> str | None:
    """
    Detect a street address in the question, geocode it, and query MassGIS.
    Returns a formatted lookup string or None.
    """
    match = re.search(
        r"\b(\d+\s+[A-Za-z][A-Za-z0-9\s]{2,30}"
        r"(?:Road|Rd|Street|St|Avenue|Ave|Drive|Dr|Lane|Ln|Way|"
        r"Court|Ct|Place|Pl|Blvd|Boulevard|Terrace|Ter|Circle|Cir))\b",
        question, re.IGNORECASE,
    )
    if not match:
        return None

    street = match.group(1).strip()
    town_name = town_slug.replace("-ma", "").replace("-", " ").title()

    coords = _geocode_address(street, town_name)
    if not coords:
        return (
            f"ADDRESS LOOKUP: Could not geocode '{street}, {town_name}, MA'. "
            "Address may not exist or is outside coverage."
        )

    lat, lon = coords
    time.sleep(1)  # Nominatim ToS: ≤1 req/sec
    zoning = _lookup_zoning_massgis(lat, lon)

    if not zoning:
        return (
            f"ADDRESS LOOKUP: Geocoded '{street}' to ({lat:.5f}, {lon:.5f}) "
            "but no zoning district found in MassGIS."
        )

    return (
        f"ADDRESS LOOKUP for '{street}, {town_name}, MA':\n"
        f"  Coordinates : {lat:.5f}, {lon:.5f}\n"
        f"  Zone code   : {zoning['zone_code']}\n"
        f"  Description : {zoning['zone_description']}\n"
        f"  MassGIS town: {zoning['town']}\n"
        f"  Source      : {zoning['source']}"
    )


# ---------------------------------------------------------------------------
# Gemini helpers
# ---------------------------------------------------------------------------

def _gemini_client():
    """Return a configured google-genai Client. Raises RuntimeError if key missing."""
    from google import genai  # noqa: PLC0415
    # Strip whitespace AND any stray quote chars that survive shell sourcing
    api_key = os.environ.get("GEMINI_API_KEY", "").strip().strip('"').strip("'")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set.\n"
            "Export it before launching:  export GEMINI_API_KEY=AIza..."
        )
    return genai.Client(api_key=api_key)


def _call_gemini_text(system: str, user: str, max_tokens: int = 1024) -> str:
  """Single-shot (non-streaming) Gemini call."""
  try:
      from google.genai import types as gt  # noqa: PLC0415
      
      # FIX: Store the client in a variable so it doesn't get closed prematurely
      client = _gemini_client()
      
      resp = client.models.generate_content(
          model=_GEMINI_MODEL,
          contents=user,
          config=gt.GenerateContentConfig(
              system_instruction=system,
              temperature=0.0,
              max_output_tokens=max_tokens,
          ),
      )
      return resp.text or ""
  except Exception as exc:  # noqa: BLE001
      return f"[Gemini error: {exc}]"


def _stream_gemini(system: str, user: str, max_tokens: int = 2048) -> Iterator[str]:
  """Stream Gemini response chunks."""
  try:
      from google.genai import types as gt  # noqa: PLC0415
      config = gt.GenerateContentConfig(
          system_instruction=system,
          temperature=0.2,
          max_output_tokens=max_tokens,
      )
      
      # FIX: Store the client in a variable so it doesn't get closed prematurely
      client = _gemini_client()
      
      for chunk in client.models.generate_content_stream(
          model=_GEMINI_MODEL, contents=user, config=config,
      ):
          if chunk.text:
              yield chunk.text
  except Exception as exc:  # noqa: BLE001
      yield f"\n\n⚠️ Gemini error: {exc}"


def _clean_sql(raw: str) -> str:
    """Strip markdown fences that Gemini occasionally adds despite instructions."""
    raw = re.sub(r"^```[a-z]*\n?", "", raw.strip(), flags=re.IGNORECASE)
    raw = re.sub(r"\n?```$", "", raw)
    return raw.strip()


# ---------------------------------------------------------------------------
# Agentic loop  (returns a structured result dict, not a generator)
# ---------------------------------------------------------------------------

def _is_gemini_error(text: str) -> bool:
    """Return True when _call_gemini_text returned an error string, not SQL."""
    return text.startswith("[Gemini error:") or text.startswith("[Gemini")


def run_agent(
    question: str,
    schema_context: str,
    address_context: str | None,
    status_container,
) -> dict:
    """
    Execute the three-step agentic loop and return a result dict:
      {
        "sql":        str | None,
        "sql_error":  str | None,
        "df":         pd.DataFrame | None,
        "summary":    str,
      }
    """
    result: dict = {"sql": None, "sql_error": None, "df": None, "summary": ""}

    # ── Step 1: generate SQL ─────────────────────────────────────────────
    status_container.write("**Step 1 / 3** — Generating SQL query…")
    sql_user = (
        f"SCHEMA CONTEXT:\n{schema_context}\n\n"
        f"USER QUESTION: {question}"
    )
    raw_sql = _clean_sql(_call_gemini_text(_SQL_SYSTEM, sql_user, max_tokens=2048))

    # Guard: if Gemini returned an error string instead of SQL, surface it cleanly
    if _is_gemini_error(raw_sql):
        result["sql_error"] = raw_sql
        result["summary"] = (
            f"⚠️ Could not generate SQL — Gemini API error:\n\n`{raw_sql}`\n\n"
            "Check that `GEMINI_API_KEY` is set and the model quota is not exhausted."
        )
        return result

    result["sql"] = raw_sql
    status_container.write("**Step 2 / 3** — Executing query against Parquet files…")

    # ── Step 2: execute (with one auto-retry on error) ───────────────────
    df, err = _run_sql(raw_sql)

    if err:
        status_container.warning(f"SQL error (attempting fix): `{err}`")
        fix_user = (
            f"ORIGINAL QUESTION: {question}\n\n"
            f"FAILING SQL:\n{raw_sql}\n\n"
            f"ERROR MESSAGE:\n{err}\n\n"
            f"SCHEMA CONTEXT:\n{schema_context}"
        )
        fixed_sql_raw = _clean_sql(
            _call_gemini_text(_SQL_FIX_SYSTEM, fix_user, max_tokens=2048)
        )
        if _is_gemini_error(fixed_sql_raw):
            result["sql_error"] = fixed_sql_raw
        else:
            result["sql"] = fixed_sql_raw
            df, err = _run_sql(fixed_sql_raw)
            if err:
                result["sql_error"] = err

    result["df"] = df

    # ── Step 3: stream synthesis ─────────────────────────────────────────
    status_container.write("**Step 3 / 3** — Synthesising analytical summary…")
    address_block = (
        f"\nADDRESS LOOKUP:\n{address_context}\n" if address_context else ""
    )
    result_str = _df_to_result_str(df) if df is not None else f"SQL ERROR: {err}"
    synth_user = (
        f"USER QUERY: {question}\n"
        f"{address_block}"
        f"\nQUERY RESULT:\n{result_str}"
    )

    # Collect streamed chunks (caller renders them live via st.write_stream)
    chunks: list[str] = []
    for chunk in _stream_gemini(_SYNTHESIS_SYSTEM, synth_user):
        chunks.append(chunk)
    result["summary"] = "".join(chunks)

    return result


# ---------------------------------------------------------------------------
# Dashboard helpers  (cached DuckDB queries shown on page load)
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False, ttl=300)
def _dash_town_pulse(town_slug: str) -> pd.DataFrame:
    """
    Return up to 6 recent 311 / transit items for the Town Pulse panel.
    Tries 311.parquet first, falls back to transit.parquet, then school-calendar.parquet.
    Always returns a DataFrame (may be empty).
    """
    pmap = _parquet_map(town_slug)
    con = duckdb.connect()

    # Try 311 first — most operationally relevant for contractors / residents
    if "311" in pmap:
        try:
            sql = f"""
                SELECT
                    COALESCE(summary, event_name, description, 'Unknown') AS alert,
                    COALESCE(CAST(start_time AS VARCHAR), status, '')      AS "when",
                    COALESCE(description, '')                               AS detail
                FROM read_parquet('{pmap["311"]}')
                ORDER BY start_time DESC NULLS LAST
                LIMIT 6
            """
            df = con.execute(sql).df()
            if not df.empty:
                con.close()
                return df
        except Exception:  # noqa: BLE001
            pass

    # Fall back to transit
    if "transit" in pmap:
        try:
            sql = f"""
                SELECT
                    COALESCE(event_name, route_id, 'Transit update')       AS alert,
                    COALESCE(CAST(start_time AS VARCHAR), effect, '')       AS "when",
                    COALESCE(header_text, description, '')                  AS detail
                FROM read_parquet('{pmap["transit"]}')
                ORDER BY start_time DESC NULLS LAST
                LIMIT 6
            """
            df = con.execute(sql).df()
            if not df.empty:
                con.close()
                return df
        except Exception:  # noqa: BLE001
            pass

    # Final fall back: school-calendar (still operationally useful)
    if "school-calendar" in pmap:
        try:
            sql = f"""
                SELECT
                    event_name                          AS alert,
                    CAST(start_time AS VARCHAR)         AS "when",
                    COALESCE(description, '')           AS detail
                FROM read_parquet('{pmap["school-calendar"]}')
                ORDER BY start_time ASC NULLS LAST
                LIMIT 6
            """
            df = con.execute(sql).df()
            con.close()
            return df
        except Exception:  # noqa: BLE001
            pass

    con.close()
    return pd.DataFrame()


@st.cache_data(show_spinner=False, ttl=300)
def _dash_top_permits(town_slug: str) -> pd.DataFrame:
    """
    Return the top 5 permits by estimated cost for the Permits panel.
    Gracefully handles missing / differently-named cost columns.
    Always returns a DataFrame (may be empty).
    """
    pmap = _parquet_map(town_slug)
    if "permits" not in pmap:
        return pd.DataFrame()

    con = duckdb.connect()
    # Discover actual columns so we can pick the right cost/address columns
    try:
        schema_df = con.execute(
            f"DESCRIBE SELECT * FROM read_parquet('{pmap['permits']}')"
        ).df()
        cols = set(schema_df["column_name"].str.lower())
    except Exception:  # noqa: BLE001
        con.close()
        return pd.DataFrame()

    # Pick the best cost column available
    cost_col = next(
        (c for c in ["estimated_cost", "estimated_value", "permit_value", "valuation", "amount"] if c in cols),
        None,
    )
    # Pick the best address/identifier column available
    addr_col = next(
        (c for c in ["address", "location", "site_address", "property_address",
                     "permit_number", "permit_id"] if c in cols),
        None,
    )
    # Pick the best permit-type column available
    type_col = next(
        (c for c in ["permit_type", "work_type", "description", "permit_description"] if c in cols),
        None,
    )

    select_parts: list[str] = []
    if addr_col:
        select_parts.append(f"{addr_col} AS address")
    if type_col:
        select_parts.append(f"{type_col} AS permit_type")
    if cost_col:
        select_parts.append(f"CAST({cost_col} AS DOUBLE) AS estimated_cost")

    if not select_parts:
        # No useful columns — just return raw top rows
        try:
            df = con.execute(
                f"SELECT * FROM read_parquet('{pmap['permits']}') LIMIT 5"
            ).df()
            con.close()
            return df
        except Exception:  # noqa: BLE001
            con.close()
            return pd.DataFrame()

    order_clause = f"ORDER BY CAST({cost_col} AS DOUBLE) DESC NULLS LAST" if cost_col else ""
    sql = f"""
        SELECT {', '.join(select_parts)}
        FROM read_parquet('{pmap["permits"]}')
        {order_clause}
        LIMIT 5
    """
    try:
        df = con.execute(sql).df()
        con.close()
        return df
    except Exception:  # noqa: BLE001
        con.close()
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _discover_towns() -> list[str]:
    """Sorted list of town slugs that have at least one parquet file."""
    if not _GOLD_DIR.exists():
        return ["arlington-ma", "woburn-ma", "somerville-ma",
                "burlington-ma", "winchester-ma", "lexington-ma"]
    towns = sorted(
        d.name for d in _GOLD_DIR.iterdir()
        if d.is_dir() and any(d.glob("*.parquet"))
    )
    return towns or ["arlington-ma", "woburn-ma", "somerville-ma",
                     "burlington-ma", "winchester-ma", "lexington-ma"]


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Municipal Intelligence Terminal",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Minimal dark-terminal CSS tweak for the B2B aesthetic
st.markdown(
    """
    <style>
    .block-container { padding-top: 1.5rem; }
    .stChatMessage [data-testid="stMarkdownContainer"] p { font-size: 0.95rem; }
    code { font-size: 0.82rem !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("## 🏛️ TownEye")
    st.caption("Municipal Intelligence Terminal")
    st.divider()

    if st.button("🏠 Home / Clear Terminal", use_container_width=True, type="primary"):
        st.session_state.messages = []
        st.rerun()

    st.divider()

    towns = _discover_towns()
    selected_town = st.selectbox(
        "Active municipality",
        options=towns,
        index=0,
        help="Loads Gold Parquet files from data/gold/{town}/",
    )

    st.divider()

    with st.expander("📦 Data inventory", expanded=False):
        town_dir = _GOLD_DIR / selected_town
        if town_dir.exists():
            parquet_files = sorted(town_dir.glob("*.parquet"))
            if parquet_files:
                for f in parquet_files:
                    try:
                        n = len(pd.read_parquet(f))
                        st.write(f"✅ `{f.stem}` — {n:,} rows")
                    except Exception:  # noqa: BLE001
                        st.write(f"⚠️ `{f.stem}` — unreadable")
            else:
                st.write("No parquet files found.")
        else:
            st.write(f"`{town_dir}` does not exist yet.")

    st.divider()
    st.caption(
        "Engine: DuckDB SQL agent\n\n"
        "Gemini writes the query → DuckDB executes it → "
        "Gemini synthesises the answer.\n\n"
        "🗺️ Address queries trigger a live MassGIS zoning lookup."
    )

# ---------------------------------------------------------------------------
# Main area
# ---------------------------------------------------------------------------

town_title = selected_town.replace("-", " ").title()
st.title(f"{town_title}: Municipal Intelligence Terminal")
st.caption(
    "Live Gold-tier data · DuckDB SQL engine · Gemini 2.5 Flash synthesis"
)

# Reset history on town change
if st.session_state.get("active_town") != selected_town:
    st.session_state.messages = []
    st.session_state.active_town = selected_town

# Build schema context once per town (cached)
schema_context = get_schema_context(selected_town)

# ── Only show the dashboard + presets when no conversation is in progress ──
if not st.session_state.get("messages"):

    # ── Dashboard ────────────────────────────────────────────────────────────
    st.markdown("### 📡 At a Glance")
    dash_left, dash_right = st.columns([1, 1], gap="large")

    # Left — Town Pulse
    with dash_left:
        st.markdown("#### 🚦 Town Pulse & Traffic Alerts")
        pulse_df = _dash_town_pulse(selected_town)
        if pulse_df.empty:
            st.info("No active traffic or service alerts.", icon="✅")
        else:
            for _, row in pulse_df.iterrows():
                alert_text = str(row.get("alert", ""))
                when_text  = str(row.get("when",  "")).strip()
                detail_text = str(row.get("detail", "")).strip()
                when_badge = f" `{when_text}`" if when_text and when_text != "nan" else ""
                detail_md  = f"\n  _{detail_text}_" if detail_text and detail_text != "nan" else ""
                st.markdown(f"- **{alert_text}**{when_badge}{detail_md}")

    # Right — Top 5 Permits by Value
    with dash_right:
        st.markdown("#### 📋 Top 5 Building Permits by Value")
        permits_df = _dash_top_permits(selected_town)
        if permits_df.empty:
            st.info("No permit data available for this town.", icon="📭")
        else:
            # Format the cost column nicely if it exists
            display_df = permits_df.copy()
            if "estimated_cost" in display_df.columns:
                display_df["estimated_cost"] = display_df["estimated_cost"].apply(
                    lambda v: f"${v:,.0f}" if pd.notna(v) else "—"
                )
            st.dataframe(display_df, use_container_width=True, hide_index=True)

    st.divider()

    # ── Preset analysis buttons ───────────────────────────────────────────────
    st.markdown("### ⚡ Run Analysis")
    # Two rows of buttons: 3 + 2
    row1 = st.columns(3, gap="small")
    row2 = st.columns(2, gap="small")
    all_cols = row1 + row2
    for col, (label, query) in zip(all_cols, _ANALYSIS_PRESETS):
        if col.button(label, use_container_width=True):
            st.session_state.messages.append({"role": "user", "content": query})
            st.rerun()

    st.divider()
    st.markdown(
        "_Or type any natural-language query in the box below — "
        "the agent will auto-generate SQL, execute it, and synthesise the answer._"
    )

# ---------------------------------------------------------------------------
# Render conversation history
# ---------------------------------------------------------------------------

for msg in st.session_state.get("messages", []):
    role = msg["role"]
    with st.chat_message(role, avatar="🧑‍💼" if role == "user" else "🤖"):
        st.markdown(msg["content"])
        if role == "assistant":
            if msg.get("df") is not None and not msg["df"].empty:
                with st.expander(
                    f"📊 Raw data — {len(msg['df']):,} rows", expanded=False
                ):
                    st.dataframe(msg["df"], use_container_width=True)
            if msg.get("sql"):
                with st.expander("🔍 Generated SQL", expanded=False):
                    st.code(msg["sql"], language="sql")
            if msg.get("sql_error"):
                st.error(f"SQL error: {msg['sql_error']}")

# ---------------------------------------------------------------------------
# Query input
# ---------------------------------------------------------------------------

if prompt := st.chat_input("Ask the Municipal Agent a custom query…"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.rerun()

# ---------------------------------------------------------------------------
# Agent execution  (fires when last message is from the user)
# ---------------------------------------------------------------------------

if st.session_state.get("messages") and st.session_state.messages[-1]["role"] == "user":
    pending = st.session_state.messages[-1]["content"]

    with st.chat_message("user", avatar="🧑‍💼"):
        st.markdown(pending)

    # Live address / zoning lookup (runs before the agent)
    address_context: str | None = None
    with st.spinner("🗺️ Checking for address reference…"):
        address_context = _address_zoning_lookup(pending, selected_town)
    if address_context:
        st.info(
            f"📍 **Live MassGIS Zoning Lookup**\n```\n{address_context}\n```",
            icon="🗺️",
        )

    # Agent loop inside st.status
    agent_result: dict = {}
    with st.status("⚙️ Querying Municipal Data…", expanded=True) as status_box:
        try:
            agent_result = run_agent(
                question=pending,
                schema_context=schema_context,
                address_context=address_context,
                status_container=status_box,
            )
        except Exception as exc:  # noqa: BLE001
            agent_result = {
                "sql": None, "sql_error": str(exc),
                "df": None, "summary": f"Agent error: {exc}",
            }
        status_box.update(label="✅ Analysis complete", state="complete", expanded=False)

    # Render assistant response
    with st.chat_message("assistant", avatar="🤖"):
        st.markdown(agent_result.get("summary", ""))

        df_result: pd.DataFrame | None = agent_result.get("df")
        if df_result is not None and not df_result.empty:
            st.markdown(f"**📊 Result — {len(df_result):,} rows**")
            st.dataframe(df_result, use_container_width=True)

        if agent_result.get("sql"):
            with st.expander("🔍 Generated SQL", expanded=False):
                st.code(agent_result["sql"], language="sql")

        if agent_result.get("sql_error"):
            st.error(f"SQL error: {agent_result['sql_error']}")

    # Persist to history (store df so the grid re-renders on scroll-back)
    st.session_state.messages.append({
        "role":      "assistant",
        "content":   agent_result.get("summary", ""),
        "sql":       agent_result.get("sql"),
        "sql_error": agent_result.get("sql_error"),
        "df":        agent_result.get("df"),
    })
    st.rerun()
