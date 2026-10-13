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


def test_movil_centra_por_carril_no_por_indice():
    """La tira continua no debe saltar de altura entre día multi y día solo."""
    html = _html()
    # el centrado móvil debe usar el carril global (dataset.lane), no el índice j del día
    assert "dataset.lane" in html


def test_grande_en_dias_solitarios():
    """La tira se agranda en días de un solo calendario, parta o continúe el evento."""
    html = _html()
    assert "grande: solo," in html


def test_checkout_con_gradiente():
    """El día de checkout (fin) lleva gradiente con brillo para la terminación curva."""
    html = _html()
    idx = html.find("function construirPildora")
    assert idx != -1
    bloque = html[idx:idx + 2500]
    assert "linear-gradient" in bloque and "color-mix" in bloque


def test_continuacion_ancla_borde_superior():
    """La tira que continúa del día anterior ancla su borde superior a la línea
    del carril (no se centra): el checkout solitario no cae bajo la línea."""
    html = _html()
    idx = html.find("para que la tira continua no salte")
    assert idx != -1
    bloque = html[idx:idx + 900]
    assert "con-izq" in bloque
