import re
from typing import Any


_PII_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    (
        "SSN",
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        "[SSN-REDACTED]",
    ),
    (
        "CREDIT_CARD",
        re.compile(
            r"\b(?:\d[ -]*?){13,16}\b"
        ),
        "[CC-REDACTED]",
    ),
    (
        "AWS_KEY",
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        "[AWS-KEY-REDACTED]",
    ),
    (
        "API_KEY",
        re.compile(r"\b(?:sk-|key-)[A-Za-z0-9_\-]{20,}\b"),
        "[API-KEY-REDACTED]",
    ),
    (
        "EMAIL",
        re.compile(
            r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Z|a-z]{2,}\b"
        ),
        "[EMAIL-REDACTED]",
    ),
    (
        "PHONE",
        re.compile(
            r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b"
        ),
        "[PHONE-REDACTED]",
    ),
]


def sanitize(text: str) -> tuple[str, list[dict[str, Any]]]:
    """Sanitize PII from text before sending to an LLM.

    Returns:
        A tuple of (sanitized_text, redactions) where redactions is a list of
        dicts with keys: type, original, replacement, start, end.
    """
    redactions: list[dict[str, Any]] = []
    sanitized = text

    # Process patterns in priority order.  Because replacements change offsets,
    # we rebuild the string for each pattern category and track cumulative
    # offset shifts per pass.
    for pii_type, pattern, replacement in _PII_PATTERNS:
        offset = 0
        new_sanitized = sanitized
        for match in pattern.finditer(sanitized):
            original = match.group()
            start = match.start() + offset
            end = match.end() + offset
            new_sanitized = new_sanitized[:start] + replacement + new_sanitized[end:]
            redactions.append(
                {
                    "type": pii_type,
                    "original": original,
                    "replacement": replacement,
                    "start": match.start(),
                    "end": match.end(),
                }
            )
            offset += len(replacement) - len(original)
        sanitized = new_sanitized

    return sanitized, redactions
