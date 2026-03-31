"""
Shared Gemini API helper.
Uses the free REST endpoint — no SDK needed.
Free tier: 1,500 req/day, 15 req/min (gemini-1.5-flash)
"""

import os
import json
import time
import logging
import requests
from typing import Any, Optional

logger = logging.getLogger(__name__)

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-1.5-flash-latest:generateContent"
)


def call_gemini(
    prompt: str,
    *,
    temperature: float = 0.2,
    max_tokens: int = 2048,
    retries: int = 3,
    retry_delay: float = 20.0,
) -> Optional[str]:
    """
    Call Gemini and return the text response.
    Returns None on unrecoverable failure.
    Automatically retries on 429 (rate limit).
    """
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        logger.error("GEMINI_API_KEY not set — skipping Gemini call")
        return None

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        },
    }

    for attempt in range(1, retries + 1):
        try:
            resp = requests.post(
                GEMINI_URL,
                params={"key": api_key},
                json=payload,
                timeout=30,
            )

            if resp.status_code == 429:
                wait = retry_delay * attempt
                logger.warning(f"Gemini rate limit — waiting {wait}s (attempt {attempt}/{retries})")
                time.sleep(wait)
                continue

            resp.raise_for_status()
            data = resp.json()
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "")

            logger.warning(f"Gemini returned no candidates: {data}")
            return None

        except requests.exceptions.RequestException as e:
            logger.warning(f"Gemini request error (attempt {attempt}): {e}")
            if attempt < retries:
                time.sleep(retry_delay)

    logger.error("Gemini failed after all retries")
    return None


def call_gemini_json(
    prompt: str,
    *,
    temperature: float = 0.1,
    max_tokens: int = 2048,
) -> Optional[Any]:
    """
    Like call_gemini but parses the response as JSON.
    Strips markdown code fences if present.
    """
    raw = call_gemini(prompt, temperature=temperature, max_tokens=max_tokens)
    if raw is None:
        return None

    # Strip ```json ... ``` fences if present
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error from Gemini: {e}\nRaw: {text[:300]}")
        return None
