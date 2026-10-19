"""Input/output sanitization engine for the gateway guardrails layer."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from agentgateway.config.settings import GuardrailsSettings
from agentgateway.guardrails.patterns import (
    API_KEY_PATTERNS,
    PATH_TRAVERSAL,
    PII_PATTERNS,
    PROMPT_INJECTION,
    SQL_DANGEROUS,
    GuardrailPattern,
)

logger = logging.getLogger(__name__)


@dataclass
class Violation:
    """A single guardrail violation."""

    pattern_name: str
    severity: str  # "block" or "warn"
    message: str
    field: str = ""


@dataclass
class SanitizationResult:
    """Result of a sanitization check."""

    passed: bool
    violations: list[Violation] = field(default_factory=list)

    @property
    def has_blocks(self) -> bool:
        return any(v.severity == "block" for v in self.violations)

    @property
    def has_warnings(self) -> bool:
        return any(v.severity == "warn" for v in self.violations)


class Sanitizer:
    """Scans tool call arguments and results for security violations."""

    def __init__(self, settings: GuardrailsSettings) -> None:
        self._settings = settings
        self._input_patterns = self._build_input_patterns()
        self._output_patterns = self._build_output_patterns()

    def _build_input_patterns(self) -> list[GuardrailPattern]:
        patterns: list[GuardrailPattern] = []
        if self._settings.block_sql_injection:
            patterns.extend(SQL_DANGEROUS)
        if self._settings.block_path_traversal:
            patterns.extend(PATH_TRAVERSAL)
        if self._settings.detect_pii:
            patterns.extend(PII_PATTERNS)
        if self._settings.detect_prompt_injection:
            patterns.extend(PROMPT_INJECTION)
        return patterns

    def _build_output_patterns(self) -> list[GuardrailPattern]:
        """Output scanning focuses on secrets and PII leakage."""
        patterns: list[GuardrailPattern] = []
        patterns.extend(API_KEY_PATTERNS)
        if self._settings.detect_pii:
            patterns.extend(PII_PATTERNS)
        return patterns

    def _scan_value(
        self,
        value: str,
        patterns: list[GuardrailPattern],
        field_name: str = "",
    ) -> list[Violation]:
        """Scan a string value against a list of patterns."""
        violations = []
        for p in patterns:
            if p.pattern.search(value):
                violations.append(
                    Violation(
                        pattern_name=p.name,
                        severity=p.severity,
                        message=p.description,
                        field=field_name,
                    )
                )
        return violations

    def _scan_dict(
        self, data: dict[str, Any], patterns: list[GuardrailPattern]
    ) -> list[Violation]:
        """Recursively scan all string values in a dict."""
        violations = []
        for key, value in data.items():
            if isinstance(value, str):
                violations.extend(self._scan_value(value, patterns, field_name=key))
            elif isinstance(value, dict):
                violations.extend(self._scan_dict(value, patterns))
            elif isinstance(value, list):
                for i, item in enumerate(value):
                    if isinstance(item, str):
                        violations.extend(
                            self._scan_value(item, patterns, field_name=f"{key}[{i}]")
                        )
                    elif isinstance(item, dict):
                        violations.extend(self._scan_dict(item, patterns))
        return violations

    def check_input(self, tool_name: str, arguments: dict[str, Any]) -> SanitizationResult:
        """Scan tool call arguments for security violations."""
        if not self._settings.enabled:
            return SanitizationResult(passed=True)

        violations = self._scan_dict(arguments, self._input_patterns)

        for v in violations:
            log_fn = logger.warning if v.severity == "block" else logger.info
            log_fn("Guardrail [%s] %s on %s.%s", v.severity, v.message, tool_name, v.field)

        return SanitizationResult(
            passed=not any(v.severity == "block" for v in violations),
            violations=violations,
        )

    def check_output(self, tool_name: str, result: Any) -> SanitizationResult:
        """Scan tool call output for leaked secrets or PII."""
        if not self._settings.enabled:
            return SanitizationResult(passed=True)

        text_to_scan = ""
        # Extract text from CallToolResult content blocks
        if hasattr(result, "content"):
            for block in result.content:
                if hasattr(block, "text"):
                    text_to_scan += block.text + "\n"

        if not text_to_scan:
            return SanitizationResult(passed=True)

        violations = self._scan_value(text_to_scan, self._output_patterns, field_name="output")

        for v in violations:
            logger.warning("Output guardrail [%s] %s on %s", v.severity, v.message, tool_name)

        return SanitizationResult(
            passed=not any(v.severity == "block" for v in violations),
            violations=violations,
        )
