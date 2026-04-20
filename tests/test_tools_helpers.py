from __future__ import annotations

import asyncio

import pytest

from wordstat_mcp.tools import (
    _fetch_many,
    _clean_phrases,
    _validate_dynamics_phrases,
    paginate,
    split_phrases,
)
from wordstat_mcp.operators import (
    WordstatPhraseBuilder,
    build_wordstat_phrase_payload,
    validate_dynamics_phrase,
)


def test_clean_phrases_trims_values() -> None:
    assert _clean_phrases(["  python  ", "asyncio"]) == ["python", "asyncio"]


@pytest.mark.parametrize(
    "phrases",
    [
        [],
        ["   "],
        ["x" * 401],
    ],
)
def test_clean_phrases_skips_invalid_values(phrases: list[str]) -> None:
    assert _clean_phrases(phrases) == []


def test_validate_dynamics_phrase_allows_plus_operator() -> None:
    validate_dynamics_phrase("работа +из дома")


@pytest.mark.parametrize(
    "phrase",
    [
        '"купить авто"',
        "купить !собаку",
        "билеты [из москвы в париж]",
        "заказать (суши|пиццу)",
    ],
)
def test_validate_dynamics_phrase_rejects_unsupported_operators(
    phrase: str,
) -> None:
    with pytest.raises(ValueError, match="getDynamics supports only"):
        validate_dynamics_phrase(phrase)


def test_validate_dynamics_phrases_checks_each_phrase() -> None:
    with pytest.raises(ValueError, match="unsupported operator"):
        _validate_dynamics_phrases(["работа +из дома", '"купить авто"'])


def test_build_wordstat_phrase_applies_exact_and_stop_word_rules() -> None:
    result = build_wordstat_phrase_payload(
        WordstatPhraseBuilder(
            natural_query="Покажи топ по точной фразе работа из дома",
            target_method="getTop",
            base_phrase="работа из дома",
            exact_word_count=True,
            required_stop_words=["из"],
        )
    )

    assert result["phrase"] == '"работа +из дома"'
    assert result["applied_operators"] == ['" "', "+"]
    assert result["warnings"] == []


def test_build_wordstat_phrase_applies_order_and_alternatives() -> None:
    result = build_wordstat_phrase_payload(
        WordstatPhraseBuilder(
            natural_query="Сравни регионы для ремонта ноутбука или компьютера",
            target_method="getRegionsDistribution",
            base_phrase="ремонт",
            alternatives=["ноутбука", "компьютера"],
            fixed_word_order=True,
        )
    )

    assert result["phrase"] == "[ремонт (ноутбука|компьютера)]"
    assert result["applied_operators"] == ["()", "[]", "|"]


def test_build_wordstat_phrase_strips_unsupported_dynamics_operators() -> None:
    result = build_wordstat_phrase_payload(
        WordstatPhraseBuilder(
            natural_query="Покажи динамику точной фразы работа из дома",
            target_method="getDynamics",
            base_phrase='"работа из дома"',
            exact_word_count=True,
            required_stop_words=["из"],
        )
    )

    assert result["phrase"] == "работа +из дома"
    assert result["applied_operators"] == ["+"]
    assert result["warnings"]


@pytest.mark.parametrize(
    "builder_kwargs",
    [
        {"base_phrase": "заказать (суши|пиццу)"},
        {"base_phrase": "заказать еду", "alternatives": ["суши", "пиццу"]},
    ],
)
def test_build_wordstat_phrase_rejects_dynamics_alternatives(
    builder_kwargs: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="cannot represent Wordstat alternatives"):
        build_wordstat_phrase_payload(
            WordstatPhraseBuilder(
                natural_query="Покажи динамику для суши или пиццы",
                target_method="getDynamics",
                **builder_kwargs,
            )
        )


def test_build_wordstat_phrase_marks_repeated_required_stop_words() -> None:
    result = build_wordstat_phrase_payload(
        WordstatPhraseBuilder(
            natural_query="Сравни маршрут",
            target_method="getTop",
            base_phrase="билеты из Москвы в Париж из Самары",
            required_stop_words=["из", "в"],
        )
    )

    assert result["phrase"] == "билеты +из Москвы +в Париж +из Самары"
    assert result["applied_operators"] == ["+"]


def test_split_phrases_creates_expected_chunks() -> None:
    phrases = [f"q{i}" for i in range(205)]
    chunks = split_phrases(phrases, chunk_size=100)

    assert [len(chunk) for chunk in chunks] == [100, 100, 5]


def test_split_phrases_rejects_non_positive_chunk_size() -> None:
    with pytest.raises(ValueError, match="chunk_size must be > 0"):
        split_phrases(["python"], chunk_size=0)


def test_paginate_includes_navigation_flags() -> None:
    data = list(range(10))

    page = paginate(data, page=2, page_size=3)

    assert page == {
        "page": 2,
        "pageSize": 3,
        "total": 10,
        "totalPages": 4,
        "hasNextPage": True,
        "hasPreviousPage": True,
        "items": [3, 4, 5],
    }


def test_paginate_handles_empty_collection() -> None:
    assert paginate([], page=1, page_size=5) == {
        "page": 1,
        "pageSize": 5,
        "total": 0,
        "totalPages": 0,
        "hasNextPage": False,
        "hasPreviousPage": False,
        "items": [],
    }


@pytest.mark.anyio
async def test_fetch_many_respects_pagination_and_worker_output() -> None:
    phrases = ["python", "aiohttp", "mcp"]
    in_flight = 0
    max_in_flight = 0

    async def worker(phrase: str) -> dict[str, str]:
        nonlocal in_flight, max_in_flight
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        await asyncio.sleep(0)
        in_flight -= 1
        return {"phrase": phrase}

    result = await _fetch_many(
        phrases,
        worker,
        page=1,
        page_size=2,
        max_concurrency=2,
    )

    assert result["items"] == [{"phrase": "python"}, {"phrase": "aiohttp"}]
    assert result["total"] == 3
    assert max_in_flight <= 2
