"""Universal Medallion Factory — core engine."""

from .config_loader import ConfigLoader
from .factory import MedallionFactory
from .identity_linker import HashLinker, PartyLinker, get_linker
from .llm_client import call_llm, select_provider
from .storage import get_parquet_path, save_gold_data
from .discovery_agent import DiscoveryAgent
from .models import (
    AuditFields,
    PartyType,
    TeBroadband,
    TeClimateZone,
    TeEquityIndex,
    TeEvent,
    TeInfraProject,
    TeMarketTrend,
    TeParty,
    TePartyRelationship,
    TePermit,
    TeStrDynamics,
    TeTownProfile,
    TeZoning,
    # Backward-compat aliases
    TownEyeAuditShield,
    Party,
    PartyRelationship,
    Event,
)

__all__ = [
    # Primary public API
    "MedallionFactory",
    "ConfigLoader",
    "PartyLinker",
    "HashLinker",
    "get_linker",
    # LLM client
    "call_llm",
    "select_provider",
    # Storage router
    "get_parquet_path",
    "save_gold_data",
    # Expansion + Discovery agents
    "DiscoveryAgent",
    # Canonical model names
    "AuditFields",
    "PartyType",
    "TeParty",
    "TePartyRelationship",
    "TeEvent",
    "TeZoning",
    "TeMarketTrend",
    "TeInfraProject",
    "TePermit",
    "TeBroadband",
    "TeClimateZone",
    "TeEquityIndex",
    "TeTownProfile",
    "TeStrDynamics",
    # Backward-compat aliases
    "TownEyeAuditShield",
    "Party",
    "PartyRelationship",
    "Event",
]
