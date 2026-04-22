"""Wordstat phrase operator helpers."""

from __future__ import annotations

import re
from importlib.resources import files
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

WordstatSearchMethod = Literal["getTop", "getDynamics", "getRegionsDistribution"]

OPERATORS_GUIDE_RESOURCE_URI = "wordstat://operators/agent-guide"
OPERATORS_PROMPT_NAME = "wordstat_phrase_builder"
OPERATORS_GUIDE_RESOURCE_PACKAGE = "wordstat_mcp.resources"
OPERATORS_GUIDE_RESOURCE_NAME = "WORDSTAT_OPERATORS_AGENT_GUIDE_RU.md"

DYNAMICS_UNSUPPORTED_OPERATORS = frozenset({"!", '"', "[", "]", "(", ")", "|"})
DYNAMICS_UNSUPPORTED_OPERATOR_PATTERN = re.compile(r'[!"\[\]()|]')
DYNAMICS_ALTERNATIVE_OPERATOR_PATTERN = re.compile(r"[()|]")
DYNAMICS_STRIPPABLE_UNSUPPORTED_OPERATOR_PATTERN = re.compile(r'[!"\[\]]')
WARNING_BASE_PHRASE_INFERRED = "BASE_PHRASE_INFERRED"
WARNING_DYNAMICS_OPERATOR_LIMIT = "DYNAMICS_OPERATOR_LIMIT"
WARNING_DYNAMICS_OPERATORS_STRIPPED = "DYNAMICS_OPERATORS_STRIPPED"

RUSSIAN_STOP_WORDS = frozenset(
    {
        "без",
        "в",
        "для",
        "до",
        "за",
        "из",
        "к",
        "на",
        "над",
        "о",
        "об",
        "от",
        "по",
        "под",
        "при",
        "про",
        "с",
        "со",
        "у",
        "через",
    }
)


def load_wordstat_operators_agent_guide() -> str:
    """Load the packaged Wordstat operator guide used by the MCP resource."""

    return (
        files(OPERATORS_GUIDE_RESOURCE_PACKAGE)
        .joinpath(OPERATORS_GUIDE_RESOURCE_NAME)
        .read_text(encoding="utf-8")
    )


WORDSTAT_OPERATORS_AGENT_GUIDE = load_wordstat_operators_agent_guide()


class WordstatPhraseBuilder(BaseModel):
    """Natural-language request and optional intent hints for phrase building."""

    model_config = ConfigDict(str_strip_whitespace=True)

    natural_query: str = Field(min_length=1, max_length=1000)
    target_method: WordstatSearchMethod
    base_phrase: str | None = Field(default=None, min_length=1, max_length=400)
    exact_word_count: bool = False
    fixed_word_order: bool = False
    alternatives: list[str] = Field(default_factory=list, max_length=20)
    fixed_forms: list[str] = Field(default_factory=list, max_length=50)
    required_stop_words: list[str] = Field(default_factory=list, max_length=50)


def validate_dynamics_phrase(phrase: str) -> None:
    """Reject operators that Wordstat dynamics does not support."""

    if unsupported := sorted(
        set(DYNAMICS_UNSUPPORTED_OPERATOR_PATTERN.findall(phrase))
    ):
        raise ValueError(
            "getDynamics supports only the `+` Wordstat operator. "
            f"Remove unsupported operator(s): {', '.join(f'`{op}`' for op in unsupported)}."
        )


def _normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _strip_surrounding_quotes(value: str) -> str:
    value = value.strip()
    quote_pairs = [('"', '"'), ("'", "'"), ("`", "`"), ("«", "»"), ("“", "”")]
    for left, right in quote_pairs:
        if value.startswith(left) and value.endswith(right):
            return value[len(left) : -len(right)].strip()
    return value


def _extract_phrase_candidate(natural_query: str) -> tuple[str, bool]:
    """Best-effort phrase extraction for clients that do not pass base_phrase."""

    query = _normalize_space(natural_query)
    if quoted := re.search(r"[\"'`«“](.+?)[\"'`»”]", query):
        return _normalize_space(quoted.group(1)), False

    candidate = query
    prefixes = [
        r"^(?:найди|покажи|посмотри|проверь|сравни|нужна|нужен)\s+",
        r"^(?:топ|динамику|частотность|статистику|спрос)\s+",
        r"^(?:топ\s+запросов|запросы)\s+",
        r"^(?:по|для|на)\s+",
        r"^(?:точной|точная|фразе|фразы|форме|формы)\s+",
    ]

    changed = True
    while changed:
        changed = False
        for prefix in prefixes:
            new_candidate = re.sub(prefix, "", candidate, flags=re.IGNORECASE).strip()
            if new_candidate != candidate:
                candidate = new_candidate
                changed = True

    candidate = re.split(
        r"\s*(?:,|;)\s*(?:порядок|без|только|именно)\b",
        candidate,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    return _normalize_space(candidate), True


def _add_plus_to_stop_words(
    phrase: str, stop_words: list[str]
) -> tuple[str, list[str]]:
    applied: list[str] = []
    result = phrase
    for stop_word in stop_words:
        word = _strip_surrounding_quotes(stop_word).lower()
        if not word:
            continue
        pattern = re.compile(rf"(?<![\w+]){re.escape(word)}(?!\w)", re.IGNORECASE)
        result, count = pattern.subn(lambda match: f"+{match.group(0)}", result)
        if count:
            applied.append("+")
    return result, applied


def _add_fixed_forms(phrase: str, fixed_forms: list[str]) -> tuple[str, list[str]]:
    applied: list[str] = []
    result = phrase
    for fixed_form in fixed_forms:
        word = _strip_surrounding_quotes(fixed_form).lower()
        if not word:
            continue
        pattern = re.compile(rf"(?<![\w!]){re.escape(word)}(?!\w)", re.IGNORECASE)
        if pattern.search(result):
            result = pattern.sub(f"!{word}", result, count=1)
        else:
            result = f"{result} !{word}".strip()
        applied.append("!")
    return result, applied


def _strip_dynamics_unsupported_operators(phrase: str) -> str:
    stripped = phrase
    for operator in DYNAMICS_UNSUPPORTED_OPERATORS - {"|"}:
        stripped = stripped.replace(operator, " ")
    stripped = stripped.replace("|", " ")
    return _normalize_space(stripped)


def _default_stop_words(phrase: str) -> list[str]:
    words = {word.lower() for word in re.findall(r"[A-Za-zА-Яа-яЁё]+", phrase)}
    return [word for word in words if word in RUSSIAN_STOP_WORDS]


def build_wordstat_phrase_payload(request: WordstatPhraseBuilder) -> dict[str, Any]:
    """Build or validate a Wordstat phrase from a request plus optional hints."""

    warnings: list[str] = []
    applied_operators: list[str] = []
    inferred = False

    if request.base_phrase:
        phrase = _normalize_space(request.base_phrase)
    else:
        phrase, inferred = _extract_phrase_candidate(request.natural_query)
        warnings.append(WARNING_BASE_PHRASE_INFERRED)

    if not phrase:
        raise ValueError("Could not build a non-empty Wordstat phrase.")

    exact_word_count = request.exact_word_count
    fixed_word_order = request.fixed_word_order
    fixed_forms = list(request.fixed_forms)
    alternatives = [_strip_surrounding_quotes(item) for item in request.alternatives]
    stop_words = list(request.required_stop_words) or _default_stop_words(phrase)

    if request.target_method == "getDynamics":
        if alternatives or DYNAMICS_ALTERNATIVE_OPERATOR_PATTERN.search(phrase):
            raise ValueError(
                "getDynamics cannot represent Wordstat alternatives or grouped "
                "operators. Pass separate phrases or use getTop/getRegionsDistribution."
            )
        if exact_word_count or fixed_word_order or fixed_forms:
            warnings.append(WARNING_DYNAMICS_OPERATOR_LIMIT)
        if DYNAMICS_STRIPPABLE_UNSUPPORTED_OPERATOR_PATTERN.search(phrase):
            warnings.append(WARNING_DYNAMICS_OPERATORS_STRIPPED)
            phrase = _strip_dynamics_unsupported_operators(phrase)
        phrase, plus_ops = _add_plus_to_stop_words(phrase, stop_words)
        applied_operators.extend(plus_ops)
        validate_dynamics_phrase(phrase)
        return {
            "phrase": phrase,
            "target_method": request.target_method,
            "applied_operators": sorted(set(applied_operators)),
            "warnings": warnings,
            "needs_review": inferred,
            "resource_uri": OPERATORS_GUIDE_RESOURCE_URI,
            "prompt_name": OPERATORS_PROMPT_NAME,
        }

    phrase, plus_ops = _add_plus_to_stop_words(phrase, stop_words)
    applied_operators.extend(plus_ops)

    if fixed_forms:
        phrase, fixed_ops = _add_fixed_forms(phrase, fixed_forms)
        applied_operators.extend(fixed_ops)

    alternatives = [item for item in alternatives if item]
    if alternatives:
        group = f"({'|'.join(alternatives)})"
        if "{alternatives}" in phrase:
            phrase = phrase.replace("{alternatives}", group)
        else:
            phrase = f"{phrase} {group}".strip()
        applied_operators.extend(["()", "|"])

    if fixed_word_order and not (phrase.startswith("[") and phrase.endswith("]")):
        phrase = f"[{phrase}]"
        applied_operators.append("[]")

    if exact_word_count and not (phrase.startswith('"') and phrase.endswith('"')):
        phrase = f'"{phrase}"'
        applied_operators.append('" "')

    if len(phrase) > 400:
        raise ValueError("Built Wordstat phrase exceeds 400 characters.")

    return {
        "phrase": phrase,
        "target_method": request.target_method,
        "applied_operators": sorted(set(applied_operators)),
        "warnings": warnings,
        "needs_review": inferred,
        "resource_uri": OPERATORS_GUIDE_RESOURCE_URI,
        "prompt_name": OPERATORS_PROMPT_NAME,
    }


def render_wordstat_phrase_builder_prompt(
    user_request: str,
    target_method: str,
) -> str:
    """Render the prompt exposed through MCP."""

    return f"""You are preparing a Yandex Wordstat API `phrase`.

Follow these instructions exactly:

1. Use Russian search phrases in examples and final `phrase` values.
2. Apply the Wordstat operators guide from `{OPERATORS_GUIDE_RESOURCE_URI}`.
3. Prefer calling `build_wordstat_phrase` with an explicit `base_phrase` and
   intent hints before calling `getTop`, `getDynamics`, or
   `getRegionsDistribution`.
4. For `getDynamics`, never use operators other than `+`. Keep operator
   compatibility details internal unless the user asks about query syntax,
   exactness, or why the phrase changed.
5. Do not invent region IDs. Use `find_regions` when a user gives a city or
   region name. Use `getRegionsTree` only for bulk/debug region index lookup.

Target method: `{target_method}`
User request: {user_request}

Return a short plan and the final `phrase`. Include warning codes only when the
result needs user review.
"""
