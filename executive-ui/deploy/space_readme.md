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
on-demand analysis of any new opportunity you describe — powered entirely by
a small local model (Ollama) baked into this Space, no paid API key required.

This Space is auto-deployed from the project's GitHub repository on every
push to `main`. See `executive-ui/README.md` in the source repo for how it
works, including the honesty guarantees (an AI-generated opportunity can
never be marked "validated" or "strong" — every generated scorecard is
capped by the real scoring engine).
