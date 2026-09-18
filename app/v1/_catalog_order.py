"""Ordenação canônica de segmento, série, área e disciplina (UI e catálogo)."""

from __future__ import annotations


def segment_order_key_sql(column: str = "name") -> str:
    """Anos iniciais → Anos finais → Ensino Médio; demais por último."""
    return f"""CASE
  WHEN {column} ILIKE '%anos iniciais%' THEN 1
  WHEN {column} ILIKE '%anos finais%' THEN 2
  WHEN {column} ILIKE '%médio%' OR {column} ILIKE '%medio%' THEN 3
  ELSE 99
END"""


def curricular_area_label_order_sql(prefix: str) -> str:
    """Rótulo BNCC por etapa (campo name)."""
    return f"LOWER({prefix}.name)"


def discipline_name_order_sql(prefix: str = "d") -> str:
    """Nome do componente (campo exibido nos selects de disciplina)."""
    return f"LOWER({prefix}.name)"
