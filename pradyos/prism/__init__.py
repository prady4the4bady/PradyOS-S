"""PRISM — creative generation & interface-artifact production (Agent PRISM).

v5.0 blueprint §4.4 / Part V. PRISM produces the OS's creative output — documents,
reports, sites, code bundles, decks, images, apps — and curates the Artifact
Gallery the Sovereign browses. It tracks each artifact through a generation
lifecycle (requested → generating → ready / failed) and supports variants.

Dependency-free and deterministic (it models the production lifecycle; a backend
wires the actual generation).

Public surface:
    Prism          — request / start / deliver / fail / add_variant / gallery
    ARTIFACT_KINDS — recognised artifact kinds
    PrismError     — typed failures
"""

from __future__ import annotations

from pradyos.prism.prism import ARTIFACT_KINDS, Prism, PrismError

__all__ = ["Prism", "ARTIFACT_KINDS", "PrismError"]
