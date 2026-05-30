"""Buildability Brief service — wraps existing generator."""

from __future__ import annotations

from datetime import date

from reports.buildability_brief import BriefInputs, BriefData, BuildabilityBriefGenerator

from backend.config import get_settings


def get_generator(town_slug: str) -> BuildabilityBriefGenerator:
    return BuildabilityBriefGenerator(
        town_slug=town_slug,
        data_dir=get_settings().gold_data_path,
        config_dir=get_settings().config_dir,
    )


def collect_brief_data(
    town_slug: str,
    parcel_id: str,
    prepared_for: str | None = None,
) -> BriefData:
    gen = get_generator(town_slug)
    return gen.collect_data(
        BriefInputs(
            town_slug=town_slug,
            parcel_id=parcel_id,
            prepared_for=prepared_for,
            prepared_on=date.today(),
        ),
    )


def generate_buildability_html(
    town_slug: str,
    parcel_id: str,
    prepared_for: str | None = None,
) -> str:
    gen = get_generator(town_slug)
    return gen.generate(
        BriefInputs(
            town_slug=town_slug,
            parcel_id=parcel_id,
            prepared_for=prepared_for,
            prepared_on=date.today(),
        ),
    )
