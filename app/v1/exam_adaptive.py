"""Engine CAT/IRT para provas adaptativas (SPEC-EXAM-002)."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AdaptiveAssessmentConfig:
    initial_theta: float = 0.0
    min_error: float = 0.2
    min_items: int = 10
    max_items: int = 15


@dataclass(frozen=True)
class AdaptiveItem:
    question_id: str
    order_index: int
    discrimination: float
    difficulty: float
    guessing: float = 0.0


@dataclass(frozen=True)
class AdaptiveResponse:
    question_id: str
    is_correct: bool


def is_adaptive_assessment_type(assessment_type: str | None, explicit: str | None = None) -> bool:
    if explicit and str(explicit).strip().lower() == "adaptive":
        return True
    return str(assessment_type or "").strip().lower() == "adaptive"


def parse_adaptive_config(row: dict[str, Any] | None) -> AdaptiveAssessmentConfig:
    if not row:
        return AdaptiveAssessmentConfig()
    return AdaptiveAssessmentConfig(
        initial_theta=float(row.get("est_theta") or 0.0),
        min_error=float(row.get("min_error") if row.get("min_error") is not None else 0.2),
        min_items=int(row.get("min_items") or 10),
        max_items=int(row.get("max_items") or 15),
    )


def parse_item_parameters(raw: Any, *, order_index: int = 0) -> tuple[float, float, float]:
    """Extrai (a, b, c) de question_item.parameters (JSON object ou string)."""
    data: dict[str, Any] = {}
    if isinstance(raw, dict):
        data = raw
    elif isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                data = parsed
        except json.JSONDecodeError:
            data = {}

    a = float(data.get("a") or data.get("discrimination") or 1.0)
    b = float(data.get("b") or data.get("difficulty") or 0.0)
    c = float(data.get("c") or data.get("guessing") or 0.0)
    c = max(0.0, min(c, 0.35))
    if a <= 0:
        a = 1.0
    return a, b, c


def probability_3pl(theta: float, discrimination: float, difficulty: float, guessing: float) -> float:
    z = discrimination * (theta - difficulty)
    z = max(-20.0, min(20.0, z))
    return guessing + (1.0 - guessing) / (1.0 + math.exp(-z))


def fisher_information(theta: float, item: AdaptiveItem) -> float:
    p = probability_3pl(theta, item.discrimination, item.difficulty, item.guessing)
    q = 1.0 - p
    if p <= 0.0 or q <= 0.0:
        return 0.0
    a, c = item.discrimination, item.guessing
    dp = (1.0 - c) * a * p * q / (1.0 - c * q) if (1.0 - c * q) != 0 else 0.0
    return (dp * dp) / (p * q)


def estimate_theta(
    responses: list[AdaptiveResponse],
    items_by_id: dict[str, AdaptiveItem],
    *,
    initial_theta: float,
) -> tuple[float, float]:
    """MLE via Newton-Raphson; retorna (theta, standard_error)."""
    if not responses:
        return initial_theta, 1.0

    theta = initial_theta
    for _ in range(30):
        first = 0.0
        second = 0.0
        for resp in responses:
            item = items_by_id.get(resp.question_id)
            if not item:
                continue
            a, b, c = item.discrimination, item.difficulty, item.guessing
            p = probability_3pl(theta, a, b, c)
            q = 1.0 - p
            if p <= 0.0 or q <= 0.0:
                continue
            u = 1.0 if resp.is_correct else 0.0
            dp = (1.0 - c) * a * p * q / (1.0 - c * q) if (1.0 - c * q) != 0 else 0.0
            d2p = (1.0 - c) * (a ** 2) * p * q * ((1.0 - c) * q - p) / ((1.0 - c * q) ** 2)
            first += ((u - p) / (p * q)) * dp if p * q > 0 else 0.0
            second += d2p + ((u - p) / (p * q)) * (dp ** 2) if p * q > 0 else 0.0
        if abs(second) < 1e-9:
            break
        step = first / second
        step = max(-1.0, min(1.0, step))
        theta -= step
        theta = max(-4.0, min(4.0, theta))
        if abs(step) < 1e-4:
            break

    info_sum = 0.0
    for resp in responses:
        item = items_by_id.get(resp.question_id)
        if item:
            info_sum += fisher_information(theta, item)
    se = 1.0 / math.sqrt(info_sum) if info_sum > 0 else 1.0
    return theta, se


def should_stop_exam(
    answered_count: int,
    standard_error: float,
    config: AdaptiveAssessmentConfig,
) -> bool:
    if answered_count >= config.max_items:
        return True
    return answered_count >= config.min_items and standard_error <= config.min_error


def select_next_item(
    theta: float,
    items: list[AdaptiveItem],
    answered_ids: set[str],
) -> AdaptiveItem | None:
    candidates = [it for it in items if it.question_id not in answered_ids]
    if not candidates:
        return None
    return max(candidates, key=lambda it: fisher_information(theta, it))


def adaptive_progress_block(
    *,
    answered_count: int,
    config: AdaptiveAssessmentConfig,
    last_answered_order: int | None,
) -> dict[str, Any]:
    remaining = max(0, config.max_items - answered_count)
    return {
        "total_questions": config.max_items,
        "answered_count": answered_count,
        "remaining_count": remaining,
        "last_answered_order": last_answered_order,
        "engine": "adaptive",
        "min_items": config.min_items,
        "max_items": config.max_items,
    }
