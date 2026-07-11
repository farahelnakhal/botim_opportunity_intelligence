# shared/ — Integration Layer

Jointly-owned assets of the combined agent (change only by agreement between both contributors — see `WORKSTREAMS.md`).

- **`integration_check.py`** — the pre-push gate. Runs Workstream A's conformance checker and unit tests, Workstream B's engine tests and knowledge-base sweep, and the cross-module test suites below. **Must pass with zero failures before anything lands on `main`.**
  ```bash
  python3 shared/integration_check.py
  ```
- **`tests/test_integration.py`** — the A↔B contract: both parsers agree on every record and score; every EV/SEG/IP reference in B's artefacts resolves into A's knowledge base; the sync bridge's axis→dimension mapping accounts for all ten axes; module isolation holds.
- **`tests/test_e2e_pipeline.py`** — a synthetic opportunity driven through the entire combined pipeline in an isolated sandbox (evidence → scorecard → models → experiment → verdict → backlog → journal), plus a deliberate-corruption test proving the sweep catches breakage.
- **`tests/test_cli_smoke.py`** — every CLI command as a real subprocess: success paths, typed failure paths, determinism, and the journal anti-contamination guard.
