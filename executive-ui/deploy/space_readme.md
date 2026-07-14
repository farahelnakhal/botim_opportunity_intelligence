---
title: BOTIM Opportunity Intelligence
emoji: 📊
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# BOTIM Opportunity Intelligence

A read-only assistant over BOTIM's product-opportunity engines, plus an
on-demand analysis of any new opportunity you describe. AI generation is
delegated to whichever OpenAI-compatible LLM endpoint is configured via this
Space's environment variables (e.g. a free provider like Groq — no card
required); with none configured it falls back to an honest offline scaffold.

This Space is auto-deployed from the project's GitHub repository on every
push to `main`. See `executive-ui/README.md` in the source repo for how it
works, including the honesty guarantees (an AI-generated opportunity can
never be marked "validated" or "strong" — every generated scorecard is
capped by the real scoring engine).
