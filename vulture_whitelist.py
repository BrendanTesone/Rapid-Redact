"""
Vulture whitelist for intentionally unused code.

This file documents code that appears unused but is actually required by
external APIs, protocols, or frameworks.
"""

# Flet event handler parameters - required by Flet API signature
_.event  # Protocol method signatures in page_renderer.py

# Function parameters required by API contracts but not used internally
_.padding_pt  # snap_to_text_bounds default parameter (API compatibility)
_.proximity_words  # _has_dosing_context_keyword parameter (future use)
_.throttled  # deep_consistency_scan parameter (feature flag)
