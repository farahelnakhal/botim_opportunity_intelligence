"""Compatibility shim — DO NOT ADD NEW CODE HERE.

The canonical, single-source-of-truth provider-neutral interface and
implementations now live in `shared.llm.provider` (shared across
copilot-backend, merchant-voice, and any future service). This module exists
only so existing imports of `copilot_backend...app.provider` / relative
`.provider` continue to work unchanged.

All new code — in this service or any other — MUST import directly from
`shared.llm.provider`. Do not add providers, logic, or re-exports here.
"""

from shared.llm.provider import (  # noqa: F401
    AnthropicProvider,
    ConversationModel,
    MockProvider,
    ModelResponse,
    ProviderError,
    make_provider,
)
