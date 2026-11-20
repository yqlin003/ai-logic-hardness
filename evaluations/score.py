"""Dependency-free scoring for the logic-hard benchmark."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable, Mapping


def normalize_answer(answer: object) -> str:
    text = str(answer).strip().lower()
    text = re.sub(r"^```(?:text|plain)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.rstrip(". ")


def score_answer(reference: object, response: object) -> dict[str, object]:
    expected = normalize_answer(reference)
    actual = normalize_answer(response)
    exact = actual == expected
    if exact:
        correctness = 1.0
    elif expected and (expected in actual or actual in expected):
        correctness = 0.5
    else:
        correctness = 0.0
    return {
        "exact": exact,
        "correctness": correctness,
        "reference": expected,
        "response": actual,
    }


def load_benchmark(path: str | Path) -> dict[str, object]:
    with Path(path).open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise ValueError("Benchmark must contain an 'items' list.")
    return data


def evaluate_items(
    items: Iterable[Mapping[str, object]],
    responses: Mapping[str, object],
) -> dict[str, object]:
    results = []
    for item in items:
        item_id = str(item["id"])
        result = score_answer(item["reference_answer"], responses.get(item_id, ""))
        results.append({"id": item_id, **result})

    if not results:
        return {"items": [], "correct": 0, "total": 0, "accuracy": 0.0}

    correct = sum(1 for result in results if result["exact"])
    total = len(results)
    return {
        "items": results,
        "correct": correct,
        "total": total,
        "accuracy": correct / total,
    }
