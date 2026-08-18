"""Verificacion documental de la bibliografia de la tesis.

**No forma parte de SAVIP.** La auditoria de citas y la verificacion de fuentes
pertenecen al proceso academico del trabajo de grado, no al producto: la
aplicacion no incluye modulos, dependencias, pruebas en tiempo de ejecucion ni
archivos destinados a auditar referencias. Esta suite vive fuera de ``tests/``
por esa razon, no entra en ``packaging/SAVIP.spec`` y no la ejecuta
``docs/remediacion_auditoria/ejecutar_suites.py``.

Estas cuatro comprobaciones estaban dentro de
``tests/test_presentacion_resultados_y_referencias.py``, que mezclaba dos cosas
sin relacion: como se presenta un resultado en la interfaz y si una cita
bibliografica esta respaldada. La separacion se hizo el 29 de julio de 2026,
cuando un clon limpio revelo que la suite del producto no podia ejecutarse sin
``referencias_bibliograficas/``.

**Requiere** la carpeta ``referencias_bibliograficas/`` del proyecto, que
contiene los registros propios de verificacion (``verificacion.txt``,
``uso_en_latex.txt``, ``fuente_revisable.md``) junto con los artefactos
consultados. Esa carpeta no se versiona: los artefactos son material de
terceros y su redistribucion no esta resuelta. Sin ella esta suite no se puede
ejecutar, y lo declara en lugar de aprobar sin comprobar nada.

Ninguna comprobacion se debilito al mover el archivo: son las mismas cuatro,
con los mismos umbrales y las mismas rutas.

Ejecucion:

    python auditoria_academica/pruebas_documentales/test_referencias_documentales.py
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
BIBLIOTECA = RAIZ / "referencias_bibliograficas"


def test_referencias_latex_quedan_auditadas_y_sin_alias_duplicados() -> None:
    root = RAIZ
    latex_dir = root / "documentacion_latex" / "guia_academica_estadistica"
    assert latex_dir.is_dir(), "La guia academica vigente debe estar en documentacion_latex/."
    bib = (latex_dir / "referencias.bib").read_text(encoding="utf-8")
    audit = (root / "referencias_bibliograficas" / "auditoria_referencias.md").read_text(encoding="utf-8")
    used_dir = root / "referencias_bibliograficas" / "usadas_en_documento_latex"

    for alias in (
        "hyndman_athanasopoulos_2021",
        "hyndman_koehler_2006",
        "akaike_1974",
        "durbin_watson_1950",
        "jarque_bera_1980",
    ):
        assert alias not in bib

    # 22 tras retirar del alcance la referencia asociada a ARIMA.
    assert "Entradas citadas detectadas: 22" in audit
    assert "Claves citadas sin entrada BibTeX: 0" in audit
    assert len([p for p in used_dir.iterdir() if p.is_dir()]) == 22


def test_bibliografia_no_conserva_urls_editoriales_obsoletas() -> None:
    root = RAIZ
    latex_dir = root / "documentacion_latex" / "guia_academica_estadistica"
    assert latex_dir.is_dir(), "La guia academica vigente debe estar en documentacion_latex/."
    textos_auditar = [
        (latex_dir / "referencias.bib").read_text(encoding="utf-8"),
        (root / "referencias_bibliograficas" / "referencias_documento_latex.bib").read_text(encoding="utf-8"),
        (root / "referencias_bibliograficas" / "auditoria_referencias.md").read_text(encoding="utf-8"),
    ]
    mh = "https://www.mheducation.com/highered/product/"
    wiley = "https://www.wiley.com/en-us/"
    cengage = "https://www.cengage.com/c/"
    urls_obsoletas = (
        mh + "engineering-economy-blank-tarquin/M9780073523439.html",
        wiley + "Introduction+to+Linear+Regression+Analysis%2C+5th+Edition-p-9780470542811",
        cengage + "introductory-econometrics-a-modern-approach-7e-wooldridge/",
        mh + "basic-econometrics-gujarati-porter/M9780073375779.html",
    )

    for texto in textos_auditar:
        for url in urls_obsoletas:
            assert url not in texto

    bib = textos_auditar[0]
    assert "https://semmedia.mhhe.com/engineering/2021c_dieter6e/dieter6e_additional_chapters/die13299_ch17_001-040.pdf" in bib
    assert "https://online.stat.psu.edu/stat501/" in bib
    assert "https://www.statsmodels.org/stable/generated/statsmodels.stats.stattools.durbin_watson.html" in bib


def test_bibliografia_no_usa_catalogos_o_fichas_comerciales_como_fuente_principal() -> None:
    root = RAIZ
    latex_dir = root / "documentacion_latex" / "guia_academica_estadistica"
    assert latex_dir.is_dir(), "La guia academica vigente debe estar en documentacion_latex/."
    bib = (latex_dir / "referencias.bib").read_text(encoding="utf-8").lower()
    audit = (root / "referencias_bibliograficas" / "auditoria_referencias.md").read_text(encoding="utf-8").lower()
    used_dir = root / "referencias_bibliograficas" / "usadas_en_documento_latex"
    patrones_no_validos = (
        "amazon.",
        "scribd.com",
        "academia.edu",
        "worldcat.org",
        "mheducation.com/highered/product",
        "wiley.com/en-us/introduction+to+linear",
        "routledge.com/time-series-forecasting",
        "press.princeton.edu/books",
        "cengage.com/c/introductory",
    )

    for patron in patrones_no_validos:
        assert patron not in bib
        assert patron not in audit

    for carpeta in used_dir.iterdir():
        if not carpeta.is_dir():
            continue
        fuentes_materiales = [
            p for p in carpeta.iterdir()
            if p.name.startswith("fuente")
            and p.suffix.lower() not in {".txt", ".url", ".md"}
            and p.stat().st_size > 0
        ]
        assert fuentes_materiales, carpeta.name


def test_referencias_citadas_no_tienen_carpetas_solo_txt() -> None:
    root = RAIZ
    used_dir = root / "referencias_bibliograficas" / "usadas_en_documento_latex"

    carpetas_solo_txt = []
    faltan_uso = []
    for carpeta in used_dir.iterdir():
        if not carpeta.is_dir():
            continue
        archivos = [p for p in carpeta.iterdir() if p.is_file()]
        if not (carpeta / "uso_en_latex.txt").exists():
            faltan_uso.append(carpeta.name)
        if not [p for p in archivos if p.suffix.lower() != ".txt"]:
            carpetas_solo_txt.append(carpeta.name)

    assert not carpetas_solo_txt
    assert not faltan_uso


def _ejecutar() -> int:
    """Ejecutor propio, sin pytest, coherente con el resto del proyecto."""
    if not BIBLIOTECA.is_dir():
        print("NO EJECUTABLE: falta referencias_bibliograficas/ en "
              f"{RAIZ}.", file=sys.stderr)
        print("Esta suite es academica y necesita los registros de verificacion "
              "de fuentes, que no se versionan. No se aprueba nada por omision.",
              file=sys.stderr)
        return 2

    fallos = total = 0
    for nombre, funcion in sorted(globals().items()):
        if not nombre.startswith("test_") or not callable(funcion):
            continue
        total += 1
        try:
            funcion()
            print(f"  OK    {nombre}")
        except AssertionError as error:
            fallos += 1
            print(f"  FALLA {nombre}: {error}")
        except Exception as error:
            fallos += 1
            print(f"  ERROR {nombre}: {type(error).__name__}: {error}")
    print()
    print(f"{total - fallos}/{total} comprobaciones documentales aprobadas.")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(_ejecutar())
