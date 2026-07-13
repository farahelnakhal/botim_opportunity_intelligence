"""Read-only JSON API for the BOTIM Opportunity Intelligence assistant UI.

This package exposes the existing engines and the evidence-impact workflow as
JSON over HTTP for the React front-end. It is strictly read-only: it never
scores, never reinterprets confidence, never writes to the knowledge base. All
numbers come from the engines via the executive-ui adapter (the single source
of truth); the API only serialises them.
"""
