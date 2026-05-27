"""Tests unitarios de los formateadores y del parser HTML."""

from __future__ import annotations

import pytest

from app.citations import format_reference, parse_name
from app.scraper import (
    Metadata,
    _has_real_metadata,
    _looks_like_challenge_title,
    parse_metadata,
)


SAMPLE_HTML = """
<!doctype html>
<html lang="es">
<head>
<meta name="citation_title" content="Asociación de Fobia Social en el Rendimiento Académico" />
<meta name="citation_author" content="Díaz Murillo Henry Juan" />
<meta name="citation_publication_date" content="2006" />
<meta name="citation_publisher" content="Universidad Católica de Santa María" />
<meta name="citation_language" content="spa" />
<meta name="DC.type" content="info:eu-repo/semantics/bachelorThesis" />
<meta name="DC.identifier.uri" content="https://repositorio.ucsm.edu.pe/handle/20.500.12920/6972" />
<meta name="DC.thesis.degree.name" content="Médico Cirujano" />
</head>
<body></body>
</html>
"""


@pytest.fixture()
def md() -> Metadata:
    return parse_metadata(
        SAMPLE_HTML,
        url="https://repositorio.ucsm.edu.pe/items/be52cb1c-7c6b-4ba5-a1ed-b2369643b85e",
    )


def test_parse_metadata_basic(md: Metadata) -> None:
    assert md.title == "Asociación de Fobia Social en el Rendimiento Académico"
    assert md.authors == ["Díaz Murillo Henry Juan"]
    assert md.year == "2006"
    assert md.institution == "Universidad Católica de Santa María"
    assert md.language == "spa"
    assert md.handle == "20.500.12920/6972"
    assert md.is_usable()


def test_parse_name_dspace_three_tokens() -> None:
    n = parse_name("Díaz Murillo Henry Juan")
    assert n.last == "Díaz Murillo"
    assert n.first == "Henry Juan"
    assert n.initials == "H. J."
    assert n.initials_no_space == "HJ"


def test_parse_name_with_comma() -> None:
    n = parse_name("Díaz Murillo, Henry Juan")
    assert n.last == "Díaz Murillo"
    assert n.first == "Henry Juan"


def test_apa_format(md: Metadata) -> None:
    ref = format_reference(md, "apa")
    assert "Díaz Murillo, H. J." in ref
    assert "(2006)" in ref
    assert "Asociación de Fobia Social" in ref
    assert "Universidad Católica de Santa María" in ref
    assert "https://repositorio.ucsm.edu.pe/items/" in ref


def test_vancouver_format(md: Metadata) -> None:
    ref = format_reference(md, "vancouver")
    assert "Díaz Murillo HJ" in ref
    assert "2006" in ref
    assert "Disponible en:" in ref


def test_ieee_format(md: Metadata) -> None:
    ref = format_reference(md, "ieee")
    assert "H. J. Díaz Murillo" in ref
    assert "2006" in ref
    assert "[En línea]" in ref


def test_mla_format(md: Metadata) -> None:
    ref = format_reference(md, "mla")
    assert "Díaz Murillo" in ref
    assert "2006" in ref


def test_chicago_format(md: Metadata) -> None:
    ref = format_reference(md, "chicago")
    assert "Díaz Murillo" in ref
    assert "2006" in ref


def test_iso690_format(md: Metadata) -> None:
    ref = format_reference(md, "iso690")
    assert "DÍAZ MURILLO" in ref
    assert "Disponible en:" in ref


def test_unsupported_format_raises(md: Metadata) -> None:
    with pytest.raises(ValueError):
        format_reference(md, "harvard")


def test_metadata_without_year_uses_sf() -> None:
    md = parse_metadata(
        '<html><head><meta name="citation_title" content="Sin año"/>'
        '<meta name="citation_author" content="López, Juan"/></head></html>',
        url="https://example.com/x",
    )
    assert md.year is None
    ref = format_reference(md, "apa")
    assert "s.f." in ref


def test_multiple_authors_apa() -> None:
    md = parse_metadata(
        '<html><head>'
        '<meta name="citation_title" content="Estudio colaborativo"/>'
        '<meta name="citation_author" content="Pérez García María"/>'
        '<meta name="citation_author" content="López Rojas Luis"/>'
        '<meta name="citation_publication_date" content="2020-05-12"/>'
        '</head></html>',
        url="https://repositorio.utp.edu.pe/items/xyz",
    )
    assert md.authors == ["Pérez García María", "López Rojas Luis"]
    assert md.year == "2020"
    assert md.institution == "Universidad Tecnológica del Perú"
    ref = format_reference(md, "apa")
    assert "Pérez García, M." in ref
    assert "López Rojas, L." in ref
    assert "&" in ref


def test_cloudflare_challenge_page_is_rejected() -> None:
    """Una página de reto Cloudflare ('Un momento…') no debe pasar como metadato real."""
    challenge_html = (
        "<!doctype html><html><head>"
        "<title>Un momento…</title>"
        "</head><body>Estamos verificando tu navegador...</body></html>"
    )
    md = parse_metadata(
        challenge_html,
        url="https://repositorio.ucsm.edu.pe/items/be52cb1c-7c6b-4ba5-a1ed-b2369643b85e",
    )
    # parse_metadata sí extrae el <title>, pero la validación lo debe rechazar.
    assert md.title == "Un momento…"
    assert _looks_like_challenge_title(md.title)
    assert not _has_real_metadata(md)


def test_has_real_metadata_accepts_dspace_page() -> None:
    md = parse_metadata(SAMPLE_HTML, url="https://repositorio.ucsm.edu.pe/items/x")
    assert _has_real_metadata(md)


def test_etiquetas_dc_lowercase() -> None:
    """DSpace en algunos repos emite las etiquetas en minúsculas (dc.title)."""
    html = (
        '<html><head>'
        '<meta name="dc.title" content="Algo"/>'
        '<meta name="dc.creator" content="Ruiz, Ana"/>'
        '<meta name="dc.date.issued" content="2019"/>'
        '</head></html>'
    )
    md = parse_metadata(html, url="https://example.com/x")
    assert md.title == "Algo"
    assert md.authors == ["Ruiz, Ana"]
    assert md.year == "2019"
