"""Generadores de referencias bibliográficas en distintos estilos.

Estilos soportados:
  - APA 7
  - Vancouver
  - IEEE
  - MLA 9
  - Chicago (autor-fecha y notas-bibliografía)
  - ISO 690
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Callable

from .scraper import Metadata


# ---------------------------------------------------------------------------
# Utilidades de nombres
# ---------------------------------------------------------------------------


@dataclass
class _Name:
    last: str   # apellido(s)
    first: str  # nombre(s) -- puede ser vacío

    @property
    def initials(self) -> str:
        """Iniciales con punto, p.ej. 'Henry Juan' -> 'H. J.'"""
        parts = [p for p in re.split(r"\s+", self.first.strip()) if p]
        return " ".join(f"{p[0].upper()}." for p in parts)

    @property
    def initials_no_space(self) -> str:
        """Vancouver: 'HJ'"""
        parts = [p for p in re.split(r"\s+", self.first.strip()) if p]
        return "".join(p[0].upper() for p in parts)


_HONORIFICS = {"dr", "dra", "mg", "mgr", "lic",
               "prof", "ph", "phd", "mr", "mrs", "ms"}


def parse_name(raw: str) -> _Name:
    """Normaliza un nombre desde formatos comunes en DSpace peruano.

    Maneja:
      - "Apellido1 Apellido2 Nombre1 Nombre2"  (DSpace peruano sin coma)
      - "Apellido, Nombre"                       (formato 'Last, First')
      - "Nombre Apellido"                        (orden directo)
    """
    s = re.sub(r"\s+", " ", raw or "").strip().strip(",")
    if not s:
        return _Name("", "")

    if "," in s:
        last, _, first = s.partition(",")
        return _Name(last.strip(), first.strip())

    tokens = s.split(" ")
    # Quita honoríficos al final
    tokens = [t for t in tokens if t.lower().rstrip(".") not in _HONORIFICS]

    if len(tokens) == 1:
        return _Name(tokens[0], "")
    if len(tokens) == 2:
        # Asumimos "Apellido Nombre" (convención DSpace) si los dos empiezan con mayúscula.
        # Pero si el segundo es claramente nombre común, asumimos "Nombre Apellido".
        # Sin un diccionario, la convención DSpace gana.
        return _Name(tokens[0], tokens[1])
    if len(tokens) == 3:
        # "Apellido1 Apellido2 Nombre"  (lo más común en DSpace peruano)
        return _Name(f"{tokens[0]} {tokens[1]}", tokens[2])
    # 4+ tokens: asumimos los dos primeros apellidos
    return _Name(f"{tokens[0]} {tokens[1]}", " ".join(tokens[2:]))


# ---------------------------------------------------------------------------
# Helpers comunes
# ---------------------------------------------------------------------------


def _title(md: Metadata) -> str:
    return (md.title or "[Sin título]").strip().rstrip(".")


def _year(md: Metadata) -> str:
    return md.year or "s.f."


def _publisher(md: Metadata) -> str:
    return (md.institution or md.publisher or "").strip().rstrip(".")


def _today_es() -> str:
    months = [
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "setiembre", "octubre", "noviembre", "diciembre",
    ]
    t = date.today()
    return f"{t.day} de {months[t.month - 1]} de {t.year}"


def _is_thesis(md: Metadata) -> bool:
    t = (md.type or "").lower()
    return any(k in t for k in ("tesis", "thesis", "info:eu-repo/semantics/bachelorthesis",
                                "info:eu-repo/semantics/masterthesis",
                                "info:eu-repo/semantics/doctoralthesis", "dissertation"))


# ---------------------------------------------------------------------------
# Formateadores por estilo
# ---------------------------------------------------------------------------


def format_apa(md: Metadata) -> str:
    """APA 7."""
    names = [parse_name(a) for a in md.authors]
    if not names:
        authors_str = "[Autor desconocido]"
    elif len(names) == 1:
        authors_str = f"{names[0].last}, {names[0].initials}".rstrip(", ")
    elif len(names) <= 20:
        parts = [f"{n.last}, {n.initials}".rstrip(", ") for n in names]
        authors_str = ", ".join(parts[:-1]) + f", & {parts[-1]}"
    else:
        first19 = [f"{n.last}, {n.initials}".rstrip(", ") for n in names[:19]]
        authors_str = ", ".join(
            first19) + f", … {names[-1].last}, {names[-1].initials}".rstrip(", ")

    year = _year(md)
    title = _title(md)
    pub = _publisher(md)
    kind = ""
    if _is_thesis(md):
        degree = (md.degree or "Tesis").strip()
        kind = f" [{degree}, {pub}]" if pub else f" [{degree}]"
        ref = f"{authors_str} ({year}). *{title}*{kind}. {pub}. {md.url}"
    else:
        ref = f"{authors_str} ({year}). *{title}*."
        if pub:
            ref += f" {pub}."
        ref += f" {md.url}"
    return _clean(ref)


def format_vancouver(md: Metadata) -> str:
    """Vancouver."""
    names = [parse_name(a) for a in md.authors]
    if not names:
        authors_str = "Anónimo"
    else:
        parts = [f"{n.last} {n.initials_no_space}".strip() for n in names[:6]]
        authors_str = ", ".join(parts)
        if len(names) > 6:
            authors_str += ", et al"

    title = _title(md)
    pub = _publisher(md)
    year = _year(md)
    accessed = _today_es()

    bracket = ""
    if _is_thesis(md):
        bracket = " [tesis en Internet]"
    else:
        bracket = " [Internet]"

    ref = (
        f"{authors_str}. {title}{bracket}. "
        f"{pub + '; ' if pub else ''}{year} [citado {accessed}]. Disponible en: {md.url}"
    )
    return _clean(ref)


def format_ieee(md: Metadata) -> str:
    """IEEE."""
    names = [parse_name(a) for a in md.authors]
    if not names:
        authors_str = "Anónimo"
    else:
        def _ieee(n: _Name) -> str:
            ini = n.initials.replace(" ", " ")
            return f"{ini} {n.last}".strip()
        parts = [_ieee(n) for n in names]
        if len(parts) == 1:
            authors_str = parts[0]
        elif len(parts) == 2:
            authors_str = f"{parts[0]} y {parts[1]}"
        else:
            authors_str = ", ".join(parts[:-1]) + f", y {parts[-1]}"

    title = _title(md)
    pub = _publisher(md)
    year = _year(md)
    accessed = _today_es()

    kind = "Tesis" if _is_thesis(md) else "en línea"
    ref = (
        f"{authors_str}, \"{title},\" {kind}, "
        f"{pub + ', ' if pub else ''}{year}. [En línea]. Disponible: {md.url}. "
        f"[Acceso: {accessed}]."
    )
    return _clean(ref)


def format_mla(md: Metadata) -> str:
    """MLA 9."""
    names = [parse_name(a) for a in md.authors]
    if not names:
        authors_str = ""
    elif len(names) == 1:
        n = names[0]
        authors_str = f"{n.last}, {n.first}".rstrip(", ")
    elif len(names) == 2:
        n1, n2 = names
        authors_str = f"{n1.last}, {n1.first}, y {n2.first} {n2.last}".rstrip(
            ", ")
    else:
        n = names[0]
        authors_str = f"{n.last}, {n.first}, et al."

    title = _title(md)
    pub = _publisher(md)
    year = _year(md)
    accessed = _today_es()
    ref = (
        f"{authors_str + '. ' if authors_str else ''}"
        f"\"{title}.\" "
        f"{pub + ', ' if pub else ''}{year}, {md.url}. Acceso {accessed}."
    )
    return _clean(ref)


def format_chicago(md: Metadata) -> str:
    """Chicago (autor-fecha)."""
    names = [parse_name(a) for a in md.authors]
    if not names:
        authors_str = ""
    elif len(names) == 1:
        n = names[0]
        authors_str = f"{n.last}, {n.first}".rstrip(", ")
    else:
        first = names[0]
        rest = [f"{n.first} {n.last}".strip() for n in names[1:]]
        authors_str = f"{first.last}, {first.first}, y " + ", ".join(rest)
        authors_str = authors_str.rstrip(", ")

    title = _title(md)
    pub = _publisher(md)
    year = _year(md)
    ref = (
        f"{authors_str + '. ' if authors_str else ''}"
        f"{year}. \"{title}.\" "
        f"{pub + '. ' if pub else ''}{md.url}."
    )
    return _clean(ref)


def format_iso690(md: Metadata) -> str:
    """ISO 690."""
    names = [parse_name(a) for a in md.authors]
    if not names:
        authors_str = "ANÓNIMO"
    else:
        def _iso(n: _Name) -> str:
            return f"{n.last.upper()}, {n.first}".rstrip(", ")
        parts = [_iso(n) for n in names[:3]]
        authors_str = "; ".join(parts)
        if len(names) > 3:
            authors_str += "; et al."

    title = _title(md)
    pub = _publisher(md)
    year = _year(md)
    accessed = _today_es()
    kind = "Tesis" if _is_thesis(md) else "documento en línea"
    ref = (
        f"{authors_str}. *{title}* [{kind}]. "
        f"{pub + ', ' if pub else ''}{year} [consultado: {accessed}]. "
        f"Disponible en: {md.url}"
    )
    return _clean(ref)


def _clean(s: str) -> str:
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\s+([.,;:])", r"\1", s)
    s = re.sub(r"\.{2,}", ".", s)
    return s.strip()


FORMATTERS: dict[str, Callable[[Metadata], str]] = {
    "apa": format_apa,
    "vancouver": format_vancouver,
    "ieee": format_ieee,
    "mla": format_mla,
    "chicago": format_chicago,
    "iso690": format_iso690,
}


SUPPORTED_FORMATS = list(FORMATTERS.keys())


def format_reference(md: Metadata, style: str) -> str:
    fmt = FORMATTERS.get(style.lower())
    if not fmt:
        raise ValueError(
            f"Formato no soportado: {style!r}. Use uno de: {SUPPORTED_FORMATS}")
    return fmt(md)
