"""REPOSITORY PROVING GROUND — autonomous repo admission pipeline.

The Proving Ground is where IMPERIUM tests and admits new code repositories
before granting them any operational authority within PRADY OS.

Admission verdict taxonomy:

    ADMITTED     — all tests green, constitution clean, dependency audit passed
    QUARANTINED  — tests fail or suspicious patterns detected; no elevation
    REJECTED     — hard constitutional violations; repo blocked permanently

Phase 1 capabilities:
    - Clone any git URL into a sandboxed workspace
    - Run the repo's own test suite via TITAN OPS (SANDBOX lane)
    - Scan imports and commands for constitutional violations
    - Report a structured AdmissionVerdict to IMPERIUM

Phase 4 wires full kernel-level isolation (nsjail / bwrap / firejail).
For Phase 1, isolation is software-only via the SANDBOX lane and a dedicated
temp directory. Repos are never executed with PRIVILEGED lane access.
"""
