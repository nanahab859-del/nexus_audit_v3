"""Shared utility functions for the infra layer."""
from __future__ import annotations


def deep_merge(target: dict, source: dict) -> None:
    """
    Recursively merge source into target in-place.
    Dicts are merged recursively; all other types overwrite.

    Example:
        target = {"a": {"b": 1, "c": 2}}
        source = {"a": {"b": 99, "d": 3}}
        deep_merge(target, source)
        # target == {"a": {"b": 99, "c": 2, "d": 3}}
    """
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            deep_merge(target[key], value)
        else:
            target[key] = value
