"""Security regex patterns for input/output guardrails."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class GuardrailPattern:
    """A regex pattern with metadata for guardrail checking."""

    name: str
    pattern: re.Pattern
    severity: str  # "block" or "warn"
    description: str
    applies_to: list[str] | None = None  # Tool names or None for all


# ── SQL Injection Patterns ──

SQL_DANGEROUS = [
    GuardrailPattern(
        name="sql_drop",
        pattern=re.compile(r"\b(DROP\s+(TABLE|DATABASE|INDEX|VIEW|SCHEMA))\b", re.IGNORECASE),
        severity="block",
        description="Dangerous SQL: DROP statement detected",
    ),
    GuardrailPattern(
        name="sql_truncate",
        pattern=re.compile(r"\bTRUNCATE\s+TABLE\b", re.IGNORECASE),
        severity="block",
        description="Dangerous SQL: TRUNCATE TABLE detected",
    ),
    GuardrailPattern(
        name="sql_alter",
        pattern=re.compile(r"\bALTER\s+(TABLE|DATABASE)\b", re.IGNORECASE),
        severity="block",
        description="Dangerous SQL: ALTER statement detected",
    ),
    GuardrailPattern(
        name="sql_delete_no_where",
        pattern=re.compile(r"\bDELETE\s+FROM\s+\w+\s*;?\s*$", re.IGNORECASE),
        severity="block",
        description="Dangerous SQL: DELETE without WHERE clause",
    ),
]

# ── Path Traversal Patterns ──

PATH_TRAVERSAL = [
    GuardrailPattern(
        name="path_traversal",
        pattern=re.compile(r"\.\./|\.\.\\", re.IGNORECASE),
        severity="block",
        description="Path traversal detected: directory traversal attempt",
    ),
    GuardrailPattern(
        name="etc_passwd",
        pattern=re.compile(r"/etc/(passwd|shadow|hosts)", re.IGNORECASE),
        severity="block",
        description="Path traversal detected: sensitive system file access",
    ),
]

# ── PII Detection Patterns ──

PII_PATTERNS = [
    GuardrailPattern(
        name="ssn",
        pattern=re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        severity="warn",
        description="Potential SSN detected in arguments",
    ),
    GuardrailPattern(
        name="credit_card",
        pattern=re.compile(r"\b(?:\d{4}[- ]?){3}\d{4}\b"),
        severity="warn",
        description="Potential credit card number detected",
    ),
]

# ── API Key / Secret Detection ──

API_KEY_PATTERNS = [
    GuardrailPattern(
        name="aws_key",
        pattern=re.compile(r"(?:AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}"),
        severity="warn",
        description="Potential AWS access key detected",
    ),
    GuardrailPattern(
        name="github_token",
        pattern=re.compile(r"gh[ps]_[A-Za-z0-9_]{36,}"),
        severity="warn",
        description="Potential GitHub token detected",
    ),
    GuardrailPattern(
        name="generic_secret",
        pattern=re.compile(
            r"(?i)(api[_-]?key|secret[_-]?key|access[_-]?token|password)\s*[:=]\s*['\"]?[A-Za-z0-9+/=_-]{20,}"
        ),
        severity="warn",
        description="Potential API key or secret in arguments",
    ),
]

# ── Prompt Injection Patterns ──

PROMPT_INJECTION = [
    GuardrailPattern(
        name="ignore_instructions",
        pattern=re.compile(
            r"(?i)(ignore\s+(all\s+)?previous\s+instructions|"
            r"disregard\s+(all\s+)?prior\s+(instructions|context)|"
            r"forget\s+(everything|all)\s+(above|before))",
        ),
        severity="block",
        description="Potential prompt injection detected",
    ),
    GuardrailPattern(
        name="system_prompt_extraction",
        pattern=re.compile(
            r"(?i)(reveal|show|print|output|display)\s+(your\s+)?(system\s+prompt|instructions|rules)",
        ),
        severity="warn",
        description="Potential system prompt extraction attempt",
    ),
]


def get_all_patterns() -> list[GuardrailPattern]:
    """Return all configured guardrail patterns."""
    return SQL_DANGEROUS + PATH_TRAVERSAL + PII_PATTERNS + API_KEY_PATTERNS + PROMPT_INJECTION
