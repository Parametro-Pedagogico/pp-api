"""Catálogo de tipos de questão (código EN → rótulo PT-BR)."""

from __future__ import annotations

QUESTION_TYPE_OPTIONS: tuple[tuple[str, str], ...] = (
    ("multiple_choice_single", "Múltipla escolha única"),
    ("multiple_choice_multiple", "Múltipla escolha múltipla"),
    ("multiple_choice", "Múltipla escolha"),
    ("true_false", "Verdadeiro/Falso"),
    ("constructed_response", "Resposta construída"),
)

# Valores legados ainda presentes no banco — exibidos, mas não ofertados em questões novas.
LEGACY_QUESTION_TYPE_LABELS: dict[str, str] = {
    "correctAlternative": "Alternativa correta (legado)",
    "single_choice": "Múltipla escolha (única resposta)",
}

QUESTION_TYPE_LABELS: dict[str, str] = {
    code: label for code, label in QUESTION_TYPE_OPTIONS
} | LEGACY_QUESTION_TYPE_LABELS

SELECTABLE_QUESTION_TYPE_CODES: frozenset[str] = frozenset(
    code for code, _ in QUESTION_TYPE_OPTIONS
)


def question_type_label(code: str | None) -> str | None:
    if code is None or not str(code).strip():
        return None
    return QUESTION_TYPE_LABELS.get(str(code).strip(), str(code).strip())


def validate_question_type(code: str | None) -> None:
    if code is None:
        return
    normalized = code.strip()
    if not normalized:
        return
    if normalized not in QUESTION_TYPE_LABELS:
        allowed = ", ".join(sorted(QUESTION_TYPE_LABELS))
        raise ValueError(f"Tipo de questão inválido. Valores aceitos: {allowed}")


def list_question_types_meta(*, include_legacy: bool = False) -> list[dict[str, str]]:
    items = [{"code": code, "label": label} for code, label in QUESTION_TYPE_OPTIONS]
    if include_legacy:
        for code, label in LEGACY_QUESTION_TYPE_LABELS.items():
            items.append({"code": code, "label": label})
    return items
