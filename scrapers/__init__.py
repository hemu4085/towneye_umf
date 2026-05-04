"""TownEye UMF -- Universal Scrapers package.

Each ``universal_*.py`` module is a town-agnostic CLI entry-point for one
domain.  All scraping logic lives in the corresponding implementation module
(e.g. ``property_scraper.py``, ``zoning_scraper.py``) which reads all
configuration from ``configs/{town_slug}/config.yaml`` and therefore works
for any onboarded municipality without code changes.

Domain map
----------
01  property        — scrapers/universal_property.py
02  zoning          — scrapers/universal_zoning.py
03  market-trends   — scrapers/universal_market.py
04  infra-projects  — scrapers/universal_dpw.py
05  permits         — scrapers/universal_permits.py
06  broadband       — scrapers/universal_broadband.py
07  climate-zones   — scrapers/universal_climate.py
08  transit         — scrapers/universal_transit.py
09a 311             — scrapers/universal_311.py
09b school-calendar — scrapers/universal_schools.py
10  equity-index    — scrapers/universal_equity.py
11  town-profile    — scrapers/universal_town_profile.py
12  str-dynamics    — scrapers/universal_str.py
"""
