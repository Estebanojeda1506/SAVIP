"""
utilidades.py
Constantes globales y funciones de utilidad puras (sin dependencias de UI).
"""

import re
import math
import numpy as np
import pandas as pd

from app_icociv.estadistica.criterios import MIN_OBS_JARQUE_BERA

# ==============================
# CONSTANTES
# ==============================
ANIO_BASE: int = 2021
NOMBRE_HOJA: str = "Anexo 16"

MESES_ESPANOL: dict[str, int] = {
    "Enero": 1, "Febrero": 2, "Marzo": 3, "Abril": 4,
    "Mayo": 5, "Junio": 6, "Julio": 7, "Agosto": 8,
    "Septiembre": 9, "Octubre": 10, "Noviembre": 11, "Diciembre": 12,
}

# Columnas fijas por tabla (usadas en cargador_datos)
COLUMNAS_FIJAS_TABLAS: dict[str, list[str]] = {
    "A16":    ["Codigo_Grupos", "Grupos_Obra", "Ponderacion"],
    "A16.1":  ["Codigo_Grupos", "Cod_Subclases", "Cod_agreg_subc", "Subclases", "Ponderacion"],
    "A16.2":  ["Codigo_Grupos", "Cod_Subclases", "Cod_tip_obra", "cod_agreg_tip_obra", "Tip_obra", "Ponderacion"],
    "A16.3":  ["Codigo_Grupos", "Cod_Subclases", "Cod_tip_obra", "Tip_obra",
               "cod_agreg_niv_obra_cap", "Cod_Cap_const", "Cap_const", "Ponderacion"],
    "A16.6":  ["Codigo_Grupos", "Grupos_CPC", "Cod_Agreg_Grup_Costos", "Grupo_Costos", "Ponderacion_grupo_CPC"],
    "A16.7":  ["Codigo_Grupos", "Grupos_CPC", "Grupo_Costos", "Cod_insumo", "Insumos", "Ponderacion_grupo_CPC"],
    "A16.8":  ["Codigo_Grupos", "Cod_Subclases", "Cod_agreg_subc", "Subclases",
               "Cod_grupo_Costos", "Grupos_costos", "Ponderacion"],
    "A16.9":  ["Codigo_Grupos", "Cod_Subclases", "COD_Agreg_Subclase", "Subclase_CPC",
               "Grupo_Costos", "Cod_insumos", "Insumos", "Ponderacion_subclase"],
    "A16.10": ["Codigo_Grupos", "Cod_Subclases", "Cod_tip_obra", "cod_agreg_tip_obra", "Tip_obra",
               "Cod_Grupo_Costos", "Grupo_Costos", "Ponderacion_tip_obra"],
    "A16.11": ["Codigo_Grupos", "Cod_Subclases", "Cod_tip_obra", "cod_agreg_tip_obra", "Tip_obra",
               "Grupo_Costos", "Cod_Grupo_insumos", "Insumos", "Ponderacion_tip_obra"],
    "A16.12": ["Codigo_Grupos", "Cod_Subclases", "Cod_tip_obra", "Tip_obra",
               "cod_agreg_nivel_obra_capitulo", "Tip_obra_Cap_constr",
               "Cod_agreg_Grupo_Costos", "Grupo_Costos", "Ponderacion_tip_obra_Capconst"],
    "A16.13": ["Codigo_Grupos", "Cod_Subclases", "Cod_tip_obra", "Tip_obra",
               "cod_agreg_nivel_obra_capitulo", "Tip_obra_Cap_constr",
               "Grupo_Costos", "Cod_Insumos", "Insumos", "Ponderacion_tip_obra_Capconst"],
}


# ==============================
# HELPERS DE DETECCIÃ“N (internos al cargador_datos, pero reutilizables)
# ==============================

def parece_texto_encabezado(x: object) -> bool:
    if not isinstance(x, str):
        return False
    s = x.strip()
    if not s:
        return False
    return (
        s.startswith("A16") or
        ("CÃ³digo" in s) or
        ("PonderaciÃ³n" in s) or
        ("ICOCIV" in s) or
        ("Serie histÃ³rica" in s)
    )


def parece_codigo(x: object) -> bool:
    """Detecta si el primer campo parece un cÃ³digo de datos (no un header)."""
    if pd.isna(x):
        return False
    if isinstance(x, (int, float, np.integer, np.floating)):
        return True
    if isinstance(x, str):
        s = x.strip()
        if not s or parece_texto_encabezado(s):
            return False
        return bool(re.match(r"^\d+([._-]\d+)*(_\d+)?$", s))
    return False


# ==============================
# DETECCION DE PERIODOS REALES
# ==============================

_PERIOD_RE = re.compile(r"^\s*(\d{4})\s*[_/-]\s*(0?[1-9]|1[0-2])\s*$")


def normalizar_periodo(label: object) -> str | None:
    """
    Normaliza una etiqueta de periodo real del Excel.

    Ejemplos:
      2025_01  -> 2025_1
      2025_11  -> 2025_11
      2025/03  -> 2025_3

    Retorna None si la etiqueta no representa un periodo válido.
    """
    if isinstance(label, tuple):
        parts = [str(part).strip() for part in label if not pd.isna(part)]
        text = "_".join(parts)
    elif pd.isna(label):
        return None
    elif isinstance(label, pd.Timestamp):
        return f"{label.year}_{label.month}"
    else:
        text = str(label).strip()

    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    match = _PERIOD_RE.fullmatch(text)
    if not match:
        return None

    year = int(match.group(1))
    month = int(match.group(2))
    return f"{year}_{month}"


def clave_periodo(etiqueta_periodo: str) -> tuple[int, int]:
    """
    Clave de ordenamiento cronológico para etiquetas normalizadas YYYY_M.
    """
    normalized = normalizar_periodo(etiqueta_periodo)
    if normalized is None:
        raise ValueError(f"Periodo inválido: {etiqueta_periodo!r}")
    year, month = normalized.split("_")
    return int(year), int(month)


def detectar_columnas_periodo(columns) -> list[str]:
    """
    Detecta columnas de periodo reales presentes en el Excel.

    No infiere periodos por cantidad de columnas ni por nombre de archivo:
    solo acepta columnas cuyo encabezado real tenga forma YYYY_M o YYYY_MM.
    """
    periods: list[str] = []
    seen: set[str] = set()

    for col in columns:
        period = normalizar_periodo(col)
        if period is None or period in seen:
            continue
        periods.append(period)
        seen.add(period)

    return sorted(periods, key=clave_periodo)


# ==============================
# CONVERSIÃ“N PERIODO <-> t
# ==============================

def periodo_a_t(etiqueta_periodo: str, anio_base: int = ANIO_BASE) -> int:
    """Convierte etiqueta "2025_11 " â†’ entero t relativo a anio_base."""
    s = etiqueta_periodo.strip()
    y, m = s.split("_")
    return (int(y) - anio_base) * 12 + (int(m) - 1)


def t_a_periodo(t: int, anio_base: int = ANIO_BASE) -> str:
    """Convierte t relativo a anio_base â†’ etiqueta "2025_11"."""
    y = anio_base + (t // 12)
    m = (t % 12) + 1
    return f"{y}_{m}"


# ==============================
# FILTRADO DE DATAFRAMES
# ==============================

def filtrar_dataframe(
    df: pd.DataFrame,
    filtros: dict,
    dropna_col: str | None = None,
) -> pd.DataFrame:
    """
    Aplica filtros de igualdad sobre un DataFrame y opcionalmente
    descarta filas con NaN en dropna_col.

    Args:
        df: DataFrame de entrada.
        filtros: {columna: valor} a filtrar por igualdad.
        dropna_col: columna sobre la que se eliminan NaN (opcional).

    Returns:
        DataFrame filtrado con Ã­ndice reseteado.
    """
    out = df
    for col, val in filtros.items():
        out = out[out[col] == val]
    if dropna_col:
        out = out.dropna(subset=[dropna_col])
    return out.reset_index(drop=True)


# ==============================
# RESTRICCIÃ“N ECONÃ“MICA
# ==============================

def forzar_no_decreciente(y_predicha: np.ndarray) -> np.ndarray:
    """Fuerza que la serie predicha sea monÃ³tonamente no-decreciente."""
    out = y_predicha.copy()
    for i in range(1, len(out)):
        if out[i] < out[i - 1]:
            out[i] = out[i - 1]
    return out


# ==============================
# ESTADÃSTICOS AUXILIARES
# ==============================

def estadistico_jarque_bera(residuos: np.ndarray) -> tuple[float, float, float]:
    """Estadístico de Jarque-Bera con momentos centrales estándar.

    Devuelve ``(JB, asimetria, curtosis)``, o ``nan`` en los tres si el
    contraste no es calculable.

    La asimetría y la curtosis se calculan con **momentos centrales de divisor
    n**, que es la definición del contraste:

        m_k = (1/n) * sum (x - x_barra)^k
        S   = m_3 / m_2^(3/2)
        K   = m_4 / m_2^2
        JB  = (n/6) * (S^2 + (K-3)^2 / 4)

    Hasta la auditoría de julio de 2026 la implementación normalizaba con
    ``std(ddof=1)``, lo que encoge S y K por factores ``((n-1)/n)^(3/2)`` y
    ``((n-1)/n)^2`` y reduce JB. En un caso con n = 26 eso daba JB = 5,4328 y
    p = 0,0661 frente a los valores estándar JB = 6,4472 y p = 0,0398: la
    decisión al 5 % cambiaba de «no rechaza» a «rechaza» (hallazgo H-04).

    No es calculable con menos de ``MIN_OBS_JARQUE_BERA`` residuos ni con
    dispersión nula.
    """
    r = np.asarray(residuos, dtype=float)
    r = r[np.isfinite(r)]
    n = len(r)
    nan = float("nan")
    if n < MIN_OBS_JARQUE_BERA:
        return nan, nan, nan

    desviaciones = r - r.mean()
    m2 = float(np.mean(desviaciones ** 2))
    if m2 <= 0.0:
        return nan, nan, nan
    m3 = float(np.mean(desviaciones ** 3))
    m4 = float(np.mean(desviaciones ** 4))

    asimetria = m3 / (m2 ** 1.5)
    curtosis = m4 / (m2 ** 2)
    jb = (n / 6.0) * (asimetria ** 2 + ((curtosis - 3.0) ** 2) / 4.0)
    if not math.isfinite(jb):
        return nan, nan, nan
    return float(jb), float(asimetria), float(curtosis)


def valor_p_jarque_bera(residuos: np.ndarray) -> float:
    """Valor p del contraste Jarque-Bera bajo chi2 con 2 grados de libertad.

    La supervivencia de chi2(2) es exactamente ``exp(-JB/2)``, de modo que no
    hace falta scipy. Devuelve ``nan`` cuando el estadístico no es calculable.
    """
    jb, _, _ = estadistico_jarque_bera(residuos)
    if not math.isfinite(jb):
        return float("nan")
    return float(math.exp(-jb / 2.0))


def version_statsmodels() -> str:
    """Versión instalada de statsmodels, dependencia obligatoria."""
    import statsmodels

    return str(statsmodels.__version__)


def curtosis_exceso(residuos: np.ndarray) -> float:
    """Curtosis en exceso (Fisher) de los residuos."""
    r = residuos[~np.isnan(residuos)]
    if len(r) < 4:
        return 0.0
    mean = r.mean()
    s2 = float(np.mean((r - mean) ** 2))
    if s2 == 0:
        return 0.0
    kurt = float(np.mean((r - mean) ** 4)) / (s2 ** 2)
    return float(kurt - 3.0)


def aicc_desde_sse(sse: float, n: int, k: int) -> float:
    """AICc = nÂ·ln(SSE/n) + 2k + (2k(k+1))/(n-k-1)."""
    if n <= k + 2 or sse <= 0:
        return float("inf")
    aic = n * math.log(sse / n) + 2 * k
    corr = (2 * k * (k + 1)) / (n - k - 1)
    return float(aic + corr)
