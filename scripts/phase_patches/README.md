# Phase patch scripts (historical archive)

These `patch_web_phase*.py` scripts are **one-off, historical** tooling used to
wire each incremental web phase into `pradyos/sovereign_web.py` as the OS was
built out. They are kept for provenance only — they are **not** part of the build,
the test suite, or any runtime path, and nothing imports them.

The capabilities they once added now live as first-class route modules under
`pradyos/web/` and are registered directly in `pradyos.sovereign_web.create_app()`.
There is no need to run these scripts; treat them as an append-only changelog of
how the surface grew.
