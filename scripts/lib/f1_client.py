"""
f1_client.py — Drop-in Anthropic SDK client routed through the F1 proxy.

F1 (https://store.mini-on-ai.com/f1) is a BYOK Anthropic cost-tracking proxy.
All calls go to api.anthropic.com via F1, which records token usage + USD
cost to a D1 database without storing prompt content.

Usage — for scripts that currently do `anthropic.Anthropic()`:

    from lib.f1_client import make_client
    client = make_client()
    # Then use client exactly like anthropic.Anthropic()

Usage — for scripts that currently do `from lib.claude_cli import claude_call`:

    from lib.f1_client import claude_call
    text, usage = claude_call(prompt, model="haiku")
    # Same signature as claude_cli.claude_call(), no other changes needed.

Environment variables:
    F1_API_KEY      — your F1 API key (f1_key_...). If unset, falls back to
                      direct Anthropic API with a warning.
    F1_PROXY_URL    — F1 Worker URL (default: https://f1-api.kirozdormu.workers.dev/v1)
    ANTHROPIC_API_KEY — used as fallback when F1_API_KEY is not set.
"""

import os
import sys
from typing import List, Optional, Tuple

from lib.utils import sans_reflexion

# ─────────────────────────────────────────────────────────────────────────────
# Build client
# ─────────────────────────────────────────────────────────────────────────────

_F1_PROXY_URL_DEFAULT = "https://f1-api.kirozdormu.workers.dev/v1"


def make_client():
    """
    Return an anthropic.Anthropic() client.

    If F1_API_KEY is set: routes through F1 proxy (base_url override).
    Otherwise: falls back to direct Anthropic API with a deprecation warning.
    """
    import anthropic

    f1_key = os.getenv("F1_API_KEY")
    proxy_url = os.getenv("F1_PROXY_URL", _F1_PROXY_URL_DEFAULT)
    # The SDK adds /v1/messages itself, so a base URL ending in /v1 would call /v1/v1/messages (404).
    proxy_url = proxy_url.rstrip("/").removesuffix("/v1")

    if f1_key:
        # F1 reads the key from "Authorization: Bearer"; api_key would send it as x-api-key,
        # which F1 rejects with a 401. auth_token sends the Bearer header.
        return anthropic.Anthropic(
            base_url=proxy_url,
            auth_token=f1_key,
        )

    # Fallback: direct Anthropic API. Warn so it's visible during migration.
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    print(
        "[f1_client] WARNING: F1_API_KEY not set — falling back to direct Anthropic API. "
        "Set F1_API_KEY in .env to route through F1 for cost tracking. "
        "(This will fail after June 15, 2026 unless you migrate.)",
        file=sys.stderr,
    )
    return anthropic.Anthropic(api_key=anthropic_key)


# ─────────────────────────────────────────────────────────────────────────────
# Compatibility shim: claude_call() — drop-in for lib.claude_cli.claude_call()
# ─────────────────────────────────────────────────────────────────────────────

# Map legacy model aliases to current Anthropic model IDs
_MODEL_ALIASES = {
    "haiku": "claude-haiku-5-5",
    "sonnet": "claude-sonnet-5-5",
    "opus": "claude-opus-5-5",
    # Passthrough: if it's already a full model ID, use as-is
}

_DEFAULT_MODEL = "claude-sonnet-5-5"


def claude_call(
    prompt: str,
    *,
    system: Optional[str] = None,
    model: Optional[str] = None,
    tools: Optional[List[str]] = None,
    timeout: int = 300,
    cwd: Optional[str] = None,  # ignored — only existed for CLI subprocess
) -> Tuple[str, dict]:
    """
    Compatibility replacement for lib.claude_cli.claude_call().

    Same call signature. Does NOT support tools that were CLI-only (WebSearch,
    WebFetch) — raise ValueError if those are requested so callers know to
    update. Plain text completions work identically.

    Args:
        prompt:  User prompt.
        system:  Optional system prompt.
        model:   Model alias ('haiku', 'sonnet', 'opus') or full model ID.
        tools:   Ignored if empty/None. Raises ValueError for CLI-only tools.
        timeout: Per-request timeout in seconds (default 300).
        cwd:     Ignored (was for subprocess CWD in claude_cli).

    Returns:
        (result_text, usage_dict) — usage has keys input_tokens, output_tokens, etc.
    """
    if tools:
        unsupported = [t for t in tools if t in ("WebSearch", "WebFetch", "Bash")]
        if unsupported:
            raise ValueError(
                f"f1_client.claude_call() does not support CLI-only tools: {unsupported}. "
                "These require a separate search API integration (e.g. Brave Search). "
                "If these calls are low-volume, they can remain on claude -p within the "
                "Max 5x $100/mo Agent SDK credit cap until reworked."
            )

    model_id = _MODEL_ALIASES.get(model, model) if model else _DEFAULT_MODEL

    client = make_client()

    messages = [{"role": "user", "content": prompt}]

    kwargs = dict(
        model=model_id,
        max_tokens=8096,
        messages=messages,
        **sans_reflexion(model_id),
    )
    if system:
        kwargs["system"] = system

    # Apply timeout via httpx transport if available, else best-effort
    try:
        response = client.messages.create(**kwargs, timeout=float(timeout))
    except Exception as e:
        raise RuntimeError(f"f1_client.claude_call() failed: {e}") from e

    # Opus 5.5 always thinks, so its reply can start with a thinking block: keep only the text.
    text = "".join(b.text for b in response.content if getattr(b, "type", "") == "text")
    usage = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "cache_creation_input_tokens": getattr(response.usage, "cache_creation_input_tokens", 0),
        "cache_read_input_tokens": getattr(response.usage, "cache_read_input_tokens", 0),
    }
    return text, usage


def claude_text(prompt: str, **kwargs) -> str:
    """Like claude_call() but returns only the text string."""
    text, _ = claude_call(prompt, **kwargs)
    return text
