"""Transformação e classificação de escala (lógica pura, sem banco)."""

from app.events.scale import classify_level, compute_proficiency

CODIGOS = ["AB", "B", "AD", "AV"]
CORTES = [200, 275, 325]  # LP 9º (v16)


def test_compute_proficiency_linear():
    # Saeb: a=50, b=250 -> θ=0.5 vira 275.
    assert compute_proficiency(50.0, 250.0, 0.5) == 275.0
    assert compute_proficiency(50.0, 250.0, 0.0) == 250.0


def test_classify_level_buckets():
    assert classify_level(199, CORTES, CODIGOS) == "AB"
    assert classify_level(200, CORTES, CODIGOS) == "B"  # limiar inferior inclusivo
    assert classify_level(274.9, CORTES, CODIGOS) == "B"
    assert classify_level(300, CORTES, CODIGOS) == "AD"
    assert classify_level(325, CORTES, CODIGOS) == "AV"
    assert classify_level(999, CORTES, CODIGOS) == "AV"


def test_classify_without_cortes_is_first_level():
    assert classify_level(123, [], CODIGOS) == "AB"


def test_classify_without_codigos_is_none():
    assert classify_level(300, CORTES, []) is None
