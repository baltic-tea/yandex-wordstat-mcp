from __future__ import annotations

import asyncio
import json
import logging
import math
import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Awaitable, Callable

from pydantic import TypeAdapter, ValidationError

from wordstat_mcp.api_settings import WordstatSettings
from wordstat_mcp.exceptions import WordstatError
from wordstat_mcp.models import PhraseModel
from wordstat_mcp.operators import validate_dynamics_phrase

logger = logging.getLogger("wordstat_mcp")

MAX_PHRASES_PER_CALL = 100
DATETIME_ADAPTER = TypeAdapter(datetime)
REGIONS_TREE_CACHE_PATH = Path(".saved") / "regions_tree.json"
REGION_NAME_KEYS = ("name", "label", "title")
REGION_WHITESPACE_PATTERN = re.compile(r"\s+")


@lru_cache(maxsize=1)
def wordstat_settings() -> WordstatSettings:
    return WordstatSettings()  # type: ignore[call-arg]


def tool_annotations(
    title: str,
    *,
    read_only: bool = True,
    idempotent: bool = True,
    open_world: bool = True,
) -> dict[str, Any]:
    """Build common read-only MCP tool annotations."""

    return {
        "title": title,
        "readOnlyHint": read_only,
        "destructiveHint": False,
        "idempotentHint": idempotent,
        "openWorldHint": open_world,
    }


def _validation_reason(exc: ValidationError) -> str:
    errors = exc.errors()
    if errors:
        return str(errors[0].get("msg", exc))
    return str(exc)


def clean_phrases_with_warnings(phrases: list[str]) -> tuple[list[str], list[str]]:
    """Validate and normalize phrase list, returning skipped-input warnings."""
    cleaned = []
    warnings = []
    for phrase in phrases:
        try:
            validated_phrase = PhraseModel(phrase=phrase).phrase
            cleaned.append(validated_phrase)
        except ValidationError as e:
            warnings.append(
                f"Skipped invalid phrase {phrase!r}: {_validation_reason(e)}."
            )
            logger.info(f"Skipping invalid phrase: {phrase}. Error: {e}")
    return cleaned, warnings


def clean_phrases(phrases: list[str]) -> list[str]:
    """Validate and normalize phrase list."""
    cleaned, _ = clean_phrases_with_warnings(phrases)
    return cleaned


def clean_tool_phrases(phrases: list[str]) -> tuple[list[str], list[str]]:
    """Validate tool phrase input and fail when no valid phrase remains."""
    cleaned, warnings = clean_phrases_with_warnings(phrases)
    if cleaned:
        return cleaned, warnings
    if warnings:
        raise ValueError("No valid phrases provided. " + " ".join(warnings))
    raise ValueError("At least one phrase is required.")


def validate_dynamics_phrases(phrases: list[str]) -> None:
    """Validate Wordstat operator usage for the dynamics API."""

    for phrase in phrases:
        validate_dynamics_phrase(phrase)


def normalize_region_name(value: str) -> str:
    """Normalize user and API region names for lookup keys."""

    return REGION_WHITESPACE_PATTERN.sub(" ", value).strip().casefold()


def region_lookup_keys(value: str) -> list[str]:
    """Return equivalent exact lookup keys for a region name."""

    normalized = normalize_region_name(value)
    if not normalized:
        return []

    keys = [normalized]
    yo_normalized = normalized.replace("ё", "е")
    if yo_normalized != normalized:
        keys.append(yo_normalized)
    return keys


def load_regions_tree_cache(
    cache_path: Path = REGIONS_TREE_CACHE_PATH,
) -> dict[str, Any] | None:
    """Load cached region index from disk when present."""
    if not cache_path.exists():
        return None

    try:
        with cache_path.open("r", encoding="utf-8") as cache_file:
            payload = json.load(cache_file)
    except (OSError, json.JSONDecodeError) as exc:
        raise WordstatError(
            f"Invalid regions tree cache at {cache_path}: {exc}"
        ) from exc

    if not isinstance(payload, dict):
        raise WordstatError(
            f"Invalid regions tree cache at {cache_path}: expected object"
        )

    return normalize_regions_lookup(payload)


def build_regions_lookup(payload: dict[str, Any]) -> dict[str, Any]:
    """Build region lookup indexes from an API tree payload."""

    index: dict[str, Any] = {"by_name": {}, "by_id": {}}

    def node_name(node: dict[str, Any]) -> str | None:
        return next(
            (
                node[key].strip()
                for key in REGION_NAME_KEYS
                if isinstance(node.get(key), str) and node[key].strip()
            ),
            None,
        )

    def visit(node: Any, path: list[str]) -> None:
        if isinstance(node, list):
            for item in node:
                visit(item, path)
            return

        if not isinstance(node, dict):
            return

        region_id = node.get("id")
        region_name = node_name(node)
        child_path = path
        if region_id is not None and region_name:
            region_id_str = str(region_id)
            child_path = [*path, region_name]
            for normalized_name in region_lookup_keys(region_name):
                region_ids = index["by_name"].setdefault(normalized_name, [])
                if region_id_str not in region_ids:
                    region_ids.append(region_id_str)
            index["by_id"][region_id_str] = {
                "name": region_name,
                "path": child_path,
            }

        for value in node.values():
            if isinstance(value, (dict, list)):
                visit(value, child_path)

    visit(payload, [])
    return index


def normalize_regions_lookup(payload: dict[str, Any]) -> dict[str, Any]:
    """Return payload as region index, accepting current, flat, or API tree shape."""
    if "by_name" in payload or "by_id" in payload:
        if not isinstance(payload.get("by_name"), dict) or not isinstance(
            payload.get("by_id"), dict
        ):
            raise WordstatError(
                "Invalid regions tree cache: by_name and by_id must be objects"
            )

        normalized_by_id: dict[str, dict[str, Any]] = {}
        for region_id, region in payload["by_id"].items():
            region_id = str(region_id)
            if not isinstance(region, dict):
                raise WordstatError(
                    "Invalid regions tree cache: by_id values must be objects"
                )
            region_name = region.get("name")
            region_path = region.get("path")
            if not isinstance(region_name, str) or not region_name.strip():
                raise WordstatError(
                    "Invalid regions tree cache: by_id entries require name"
                )
            if not isinstance(region_path, list) or not all(
                isinstance(part, str) for part in region_path
            ):
                raise WordstatError(
                    "Invalid regions tree cache: by_id entries require string path"
                )
            normalized_by_id[region_id] = {"name": region_name, "path": region_path}

        by_name: dict[str, list[str]] = {}
        for name, value in payload["by_name"].items():
            if not isinstance(name, str):
                raise WordstatError(
                    "Invalid regions tree cache: by_name keys must be strings"
                )
            if isinstance(value, list):
                if not all(
                    isinstance(region_id, str) and region_id.strip()
                    for region_id in value
                ):
                    raise WordstatError(
                        "Invalid regions tree cache: by_name values must be string lists"
                    )
                region_ids = value
            elif isinstance(value, str) and value.strip():
                region_ids = [str(value)]
            else:
                raise WordstatError(
                    "Invalid regions tree cache: by_name values must be string lists"
                )
            for normalized_name in region_lookup_keys(name):
                by_name.setdefault(normalized_name, [])
                for region_id in region_ids:
                    if region_id not in normalized_by_id:
                        raise WordstatError(
                            "Invalid regions tree cache: by_name references unknown id"
                        )
                    if region_id not in by_name[normalized_name]:
                        by_name[normalized_name].append(region_id)
        return {"by_name": by_name, "by_id": normalized_by_id}

    if all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in payload.items()
    ):
        flat_by_name: dict[str, list[str]] = {}
        for name, region_id in payload.items():
            for normalized_name in region_lookup_keys(name):
                flat_by_name.setdefault(normalized_name, [])
                if region_id not in flat_by_name[normalized_name]:
                    flat_by_name[normalized_name].append(region_id)
        return {
            "by_name": flat_by_name,
            "by_id": {
                region_id: {"name": name, "path": [name]}
                for name, region_id in payload.items()
            },
        }
    return build_regions_lookup(payload)


def find_region_matches(
    index: dict[str, Any],
    query: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Find exact and fuzzy region matches in a cached region index."""
    query_keys = region_lookup_keys(query)
    if not query_keys:
        return []
    primary_query = query_keys[0]

    by_name: dict[str, list[str] | str] = index.get("by_name", {})
    by_id: dict[str, dict[str, Any]] = index.get("by_id", {})
    matches: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_match(region_id: str, match_type: str) -> None:
        if region_id in seen or len(matches) >= limit:
            return
        region = by_id.get(region_id)
        if not region:
            return
        seen.add(region_id)
        matches.append(
            {
                "id": region_id,
                "name": region.get("name", ""),
                "path": region.get("path", []),
                "matchType": match_type,
            }
        )

    for query_key in query_keys:
        exact_ids = by_name.get(query_key)
        if exact_ids:
            region_ids = exact_ids if isinstance(exact_ids, list) else [exact_ids]
            for region_id in region_ids:
                add_match(region_id, "exact")

    ranked_candidates: list[tuple[int, int, str, str, str]] = []
    for region_id, region in by_id.items():
        region_name = str(region.get("name", ""))
        name_keys = region_lookup_keys(region_name)
        path_parts = region.get("path", [])
        if not isinstance(path_parts, list):
            path_parts = []
        path = " ".join(normalize_region_name(str(part)) for part in path_parts)

        if any(name_key.startswith(primary_query) for name_key in name_keys):
            ranked_candidates.append((1, len(path_parts), region_name, region_id, "prefix"))
        elif any(primary_query in name_key for name_key in name_keys):
            ranked_candidates.append(
                (2, len(path_parts), region_name, region_id, "contains_name")
            )
        elif primary_query in path:
            ranked_candidates.append(
                (3, len(path_parts), region_name, region_id, "contains_path")
            )

    for _, _, _, region_id, match_type in sorted(ranked_candidates):
        add_match(region_id, match_type)
        if len(matches) >= limit:
            break

    return matches


def save_regions_tree_cache(
    payload: dict[str, Any],
    cache_path: Path = REGIONS_TREE_CACHE_PATH,
) -> dict[str, Any]:
    """Persist compact region index cache and return it."""
    lookup = normalize_regions_lookup(payload)
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with cache_path.open("w", encoding="utf-8") as cache_file:
            json.dump(lookup, cache_file, ensure_ascii=False, indent=2, sort_keys=True)
            cache_file.write("\n")
    except OSError as exc:
        raise WordstatError(
            f"Could not write regions tree cache to {cache_path}: {exc}"
        ) from exc
    return lookup


def split_phrases(
    phrases: list[str], chunk_size: int = MAX_PHRASES_PER_CALL
) -> list[list[str]]:
    """Split phrase list into chunks of up to ``chunk_size``."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0.")
    return [phrases[i : i + chunk_size] for i in range(0, len(phrases), chunk_size)]


def paginate(items: list[Any], page: int = 1, page_size: int = 50) -> dict[str, Any]:
    """Paginate list-like data for MCP tool responses."""
    if page < 1:
        raise ValueError("page must be >= 1.")
    if page_size < 1:
        raise ValueError("page_size must be >= 1.")

    total = len(items)
    total_pages = math.ceil(total / page_size) if total else 0
    start = (page - 1) * page_size
    end = start + page_size

    return {
        "page": page,
        "pageSize": page_size,
        "total": total,
        "totalPages": total_pages,
        "hasNextPage": end < total,
        "hasPreviousPage": page > 1,
        "items": items[start:end],
    }


def parse_datetime(value: str | datetime) -> datetime:
    """Parse datetime-like tool input for typed request models."""

    if isinstance(value, datetime):
        return value
    return DATETIME_ADAPTER.validate_python(value)


async def fetch_many(
    phrases: list[str],
    worker: Callable[[str], Awaitable[dict[str, Any]]],
    *,
    page: int,
    page_size: int,
    max_concurrency: int,
) -> dict[str, Any]:
    """Fetch many phrase-level responses with bounded concurrency."""

    semaphore = asyncio.Semaphore(max_concurrency)
    indexed_results: list[dict[str, Any]] = []

    async def run_worker(phrase: str) -> dict[str, Any]:
        async with semaphore:
            return await worker(phrase)

    for chunk in split_phrases(phrases, MAX_PHRASES_PER_CALL):
        chunk_results = await asyncio.gather(*(run_worker(phrase) for phrase in chunk))
        indexed_results.extend(chunk_results)

    return paginate(indexed_results, page=page, page_size=page_size)
