"""
LLM Helper — Anthropic Claude API
──────────────────────────────────────────────────────────────
Replaces Gemini. Uses claude-haiku-4-5 (fast + cheap).
Free credits: $5 from console.anthropic.com — lasts ~3 months
at this usage level.

Set ANTHROPIC_API_KEY as a GitHub Secret.
──────────────────────────────────────────────────────────────
"""

import json
import os
import time
import logging
import urllib.request
import urllib.error
from typing import Any, Optional

logger = logging.getLogger(__name__)

API_URL = "https://api.anthropic.com/v1/messages"
MODEL   = "claude-haiku-4-5-20251001"   # Fast, cheap, reliable


def call_claude(
    prompt: str,
    *,
    temperature: float = 0.2,
    max_tokens:  int   = 2048,
    retries:     int   = 2,
    retry_delay: float = 10.0,
) -> Optional[str]:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not set")
        return None

    payload = json.dumps({
        "model":      MODEL,
        "max_tokens": max_tokens,
        "messages":   [{"role": "user", "content": prompt}],
    }).encode()

    headers = {
        "Content-Type":      "application/json",
        "x-api-key":         api_key,
        "anthropic-version": "2023-06-01",
    }

    for attempt in range(1, retries + 1):
        try:
            req  = urllib.request.Request(API_URL, data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
                return data["content"][0]["text"]

        except urllib.error.HTTPError as e:
            body = e.read().decode()
            if e.code == 429:
                wait = retry_delay * attempt
                logger.warning(f"Claude rate limit — waiting {wait}s (attempt {attempt}/{retries})")
                time.sleep(wait)
            else:
                logger.error(f"Claude API error {e.code}: {body[:200]}")
                return None
        except Exception as e:
            logger.warning(f"Claude request error (attempt {attempt}): {e}")
            if attempt < retries:
                time.sleep(retry_delay)

    logger.error("Claude failed after all retries")
    return None


def call_claude_json(prompt: str, **kwargs) -> Optional[Any]:
    """Call Claude and parse JSON response."""
    raw = call_claude(prompt, **kwargs)
    if raw is None:
        return None
    text = raw.strip()
    # Strip markdown fences if present
    if text.startswith("```"):
        lines = [l for l in text.split("\n") if not l.strip().startswith("```")]
        text  = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error: {e}\nRaw: {text[:300]}")
        return None
