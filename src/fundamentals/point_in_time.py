"""
Point-in-time gating layer for SEC XBRL observations.

Why this module exists
-----------------------
Framework v2.0 (finalized 2026-09-13, see project design docs) locks in
one non-negotiable discipline: a metric's value "as of" some evaluation
date must only ever be built from filings that were PUBLICLY AVAILABLE
by that date. Concretely: an observation is usable only if

    observation["filed"] <= evaluation_date

Never gate on the observation's economic period (`start`/`end`) alone --
a company can file a 10-K for fiscal year 2024 as late as several months
into 2025, and SEC filings are sometimes restated. Using period_end
instead of filed_date as the availability cutoff is exactly how
look-ahead bias sneaks into a "historical" backtest.

This module does NOT do concept selection (which XBRL tag represents
"revenue") -- that is src/fundamentals/sec_normalizer.py's job. It does
NOT do annual/quarterly reconstruction (Q2 = H1 - Q1, etc.) -- that is
src/fundamentals/sec_history.py's job. This module is a thin, pure
composition layer that sits between them: look up one already-identified
concept's raw observations (via sec_normalizer.find_concept), gate them
to only those filed on or before the evaluation date, and hand the
gated, still-fully-provenanced list to sec_history.py for reconstruction.

Nothing here flattens or drops SEC provenance fields (filed/start/end/
accn) -- gating only removes whole observations that were not yet public,
it never rewrites the ones that remain.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from src.fundamentals.sec_normalizer import find_concept
from src.fundamentals.sec_history import extract_concept_history

SCHEMA_VERSION = "point_in_time_v0.1"


# ============================================================
# DATE HELPERS
# ============================================================

def _parse_date(value: Any) -> date | None:
    """Parse an ISO 'YYYY-MM-DD' string (or a date/datetime already) into
    a date. Returns None for anything unparseable -- callers treat that
    as "no filing date on record", which fails the gate closed (excluded),
    never open."""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None

    return None


def coerce_evaluation_date(value: Any) -> date:
    """Normalize the caller-supplied evaluation date into a date object.
    Raises ValueError rather than silently falling back to today's date
    or an unbounded gate -- an unparseable evaluation date is a caller
    bug, not something to paper over, since it directly controls
    look-ahead-bias protection."""
    parsed = _parse_date(value)

    if parsed is None:
        raise ValueError(
            f"evaluation_date could not be parsed as an ISO date: {value!r}"
        )

    return parsed


# ============================================================
# OBSERVATION-LEVEL GATING
# ============================================================

def is_observation_available_as_of(
    observation: dict,
    evaluation_date: date,
) -> bool:
    """
    True only if this observation's filing date is on or before
    evaluation_date. An observation with a missing or unparseable
    'filed' field is treated as NOT available -- the gate fails closed,
    never open, since a missing filed date means we cannot prove the
    data was public by evaluation_date.
    """
    filed = _parse_date(observation.get("filed"))

    if filed is None:
        return False

    return filed <= evaluation_date


def filter_observations_as_of(
    observations: list[dict],
    evaluation_date: date,
) -> list[dict]:
    """Keep only observations available as of evaluation_date. Order and
    every field on the surviving observations are preserved unchanged."""
    return [
        observation
        for observation in observations
        if is_observation_available_as_of(observation, evaluation_date)
    ]


# ============================================================
# CONCEPT-BLOCK-LEVEL GATING
# ============================================================

def as_of_concept_data(
    concept_data: dict,
    evaluation_date: date,
) -> dict:
    """
    Given a raw SEC Company Facts concept block
    (`{"label": ..., "units": {"USD": [...], ...}}`), return a new block
    of the same shape whose per-unit observation lists have been gated
    to evaluation_date. The input is never mutated. Non-list `units`
    entries and non-dict observations are dropped defensively (mirrors
    sec_history.extract_concept_history's own defensive handling), not
    raised on, since malformed SEC data should degrade to "no usable
    observations" rather than crash a point-in-time build.
    """
    if not isinstance(concept_data, dict):
        raise ValueError("concept_data must be a dictionary")

    units = concept_data.get("units")

    if not isinstance(units, dict):
        raise ValueError("concept_data.units must be a dictionary")

    gated_units: dict[str, list[dict]] = {}

    for unit_name, unit_observations in units.items():
        if not isinstance(unit_observations, list):
            continue

        valid_observations = [
            observation
            for observation in unit_observations
            if isinstance(observation, dict)
        ]

        gated_units[unit_name] = filter_observations_as_of(
            valid_observations,
            evaluation_date,
        )

    result = dict(concept_data)
    result["units"] = gated_units

    return result


# ============================================================
# END-TO-END: LOOKUP -> GATE -> RECONSTRUCT
# ============================================================

def get_point_in_time_history(
    data: dict,
    namespace: str,
    concept_name: str,
    evaluation_date: Any,
) -> dict | None:
    """
    Look up one already-identified XBRL concept
    (namespace + concept_name -- the caller decides which concept
    represents the metric, e.g. via sec_normalizer's concept-priority
    helpers; this function does not choose among candidates), gate its
    observations to what was publicly available as of evaluation_date,
    and reconstruct annual/quarterly/standalone-quarter history from the
    gated set via sec_history.extract_concept_history().

    Returns None if the concept does not exist in `data` at all (matches
    sec_normalizer.find_concept's own None-on-missing behavior). Returns
    an empty-but-valid history structure if the concept exists but every
    observation was filed after evaluation_date (nothing was public yet
    -- a real, expected state for e.g. a newly-listed company evaluated
    shortly after IPO, not an error).
    """
    evaluation_date = coerce_evaluation_date(evaluation_date)

    concept_data = find_concept(data, namespace, concept_name)

    if concept_data is None:
        return None

    gated_concept_data = as_of_concept_data(concept_data, evaluation_date)

    history = extract_concept_history(gated_concept_data)
    history["evaluation_date"] = evaluation_date.isoformat()
    history["namespace"] = namespace
    history["concept"] = concept_name

    return history
