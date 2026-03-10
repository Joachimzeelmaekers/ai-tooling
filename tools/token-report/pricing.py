"""Pricing data per 1M tokens (USD): (input, output, cache_read, cache_write).

cache_write uses the 5-minute ephemeral cache write price (most common in CLI usage).
"""

PRICING = {
    # -------------------------------------------------------------------------
    # Claude (Anthropic) — used by Claude Code
    # Format: (base_input, output, cache_read, cache_write_5m)
    # -------------------------------------------------------------------------
    "claude-opus-4-6":             (5.00, 25.00, 0.50, 6.25),
    "claude-opus-4-5-20251101":    (5.00, 25.00, 0.50, 6.25),
    "claude-opus-4-1":             (15.00, 75.00, 1.50, 18.75),
    "claude-opus-4":               (15.00, 75.00, 1.50, 18.75),
    "claude-sonnet-4-6":           (3.00, 15.00, 0.30, 3.75),
    "claude-sonnet-4-5-20250929":  (3.00, 15.00, 0.30, 3.75),
    "claude-sonnet-4":             (3.00, 15.00, 0.30, 3.75),
    "claude-sonnet-3-7":           (3.00, 15.00, 0.30, 3.75),
    "claude-haiku-4-5-20251001":   (1.00, 5.00, 0.10, 1.25),
    "claude-haiku-3-5":            (0.80, 4.00, 0.08, 1.00),
    "claude-opus-3":               (15.00, 75.00, 1.50, 18.75),
    "claude-haiku-3":              (0.25, 1.25, 0.03, 0.30),

    # -------------------------------------------------------------------------
    # OpenCode — free-tier / internal
    # -------------------------------------------------------------------------
    "kimi-k2.5-free":    (0.0, 0.0, 0.0, 0.0),
    "glm-4.7-free":      (0.0, 0.0, 0.0, 0.0),
    "glm-5-free":        (0.0, 0.0, 0.0, 0.0),
    "big-pickle":        (0.0, 0.0, 0.0, 0.0),
    "minimax-m2.5-free": (0.0, 0.0, 0.0, 0.0),

    # -------------------------------------------------------------------------
    # OpenAI — used by OpenCode and potentially Codex
    # -------------------------------------------------------------------------
    "gpt-5.4-codex":       (2.50, 15.00, 0.25, 0.0),
    "gpt-5.4":             (2.50, 15.00, 0.25, 0.0),
    "gpt-5.4-long":        (5.00, 22.50, 0.50, 0.0),
    "gpt-5.4-pro":         (30.00, 180.00, 0.0, 0.0),
    "gpt-5.4-pro-long":    (60.00, 270.00, 0.0, 0.0),
    "gpt-5.2":             (1.75, 14.00, 0.175, 0.0),
    "gpt-5.1":             (1.25, 10.00, 0.125, 0.0),
    "gpt-5":               (1.25, 10.00, 0.125, 0.0),
    "gpt-5-mini":          (0.25, 2.00, 0.025, 0.0),
    "gpt-5-nano":          (0.05, 0.40, 0.005, 0.0),
    "gpt-5.3-chat-latest": (1.75, 14.00, 0.175, 0.0),
    "gpt-5.2-chat-latest": (1.75, 14.00, 0.175, 0.0),
    "gpt-5.1-chat-latest": (1.25, 10.00, 0.125, 0.0),
    "gpt-5-chat-latest":   (1.25, 10.00, 0.125, 0.0),
    "gpt-5.3-codex":       (1.75, 14.00, 0.175, 0.0),
    "gpt-5.2-codex":       (1.75, 14.00, 0.175, 0.0),
    "gpt-5.1-codex-max":   (1.25, 10.00, 0.125, 0.0),
    "gpt-5.1-codex":       (1.25, 10.00, 0.125, 0.0),
    "gpt-5-codex":         (1.25, 10.00, 0.125, 0.0),
    "gpt-5.2-pro":         (21.00, 168.00, 0.0, 0.0),
    "gpt-5-pro":           (15.00, 120.00, 0.0, 0.0),
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int,
                  cache_read_tokens: int, cache_write_tokens: int = 0) -> float:
    price = PRICING.get(model, (0.0, 0.0, 0.0, 0.0))
    inp_price, out_price, cr_price, cw_price = price
    return (
        input_tokens / 1_000_000 * inp_price
        + output_tokens / 1_000_000 * out_price
        + cache_read_tokens / 1_000_000 * cr_price
        + cache_write_tokens / 1_000_000 * cw_price
    )
