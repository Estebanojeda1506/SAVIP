"""Genera tabla_criterios.tex desde la matriz de criterios de criterios.py.

Emite anchos de columna fraccionales sobre \\linewidth para que la misma tabla
quepa tanto en el anexo independiente (retrato) como en el cuerpo de la tesis
(paisaje). Se escribe en las dos carpetas que la incorporan con \\input.

La tabla publicada NO incluye la columna de identificador interno ni la de ruta
de implementacion en el repositorio: el lector de la tesis no accede al codigo,
por lo que esas columnas se omiten. La trazabilidad interna sigue viviendo en la
matriz del codigo; aqui solo se publican criterio, tipo, valor y sustento.
"""
import sys
from pathlib import Path

RAIZ = Path(r"C:\Users\Esteban\Desktop\Proyecto trabajo de grado\Proyecto")
sys.path.insert(0, str(RAIZ))
from app_icociv.estadistica.criterios import matriz_criterios  # noqa: E402


def esc(s: object) -> str:
    t = str(s)
    t = t.replace("\\", "\\textbackslash{}")
    # `^` y `~` tambien son caracteres activos en LaTeX: sin escapar, un `e^2`
    # dentro del texto de un criterio rompe la compilacion fuera de modo
    # matematico. Detectado el 09-08-2026 al publicar la formula de C-INT-001.
    for a, b in (("&", "\\&"), ("%", "\\%"), ("_", "\\_"), ("#", "\\#"), ("$", "\\$"),
                 ("^", "\\textasciicircum{}"), ("~", "\\textasciitilde{}")):
        t = t.replace(a, b)
    # Los identificadores internos -`operativo_interno_sin_sustento` y
    # similares- son cadenas largas SIN punto de corte natural, y en las
    # columnas estrechas de la tabla desbordaban la caja hacia el margen.
    # `\allowbreak` autoriza el corte de linea tras cada guion bajo sin
    # anadir ningun caracter visible ni alterar el texto publicado.
    t = t.replace("\\_", "\\_\\allowbreak{}")
    t = t.replace(">=", "$\\geq$").replace("<=", "$\\leq$")
    t = t.replace(" > ", " $>$ ").replace(" < ", " $<$ ")
    return t


def _tabla(columnas_ancho: str, encabezados: str, n_cols: int, filas: str) -> str:
    return (
        "% Tabla generada automaticamente desde la matriz de criterios del codigo.\n"
        "% No editar a mano; regenerar con genera_tabla_criterios.py (misma carpeta).\n"
        "{\\scriptsize\n"
        f"\\begin{{longtable}}{{{columnas_ancho}}}\n"
        "\\caption{Matriz de criterios estad\\'isticos de la aplicaci\\'on, "
        "generada autom\\'aticamente desde el m\\'odulo interno de criterios.}\n"
        "\\label{tab:matriz_criterios}\\\\\n"
        "\\toprule\n"
        f"{encabezados} \\\\\n"
        "\\midrule\n"
        "\\endfirsthead\n"
        f"\\multicolumn{{{n_cols}}}{{l}}{{\\emph{{Continuaci\\'on de la "
        "Tabla~\\ref{tab:matriz_criterios}}}\\\\\n"
        "\\toprule\n"
        f"{encabezados} \\\\\n"
        "\\midrule\n"
        "\\endhead\n"
        "\\bottomrule\n"
        "\\endlastfoot\n"
        + filas + "\n\\end{longtable}\n}\n"
    )


#: Traduccion del identificador interno del campo `tipo` al vocabulario que se
#: publica en el CUERPO de la tesis. 17-08-2026, cierre documental.
#:
#: Los identificadores del codigo son etiquetas de inventario: sirven para
#: auditar y para que una prueba pueda comprobarlas, pero leidos por un jurado
#: no dicen lo que significan -«muerto» sugiere codigo roto cuando lo que indica
#: es que la constante existe y NO decide nada- y ademas son cadenas largas sin
#: punto de corte natural que desbordaban las columnas estrechas.
#:
#: La traduccion se aplica SOLO a la version de la tesis. El anexo tecnico de
#: auditoria conserva el identificador crudo junto al ID y a la ruta de
#: implementacion, que es donde la trazabilidad literal si es util.
TIPO_PUBLICADO = {
    "bibliografico": "bibliográfico",
    "derivacion_matematica": "derivación matemática",
    "operativo_tecnico": "operativo técnico",
    "operativo_interno_sin_sustento": "operativo interno, sin fuente externa",
    "muerto": "sin efecto decisorio",
    "experimental": "evaluado, no adoptado",
    "pendiente_de_decision": "pendiente de decisión",
}


def tipo_publicado(tipo: object) -> str:
    """Etiqueta academica del tipo; un tipo nuevo se publica tal cual."""
    return TIPO_PUBLICADO.get(str(tipo), str(tipo))


# --- Versión publicada en la tesis: sin identificador interno ni ruta ---------
filas_tesis = "\n".join(
    f"{esc(c.criterio)} & {esc(tipo_publicado(c.tipo))} & {esc(c.valor)} & {esc(c.fuente)} \\\\"
    for c in matriz_criterios()
)
# Las fracciones NO deben sumar 1,0: con `@{}` en los extremos quedan (k-1)
# separaciones internas de 2*tabcolsep = 12pt cada una, que se suman al ancho
# total. Sumar 1,0 desbordaba la caja en exactamente (k-1)*12pt -36pt en la
# tabla de cuatro columnas y 60pt en la de seis- y la tabla invadia el margen
# derecho. Se reserva ese espacio descontandolo de las fracciones.
cols_tesis = (
    "@{}"
    ">{\\raggedright\\arraybackslash}p{0.238\\linewidth}"
    ">{\\raggedright\\arraybackslash}p{0.152\\linewidth}"
    ">{\\raggedright\\arraybackslash}p{0.266\\linewidth}"
    ">{\\raggedright\\arraybackslash}p{0.295\\linewidth}@{}"
)
enc_tesis = ("\\textbf{Criterio} & \\textbf{Tipo} & \\textbf{Valor o umbral} & "
             "\\textbf{Sustento}")

# --- Versión del anexo técnico de auditoría: incluye ID e implementación ------
filas_audit = "\n".join(
    f"{esc(c.id)} & {esc(c.criterio)} & {esc(c.tipo)} & {esc(c.valor)} & "
    f"{esc(c.fuente)} & {esc(c.ubicacion)} \\\\"
    for c in matriz_criterios()
)
cols_audit = (
    "@{}"
    ">{\\raggedright\\arraybackslash}p{0.067\\linewidth}"
    ">{\\raggedright\\arraybackslash}p{0.153\\linewidth}"
    ">{\\raggedright\\arraybackslash}p{0.105\\linewidth}"
    ">{\\raggedright\\arraybackslash}p{0.182\\linewidth}"
    ">{\\raggedright\\arraybackslash}p{0.20\\linewidth}"
    ">{\\raggedright\\arraybackslash}p{0.22\\linewidth}@{}"
)
enc_audit = ("\\textbf{ID} & \\textbf{Criterio} & \\textbf{Tipo} & "
             "\\textbf{Valor o umbral} & \\textbf{Sustento} & \\textbf{Implementaci\\'on}")

RAIZ_TEX = RAIZ / "documentacion_latex"
(RAIZ_TEX / "criterios_estadisticos_aplicacion" / "tabla_criterios.tex").write_text(
    _tabla(cols_audit, enc_audit, 6, filas_audit), encoding="utf-8")
(RAIZ_TEX / "documento_tecnico_icociv_iccp" / "tabla_criterios_auditable.tex").write_text(
    _tabla(cols_tesis, enc_tesis, 4, filas_tesis), encoding="utf-8")
print("filas:", len(matriz_criterios()), "| tesis: 4 columnas | anexo auditoria: 6 columnas")
