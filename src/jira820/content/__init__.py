"""Locale-specific text and name pools for deterministic data generation."""

from . import en, ko

_POOLS = {"en": en, "ko": ko}


def get(locale: str):
    return _POOLS.get((locale or "en").lower(), en)
