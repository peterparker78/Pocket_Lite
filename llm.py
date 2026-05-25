"""
LLM helpers for Pocket Lite.

Uses Claude Haiku to generate higher-quality article summaries and
suggest tags. Reads ANTHROPIC_API_KEY from the environment (a .env file
in the project root is also loaded). All functions return None on any
failure so callers can fall back to the heuristic summary.
"""
import json
import logging
import os
import re

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None

log = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"
MAX_CONTENT_CHARS = 60_000  # ~15k tokens; plenty for almost any article

_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client
    if Anthropic is None:
        return None
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    _client = Anthropic()
    return _client


def _strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html or "")
    return re.sub(r"\s+", " ", text).strip()


def summarize_and_tag(title: str, content_html: str) -> dict | None:
    """
    Generate a 2-3 sentence summary and 2-5 topical tags via Claude Haiku.

    Returns {"summary": str, "tags": [str]} on success, or None if the
    API key is missing, the SDK isn't installed, or the call fails.
    Tags are lowercase, single-word or hyphenated, no leading '#'.
    """
    client = _get_client()
    if client is None:
        return None

    text = _strip_html(content_html)
    if not text:
        return None
    if len(text) > MAX_CONTENT_CHARS:
        text = text[:MAX_CONTENT_CHARS]

    prompt = (
        "You will be given an article. Produce a JSON object with exactly two "
        "keys:\n"
        '  - "summary": 2-3 sentences capturing the article\'s main argument or '
        "findings. Plain prose, no bullets, no preamble like \"This article\".\n"
        '  - "tags": an array of 2-5 short topical tags (lowercase, single word '
        "or hyphenated, no '#', no spaces inside a tag). Tags should be "
        "specific enough to be useful for filtering a personal reading "
        "library.\n\n"
        "Return ONLY the JSON object, no markdown fence, no commentary.\n\n"
        f"Title: {title or '(no title)'}\n\n"
        f"Article:\n{text}"
    )

    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
    except Exception as e:
        log.warning("LLM call failed: %s", e)
        return None

    # Strip accidental code fences
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("LLM returned non-JSON: %s", raw[:200])
        return None

    summary = (data.get("summary") or "").strip()
    tags = data.get("tags") or []
    if not isinstance(tags, list):
        tags = []
    clean_tags = []
    for t in tags:
        if not isinstance(t, str):
            continue
        t = t.strip().lower().lstrip("#")
        t = re.sub(r"\s+", "-", t)
        t = re.sub(r"[^a-z0-9\-]", "", t)
        if t and t not in clean_tags:
            clean_tags.append(t)

    if not summary:
        return None
    return {"summary": summary, "tags": clean_tags[:5]}
