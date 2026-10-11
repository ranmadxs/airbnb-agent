"""Orden de tiras sigue el orden del filtro (rojo primero, luego azul).

TDD RED: pildorasVisibles y carrilEnFila ordenan por (start, id) y el azul
puede quedar arriba del rojo los días 13-14 en móvil.
"""
from pathlib import Path


def _html():
    return (Path(__file__).resolve().parent.parent / "airbnb_agent" / "templates" / "calendar.html").read_text(encoding="utf-8")


def test_pildoras_visibles_orden_filtro():
    html = _html()
    # Debe existir helper de índice por filtro y usarse en pildorasVisibles
    assert "indiceCalendario" in html or "ordenCalendario" in html or "filterOrder" in html
    # pildorasVisibles debe ordenar por calendario antes que por start
    idx = html.find("function pildorasVisibles")
    assert idx != -1
    bloque = html[idx:idx + 800]
    assert "calendario" in bloque.lower()


def test_carril_en_fila_orden_filtro():
    html = _html()
    idx = html.find("function carrilEnFila")
    assert idx != -1
    bloque = html[idx:idx + 1200]
    # carril debe usar el mismo orden de filtro, no solo (start, id)
    assert "compararPorFiltro" in bloque or "indiceCalendario" in bloque or "ordenCalendario" in bloque or "calendariosDisponibles" in bloque
