"""Catálogo de níveis de dificuldade (código EN → rótulo PT-BR)."""

from __future__ import annotations

DIFFICULTY_LEVEL_OPTIONS: tuple[tuple[str, str], ...] = (
    ("easy", "Fácil"),
    ("medium", "Média"),
    ("hard", "Difícil"),
)

LEGACY_DIFFICULTY_LEVEL_LABELS: dict[str, str] = {
    "easyest": "Fácil (legado)",
    "hardest": "Difícil (legado)",
}

DIFFICULTY_LEVEL_LABELS: dict[str, str] = {
    code: label for code, label in DIFFICULTY_LEVEL_OPTIONS
} | LEGACY_DIFFICULTY_LEVEL_LABELS

UNCALCULATED_DIFFICULTY_LABEL = "Não calculado"
UNCALCULATED_DIFFICULTY_FILTER = "__uncalculated__"


def difficulty_level_label(code: str | None) -> str:
    if code is None or not str(code).strip():
        return UNCALCULATED_DIFFICULTY_LABEL
    return DIFFICULTY_LEVEL_LABELS.get(str(code).strip(), str(code).strip())


def validate_difficulty_level(code: str | None) -> None:
    if code is None:
        return
    normalized = code.strip()
    if not normalized:
        return
    if normalized not in DIFFICULTY_LEVEL_LABELS:
        allowed = ", ".join(sorted(DIFFICULTY_LEVEL_LABELS))
        raise ValueError(f"Dificuldade inválida. Valores aceitos: {allowed}")


def list_difficulty_levels_meta() -> list[dict[str, str]]:
    return [{"code": code, "label": label} for code, label in DIFFICULTY_LEVEL_OPTIONS]
