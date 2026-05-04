# [FILE PATH]: core/config_loader.py
# Patch #179
# Execution Mode: Town-Specific Configuration Loader
# Date: 2026-03-03

import logging
import os
import pathlib
from functools import lru_cache
from typing import Any, Dict, Optional

import yaml

logger = logging.getLogger(__name__)


class ConfigLoader:
    """
    Loads and caches town-specific YAML configuration.

    Guarantees Zero-Hardcoding compliance: all town context is read from
    ``configs/{town_slug}/config.yaml`` at runtime — never from literals
    embedded in core logic.

    Instantiation styles
    --------------------
    Original (used by MedallionFactory and older scrapers)::

        loader = ConfigLoader(base_dir="configs")
        cfg    = loader.get_town_config("arlington-ma")

    Convenience shorthand (used by newer scrapers)::

        cfg = ConfigLoader(town_slug="arlington-ma").load()

    Both styles are fully supported and produce identical results.
    """

    # ------------------------------------------------------------------
    # Global legal disclaimer — available to any reporting script that
    # instantiates a ConfigLoader.  Centralised here so it can never
    # diverge between report templates.
    # ------------------------------------------------------------------
    LEGAL_DISCLAIMER: str = (
        "TownEye or any of its products data, including qualitative market "
        "summaries and STR estimates, is generated via AI synthesis and is "
        "for informational purposes only. Users must independently verify "
        "all zoning, regulatory, and financial data with official municipal "
        "authorities before making investment decisions."
    )

    def __init__(
        self,
        base_dir: str = "configs",
        town_slug: Optional[str] = None,
    ) -> None:
        self.base_path  = pathlib.Path(base_dir)
        self._town_slug = town_slug

    # ------------------------------------------------------------------
    # Convenience shorthand for the newer scraper pattern
    # ------------------------------------------------------------------

    def load(self) -> Dict[str, Any]:
        """
        Load and return the config for the ``town_slug`` provided at
        construction time.

        Raises
        ------
        ValueError
            When the instance was constructed without a ``town_slug``.
        """
        if not self._town_slug:
            raise ValueError(
                "ConfigLoader.load() requires a town_slug. "
                "Pass it as ConfigLoader(town_slug='arlington-ma').load(), "
                "or use get_town_config(slug) on a base-dir instance."
            )
        return self.get_town_config(self._town_slug)

    # ------------------------------------------------------------------
    # Core config loader
    # ------------------------------------------------------------------

    @lru_cache(maxsize=32)
    def get_town_config(self, town_slug: str) -> Dict[str, Any]:
        """
        Load the YAML config for *town_slug*, with in-process LRU caching
        to prevent redundant disk I/O across repeated calls.

        Parameters
        ----------
        town_slug : str
            Kebab-case municipality identifier (e.g. ``'arlington-ma'``).

        Returns
        -------
        dict
            Parsed YAML content, guaranteed to include a ``town_slug`` key.

        Raises
        ------
        FileNotFoundError
            When no config directory exists for the given slug.
        """
        config_file = self.base_path / town_slug / "config.yaml"

        logger.info(
            "ConfigLoader | Fetching config for town_slug='%s' from '%s'",
            town_slug,
            config_file,
        )

        if not config_file.exists():
            logger.error(
                "ConfigLoader | No config found for town_slug='%s'. "
                "Expected path: %s",
                town_slug,
                config_file,
            )
            raise FileNotFoundError(
                f"No configuration found for town: '{town_slug}'. "
                f"Expected path: {config_file}"
            )

        with open(config_file, "r") as f:
            config_data: Dict[str, Any] = yaml.safe_load(f)

        if "town_slug" not in config_data:
            config_data["town_slug"] = town_slug

        logger.info(
            "ConfigLoader | Loaded config for town_slug='%s' "
            "(geo_hash=%s, version=%s)",
            town_slug,
            config_data.get("geo_hash", "N/A"),
            config_data.get("version", "N/A"),
        )

        return config_data

    # ------------------------------------------------------------------
    # Legal disclaimer accessor
    # ------------------------------------------------------------------

    def get_legal_disclaimer(self) -> str:
        """
        Return the platform-wide legal disclaimer text.

        This method is the canonical way for reporting scripts and LLM
        synthesis scrapers to access the disclaimer, ensuring the exact
        wording is always sourced from a single location.

        Returns
        -------
        str
            The full disclaimer string defined in ``LEGAL_DISCLAIMER``.
        """
        return self.LEGAL_DISCLAIMER

    # ------------------------------------------------------------------
    # Environment helpers
    # ------------------------------------------------------------------

    @staticmethod
    def is_production() -> bool:
        """
        Return ``True`` when the process is running in production mode.

        The check is intentionally simple and explicit: the caller must
        *opt in* to production by setting ``TOWNEYE_ENV=production``.
        Any other value (including an unset variable) is treated as a
        development/test environment so that local runs are always safe
        by default.

        Returns
        -------
        bool
            ``True``  iff ``os.environ["TOWNEYE_ENV"] == "production"``.
            ``False`` in all other cases (variable absent, set to "dev",
            "staging", "test", etc.).

        Examples
        --------
        ::

            # In a shell:
            # export TOWNEYE_ENV=production
            # python run_pipeline.py --town arlington-ma

            from core.config_loader import ConfigLoader

            if ConfigLoader.is_production():
                print("Running in PRODUCTION — data will be written to GCS.")
            else:
                print("Running in DEV — data will be written to data/gold/.")
        """
        return os.environ.get("TOWNEYE_ENV", "").lower() == "production"


# core/config_loader.py
# End of Patch #181
