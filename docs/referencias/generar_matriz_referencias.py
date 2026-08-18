"""Genera la matriz de referencias y el manifiesto de fuentes externas.

Decisión autorizada el 29 de julio de 2026 (punto 2): los PDF y la biblioteca de
terceros **no** se versionan, pero sí deben versionarse ``referencias.bib``, una
matriz de referencias y un manifiesto de fuentes externas con DOI o URL, la
ubicación consultada, el estado de acceso y los hashes cuando corresponda.

Este script lee dos cosas que ya existen en el proyecto y no inventa ninguna:

1. ``documentacion_latex/documento_tecnico_icociv_iccp/referencias.bib``, que es
   la bibliografía real del documento;
2. ``referencias_bibliograficas/`` (carpeta local **excluida** del control de
   versiones), donde cada fuente tiene su ``verificacion.txt`` y su
   ``uso_en_latex.txt`` con el registro de acceso y de uso.

De la segunda carpeta se extrae metadato y hash, nunca contenido: el manifiesto
permite a un auditor confirmar qué artefacto se consultó sin redistribuirlo.

Si la carpeta local no está presente —el caso de un clon limpio— el script lo
declara y genera la matriz solo con lo que ``referencias.bib`` permite afirmar,
en lugar de fallar o de rellenar campos.

Uso:
    python docs/referencias/generar_matriz_referencias.py
"""
from __future__ import annotations

import csv
import hashlib
import re
import sys
from datetime import datetime
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[1]
BIB = RAIZ / "documentacion_latex" / "documento_tecnico_icociv_iccp" / "referencias.bib"
BIBLIOTECA = RAIZ / "referencias_bibliograficas"
CARPETAS_FUENTES = ("usadas_en_documento_latex", "usadas_en_otros_componentes")
SALIDA_CSV = AQUI / "MATRIZ_REFERENCIAS.csv"
SALIDA_MD = AQUI / "MANIFIESTO_FUENTES_EXTERNAS.md"

#: Archivos que constituyen la evidencia local de una fuente consultada.
EVIDENCIA = ("fuente.pdf", "fuente.html", "fuente_revisable.md",
             "fuente_semantic_scholar.json")

#: Encabezados de verificacion.txt, en el orden en que aparecen.
ENCABEZADOS = (
    "Referencia completa",
    "Clave BibTeX",
    "DOI",
    "URL oficial",
    "Tipo de fuente",
    "?Permite leer el contexto citado?",
    "Ubicacion exacta del contenido",
    "Afirmacion que respalda",
    "Estado",
    "Observaciones",
)

NO_REGISTRADO = "No registrado"


def _leer(ruta: Path) -> str:
    """Lee un archivo del proyecto tolerando BOM y codificación heredada."""
    crudo = ruta.read_bytes()
    for codec in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return crudo.decode(codec)
        except UnicodeDecodeError:
            continue
    return crudo.decode("utf-8", errors="replace")


def _una_linea(texto: str) -> str:
    return " ".join(str(texto).split())


# ==============================
# BIBLIOGRAFÍA
# ==============================


def entradas_bib(ruta: Path) -> dict[str, dict[str, str]]:
    """Extrae clave, tipo, autor, año, título, DOI y URL de cada entrada."""
    texto = _leer(ruta)
    entradas: dict[str, dict[str, str]] = {}
    for bloque in re.finditer(r"@(\w+)\s*\{\s*([^,]+),(.*?)\n\}", texto, re.S):
        tipo, clave, cuerpo = bloque.group(1), bloque.group(2).strip(), bloque.group(3)
        campos = {"tipo_bib": tipo}
        for campo in ("author", "year", "title", "doi", "url", "institution", "publisher"):
            hallado = re.search(rf"\b{campo}\s*=\s*[{{\"](.*?)[}}\"]\s*,?\s*\n",
                                cuerpo, re.S | re.I)
            campos[campo] = _una_linea(hallado.group(1)) if hallado else ""
        entradas[clave] = campos
    return entradas


def citas_en_documento(ruta_tex: Path) -> dict[str, int]:
    """Cuenta cuántas veces se cita cada clave en el documento final."""
    if not ruta_tex.is_file():
        return {}
    texto = _leer(ruta_tex)
    conteo: dict[str, int] = {}
    # El documento usa \parencite y \textcite de apacite, no solo \cite: el patron
    # acepta cualquier comando que contenga "cite" para no perder citas por nombre.
    for grupo in re.finditer(r"\\[a-zA-Z]*cite[a-zA-Z]*\*?(?:\[[^\]]*\])*\{([^}]*)\}", texto):
        for clave in grupo.group(1).split(","):
            clave = clave.strip()
            if clave:
                conteo[clave] = conteo.get(clave, 0) + 1
    return conteo


# ==============================
# BIBLIOTECA LOCAL (EXCLUIDA DE GIT)
# ==============================


def _campos_verificacion(texto: str) -> dict[str, str]:
    """Parte verificacion.txt en sus secciones declaradas."""
    campos: dict[str, str] = {}
    actual: str | None = None
    acumulado: list[str] = []
    for linea in texto.splitlines():
        limpia = linea.strip()
        if limpia.rstrip(":") in ENCABEZADOS and limpia.endswith(":"):
            if actual:
                campos[actual] = _una_linea(" ".join(acumulado))
            actual, acumulado = limpia.rstrip(":"), []
            continue
        if actual and limpia:
            acumulado.append(limpia)
    if actual:
        campos[actual] = _una_linea(" ".join(acumulado))
    return campos


def _sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open("rb") as f:
        for trozo in iter(lambda: f.read(65536), b""):
            h.update(trozo)
    return h.hexdigest()


def _evidencia_local(carpeta: Path) -> list[tuple[str, int, str]]:
    """Nombre, tamaño y SHA-256 de cada artefacto consultado de la fuente."""
    salida: list[tuple[str, int, str]] = []
    for nombre in EVIDENCIA:
        ruta = carpeta / nombre
        if ruta.is_file():
            salida.append((nombre, ruta.stat().st_size, _sha256(ruta)))
    return salida


def fuentes_locales() -> dict[str, dict[str, object]]:
    """Metadato y hashes por clave BibTeX; vacío si la biblioteca no está."""
    fuentes: dict[str, dict[str, object]] = {}
    for nombre_carpeta in CARPETAS_FUENTES:
        raiz = BIBLIOTECA / nombre_carpeta
        if not raiz.is_dir():
            continue
        for carpeta in sorted(p for p in raiz.iterdir() if p.is_dir()):
            verificacion = carpeta / "verificacion.txt"
            if not verificacion.is_file():
                continue
            campos = _campos_verificacion(_leer(verificacion))
            clave = campos.get("Clave BibTeX", "").strip() or carpeta.name.split("_")[-1]
            uso = carpeta / "uso_en_latex.txt"
            fuentes[clave] = {
                "carpeta": f"{nombre_carpeta}/{carpeta.name}",
                "campos": campos,
                "evidencia": _evidencia_local(carpeta),
                "usos_registrados": _leer(uso).count("- Archivo:") if uso.is_file() else 0,
            }
    return fuentes


# ==============================
# SALIDAS
# ==============================


def main() -> int:
    if not BIB.is_file():
        print(f"Falta {BIB}", file=sys.stderr)
        return 2

    bib = entradas_bib(BIB)
    citas = citas_en_documento(BIB.with_name("main.tex"))
    locales = fuentes_locales()
    biblioteca_presente = bool(locales)

    filas: list[list[str]] = []
    for clave in sorted(bib):
        b = bib[clave]
        local = locales.get(clave, {})
        campos: dict[str, str] = local.get("campos", {})  # type: ignore[assignment]
        evidencia: list[tuple[str, int, str]] = local.get("evidencia", [])  # type: ignore[assignment]

        doi = b["doi"] or campos.get("DOI", "")
        url = b["url"] or campos.get("URL oficial", "")
        filas.append([
            clave,
            b["tipo_bib"],
            b["author"] or NO_REGISTRADO,
            b["year"] or NO_REGISTRADO,
            b["title"] or NO_REGISTRADO,
            doi.strip() or "Sin DOI",
            url.strip() or "Sin URL",
            campos.get("Tipo de fuente", NO_REGISTRADO if biblioteca_presente else "No evaluable sin la biblioteca local"),
            campos.get("Ubicacion exacta del contenido", NO_REGISTRADO),
            campos.get("?Permite leer el contexto citado?", NO_REGISTRADO),
            campos.get("Estado", NO_REGISTRADO),
            str(citas.get(clave, 0)),
            "; ".join(f"{n} sha256={h}" for n, _t, h in evidencia) or "Sin artefacto local",
            str(local.get("carpeta", "")) or "No presente en la copia local",
        ])

    huerfanas = sorted(k for k in locales if k not in bib)
    sin_citar = sorted(k for k in bib if not citas.get(k))

    with SALIDA_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow([
            "Clave BibTeX", "Tipo de entrada", "Autor", "Anio", "Titulo",
            "DOI", "URL", "Tipo de fuente", "Ubicacion consultada",
            "Permite leer el contexto citado", "Estado de acceso",
            "Citas en main.tex", "Hash del artefacto consultado",
            "Carpeta local (no versionada)",
        ])
        w.writerows(filas)

    con_hash = sum(1 for f_ in filas if not f_[12].startswith("Sin artefacto"))
    con_doi = sum(1 for f_ in filas if f_[5] != "Sin DOI")
    con_url = sum(1 for f_ in filas if f_[6] != "Sin URL")

    SALIDA_MD.write_text(_manifiesto(
        filas, con_hash, con_doi, con_url, biblioteca_presente, huerfanas, sin_citar,
    ), encoding="utf-8")

    print(f"{SALIDA_CSV.name}: {len(filas)} referencias")
    print(f"  con DOI: {con_doi} | con URL: {con_url} | con hash local: {con_hash}")
    print(f"  biblioteca local presente: {'si' if biblioteca_presente else 'no'}")
    if huerfanas:
        print(f"  claves locales que no estan en referencias.bib: {', '.join(huerfanas)}")
    if sin_citar:
        print(f"  entradas de bib sin cita en main.tex: {', '.join(sin_citar)}")
    return 0


def _manifiesto(
    filas: list[list[str]],
    con_hash: int,
    con_doi: int,
    con_url: int,
    biblioteca_presente: bool,
    huerfanas: list[str],
    sin_citar: list[str],
) -> str:
    lineas = [
        "# Manifiesto de fuentes externas",
        "",
        f"**Generado:** {datetime.now().strftime('%Y-%m-%d %H:%M')} por "
        "`docs/referencias/generar_matriz_referencias.py`",
        "**Matriz tabulada:** `MATRIZ_REFERENCIAS.csv`",
        "**Bibliografía versionada:** "
        "`documentacion_latex/documento_tecnico_icociv_iccp/referencias.bib`",
        "",
        "## 1. Qué se versiona y qué no",
        "",
        "Decisión autorizada el 29 de julio de 2026. Los PDF y la biblioteca de "
        "referencias de terceros **no** se versionan: `referencias_bibliograficas/` "
        "permanece excluida del control de versiones hasta revisar los permisos de "
        "redistribución de cada fuente. Lo que sí se versiona es la bibliografía "
        "(`referencias.bib`), la matriz de referencias y este manifiesto.",
        "",
        "El manifiesto registra el **hash** del artefacto consultado, no el "
        "artefacto. Eso permite a un auditor con acceso legítimo a la fuente "
        "confirmar que revisó el mismo documento, sin que el repositorio "
        "redistribuya material de terceros.",
        "",
        "## 2. Cobertura",
        "",
        f"| Concepto | Valor |",
        "|---|---|",
        f"| Referencias en `referencias.bib` | {len(filas)} |",
        f"| Con DOI registrado | {con_doi} |",
        f"| Con URL registrada | {con_url} |",
        f"| Con hash del artefacto consultado | {con_hash} |",
        f"| Biblioteca local disponible al generar | {'sí' if biblioteca_presente else 'no'} |",
        "",
    ]
    if not biblioteca_presente:
        lineas += [
            "> **Advertencia.** Este manifiesto se generó sin la carpeta local "
            "`referencias_bibliograficas/`, por lo que los campos de estado de acceso, "
            "ubicación consultada y hash quedaron sin registrar. No es un dato ausente "
            "en la fuente: es un dato que esta ejecución no pudo leer. Para completarlo "
            "hay que regenerar el manifiesto en la máquina que conserva la biblioteca.",
            "",
        ]
    lineas += [
        "## 3. Fuentes",
        "",
        "| Clave | Autor | Año | DOI o URL | Estado de acceso | Citas | Hash |",
        "|---|---|---|---|---|---|---|",
    ]
    for f in filas:
        identificador = f[5] if f[5] != "Sin DOI" else f[6]
        hash_corto = (f[12].split("sha256=")[-1][:16] + "…") if "sha256=" in f[12] else "—"
        lineas.append(
            f"| `{f[0]}` | {f[2][:40]} | {f[3]} | {identificador[:60]} | "
            f"{f[10]} | {f[11]} | `{hash_corto}` |"
        )
    lineas += [
        "",
        "Los hashes completos están en `MATRIZ_REFERENCIAS.csv`, columna "
        "«Hash del artefacto consultado», junto con el nombre del archivo al que "
        "corresponde cada uno.",
        "",
        "## 4. Sobre las páginas consultadas",
        "",
        "La columna «Ubicación consultada» reproduce lo que quedó registrado al "
        "verificar cada fuente. Cuando la fuente es paginada y el registro anotó la "
        "página, ahí aparece; cuando es un recurso web sin paginación, o cuando el "
        "registro no la anotó, dice qué se leyó en lugar de inventar un número de "
        "página. Ninguna página se completó por inferencia.",
        "",
        "## 5. Consistencia",
        "",
    ]
    if huerfanas:
        lineas += [
            "Claves con carpeta local que **no** están en `referencias.bib` "
            "(material consultado que el documento final ya no cita):",
            "",
        ] + [f"- `{k}`" for k in huerfanas] + [""]
    else:
        lineas += ["Toda carpeta local corresponde a una entrada de `referencias.bib`.", ""]
    if sin_citar:
        lineas += [
            "Entradas de `referencias.bib` sin cita detectada en `main.tex`:",
            "",
        ] + [f"- `{k}`" for k in sin_citar] + [
            "",
            "Una entrada sin citar no es necesariamente un error —puede sostener un "
            "anexo o una tabla generada— pero conviene revisarla antes de cerrar el "
            "documento.",
            "",
        ]
    else:
        lineas += ["Toda entrada de `referencias.bib` se cita al menos una vez en "
                   "`main.tex`.", ""]
    lineas += [
        "## 6. Reproducción",
        "",
        "```bash",
        "python docs/referencias/generar_matriz_referencias.py",
        "```",
        "",
        "El script no descarga nada ni consulta la red: lee `referencias.bib` y, si "
        "está disponible, la carpeta local de verificación. Es determinista salvo el "
        "sello de fecha de la cabecera.",
    ]
    return "\n".join(lineas) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
