"""Aplicativo web Flask: input URL + selector de formato + botón 'Generar referencia'."""

from __future__ import annotations

import logging
import os
from dataclasses import asdict

from flask import Flask, jsonify, render_template, request

from .citations import SUPPORTED_FORMATS, format_reference
from .scraper import ScrapeError, scrape

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
log = logging.getLogger("citas")


def create_app() -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")

    @app.get("/")
    def index():
        return render_template("index.html", formats=SUPPORTED_FORMATS)

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.post("/api/generate")
    def generate():
        data = request.get_json(silent=True) or request.form
        url = (data.get("url") or "").strip()
        style = (data.get("style") or "apa").strip().lower()

        if not url:
            return jsonify({"ok": False, "error": "Debe ingresar una URL."}), 400
        if style not in SUPPORTED_FORMATS:
            return (
                jsonify({"ok": False, "error": f"Formato no soportado: {style}"}),
                400,
            )

        log.info("Generando referencia: url=%s style=%s", url, style)
        try:
            md = scrape(url)
        except ScrapeError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 422
        except Exception as exc:  # pragma: no cover -- defensa en profundidad
            log.exception("Error inesperado al scrapear")
            return jsonify({"ok": False, "error": f"Error inesperado: {exc}"}), 500

        try:
            reference = format_reference(md, style)
        except Exception as exc:
            log.exception("Error formateando referencia")
            return jsonify({"ok": False, "error": f"Error formateando: {exc}"}), 500

        payload = {
            "ok": True,
            "style": style,
            "reference": reference,
            "metadata": {
                "title": md.title,
                "authors": md.authors,
                "year": md.year,
                "publisher": md.publisher,
                "institution": md.institution,
                "type": md.type,
                "language": md.language,
                "handle": md.handle,
                "doi": md.doi,
                "advisor": md.advisor,
                "degree": md.degree,
            },
        }
        return jsonify(payload)

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
