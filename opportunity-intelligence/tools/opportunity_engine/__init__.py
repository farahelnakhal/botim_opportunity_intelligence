"""Opportunity Intelligence engine (Workstream B).

Computation layer for the markdown frameworks in opportunity-intelligence/:
- commercial: three-case commercial model (contribution, break-even, subsidy ceilings)
- subsidy: MDR/interchange subsidy budget for card products
- scoring: 17-dimension scorecard validation, caps and floors
- evidence: read-only parser for Workstream A records in
  knowledge-base/customer-evidence/records/ (EV-YYYY-Wnn-nnn format)
- experiments: validator for VE-*.md specs (mandatory fields, quantified
  pre-committed thresholds)
- backlog: parser and integrity checker for BACKLOG.md
- sensitivity: tornado analysis and two-way stress grids
- results: verdict engine for experiment results vs pre-committed thresholds
- montecarlo: seeded Monte Carlo over the three-case model
- stress: named correlated adverse scenarios (credit-and-run, ...)
- journal: calibrated decision journal (Brier-scored predictions)

Pure standard library. Inputs are JSON files kept in the module's own
knowledge-base folders; Workstream A files are never written.
"""

__all__ = [
    "commercial", "subsidy", "scoring", "evidence",
    "experiments", "backlog", "sensitivity", "results",
    "montecarlo", "stress", "journal",
]
