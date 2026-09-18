"""Catálogo de tipos de questão (código EN → rótulo PT-BR).

A plataforma (prova do aluno + correção) implementa apenas múltipla escolha
com uma alternativa correta (`student-exam-page` radiogroup + validação no CRUD).
"""

from __future__ import annotations

# Único tipo ofertado em questões novas / edição no admin.
SUPPORTED_QUESTION_TYPE_OPTIONS: tuple[tuple[str, str], ...] = (
    ("multiple_choice", "Múltipla escolha"),
)

# Valores legados ainda no banco — rótulo na listagem; não aparecem no seletor.
LEGACY_QUESTION_TYPE_LABELS: dict[str, str] = {
    "correctAlternative": "Múltipla escolha (legado)",
    "single_choice": "Múltipla escolha (legado)",
    "multiple_choice_single": "Múltipla escolha (legado)",
}

# Tipos conhecidos mas não implementados — não aceitos em create/update.
DEPRECATED_QUESTION_TYPE_LABELS: dict[str, str] = {
    "multiple_choice_multiple": "Múltipla escolha múltipla (indisponível)",
    "true_false": "Verdadeiro/Falso (indisponível)",
    "constructed_response": "Resposta construída (indisponível)",
}

QUESTION_TYPE_LABELS: dict[str, str] = {
    code: label for code, label in SUPPORTED_QUESTION_TYPE_OPTIONS
} | LEGACY_QUESTION_TYPE_LABELS | DEPRECATED_QUESTION_TYPE_LABELS

SELECTABLE_QUESTION_TYPE_CODES: frozenset[str] = frozenset(
    code for code, _ in SUPPORTED_QUESTION_TYPE_OPTIONS
)

_ASSIGNABLE_CODES: frozenset[str] = SELECTABLE_QUESTION_TYPE_CODES | frozenset(
    LEGACY_QUESTION_TYPE_LABELS
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
        allowed = ", ".join(sorted(_ASSIGNABLE_CODES))
        raise ValueError(
            f"Tipo de questão inválido. Valores aceitos: {allowed}",
        )
    if normalized not in _ASSIGNABLE_CODES:
        raise ValueError(
            "Este tipo de questão ainda não é suportado pela plataforma. "
            "Use «Múltipla escolha».",
        )


def list_question_types_meta(*, include_legacy: bool = False) -> list[dict[str, str]]:
    items = [{"code": code, "label": label} for code, label in SUPPORTED_QUESTION_TYPE_OPTIONS]
    if include_legacy:
        for code, label in LEGACY_QUESTION_TYPE_LABELS.items():
            items.append({"code": code, "label": label})
    return items
