"""
cargador_datos.py
Carga el archivo Excel del DANE (ICOCIV) y extrae todas las tablas A16.x
como DataFrames limpios, sin dependencia de interfaz gráfica.
"""

import io
import re
import numpy as np
import pandas as pd

from app_icociv.utilidades.utilidades import  (
    NOMBRE_HOJA,
    MESES_ESPANOL,
    COLUMNAS_FIJAS_TABLAS,
    parece_codigo,
    detectar_columnas_periodo,
    normalizar_periodo,
    clave_periodo,
)



# LECTURA CRUDA DEL EXCEL

def cargar_crudo(file_bytes: bytes, file_name: str) -> pd.DataFrame:
    """
    Lee la hoja 'Anexo 16' del Excel y devuelve el DataFrame crudo
    (sin encabezados, todas las celdas como valores).

    Args:
        file_bytes: contenido binario del archivo Excel.
        file_name: nombre del archivo (para detectar extensiÃ³n .xlsb).

    Returns:
        DataFrame crudo con header=None.

    Raises:
        RuntimeError: si falla la lectura de .xlsb por falta de pyxlsb.
        ValueError: si la hoja no existe o el formato no es soportado.
    """
    buf = io.BytesIO(file_bytes)
    if file_name.lower().endswith(".xlsb"):
        try:
            return pd.read_excel(buf, sheet_name=NOMBRE_HOJA, header=None, engine="pyxlsb")
        except ImportError as e:
            raise RuntimeError(
                "Error leyendo .xlsb. Instala pyxlsb: pip install pyxlsb"
            ) from e
    return pd.read_excel(buf, sheet_name=NOMBRE_HOJA, header=None)


# ==============================
# DETECCIÃ“N DE BLOQUES DENTRO DEL RAW
# ==============================

def _buscar_fila_titulo(raw: pd.DataFrame, table_tag: str) -> int | None:
    """
    Busca la fila donde aparece el tÃ­tulo de la tabla (ej. 'A16.1') en
    la primera columna.
    """
    if table_tag == "A16":
        pattern = re.compile(r"^A16\.\s", re.IGNORECASE)
    else:
        n = table_tag.replace("A16.", "")
        pattern = re.compile(rf"^A16\.{re.escape(n)}\b", re.IGNORECASE)

    for r in range(raw.shape[0]):
        v = raw.iat[r, 0]
        if isinstance(v, str) and pattern.search(v.strip()):
            return r
    return None


def _buscar_inicio_datos(
    raw: pd.DataFrame,
    approx_row: int,
    fixed_len: int,
    search_down: int = 80,
) -> int:
    """
    Busca la primera fila real de datos (cÃ³digo en la primera columna)
    a partir de approx_row.
    """
    max_r = min(raw.shape[0], approx_row + search_down)
    for r in range(approx_row, max_r):
        first = raw.iat[r, 0]
        if parece_codigo(first):
            anchor = raw.iloc[r, :fixed_len]
            if anchor.notna().any():
                return r
    # fallback menos estricto
    for r in range(approx_row, max_r):
        anchor = raw.iloc[r, :fixed_len]
        if anchor.notna().any():
            return r
    return approx_row


def _buscar_fin_tabla(
    raw: pd.DataFrame,
    start_row: int,
    fixed_len: int,
    blank_run: int = 3,
) -> int:
    """
    Detecta el fin de una tabla cuando aparecen N filas consecutivas
    con las columnas ancla vacÃ­as.
    """
    blanks = 0
    r = start_row
    while r < raw.shape[0]:
        anchor = raw.iloc[r, :fixed_len]
        if anchor.notna().any():
            blanks = 0
        else:
            blanks += 1
            if blanks >= blank_run:
                return r - blank_run
        r += 1
    return raw.shape[0] - 1


def _pares_periodo_desde_etiquetas(labels, fixed_len: int) -> list[tuple[int, str]]:
    """
    Devuelve pares (indice_columna, periodo_normalizado) detectados en una
    fila/lista de encabezados. Solo usa etiquetas reales YYYY_M / YYYY_MM.
    """
    pairs: list[tuple[int, str]] = []
    for col_idx, label in enumerate(labels):
        if col_idx < fixed_len:
            continue
        period = normalizar_periodo(label)
        if period is not None:
            pairs.append((col_idx, period))
    return pairs


def _anio_desde_encabezado(value: object) -> int | None:
    """
    Extrae un anio desde una celda de encabezado real, incluyendo celdas
    numéricas leidas desde Excel como 2025 o 2025.0.
    """
    if pd.isna(value):
        return None
    if isinstance(value, (int, np.integer)):
        year = int(value)
        return year if 1900 <= year <= 2100 else None
    if isinstance(value, (float, np.floating)) and float(value).is_integer():
        year = int(value)
        return year if 1900 <= year <= 2100 else None

    text = str(value).strip().replace("\xa0", " ")
    match = re.fullmatch(r"(19|20)\d{2}(?:\.0)?", text)
    if not match:
        return None
    return int(float(text))


def _mes_desde_encabezado(value: object) -> int | None:
    """
    Extrae el número de mes desde una celda real tipo 'Enero', 'Febrero', etc.
    """
    if not isinstance(value, str):
        return None
    text = value.strip().replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return MESES_ESPANOL.get(text)


def _deduplicar_y_ordenar_pares_periodo(pairs: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """
    Deduplica por periodo y ordena cronologicamente, preservando la columna
    real del primer encabezado encontrado para cada periodo.
    """
    by_period: dict[str, int] = {}
    for col_idx, period in pairs:
        by_period.setdefault(period, col_idx)
    return [
        (col_idx, period)
        for period, col_idx in sorted(by_period.items(), key=lambda item: clave_periodo(item[0]))
    ]


def _detectar_posiciones_periodo(
    raw: pd.DataFrame,
    heading_row: int,
    data_start: int,
    fixed_len: int,
    lookback: int = 20,
) -> list[tuple[int, str]]:
    """
    Detecta las columnas reales de periodo ubicadas en el encabezado de la
    tabla. Primero busca encabezados directos YYYY_M / YYYY_MM; si el Excel
    trae encabezados separados por anio y nombre de mes, reconstruye el
    periodo usando esas celdas reales, no por conteo.
    """
    header_start = max(heading_row + 1, data_start - lookback)
    header_end = data_start

    best_direct: list[tuple[int, str]] = []
    for row_idx in range(header_start, header_end):
        row = raw.iloc[row_idx, :]
        pairs = _pares_periodo_desde_etiquetas(row.tolist(), fixed_len)
        detected_periods = detectar_columnas_periodo(row.iloc[fixed_len:].tolist())
        if len(detected_periods) > len(best_direct):
            best_direct = pairs

    if best_direct:
        return _deduplicar_y_ordenar_pares_periodo(best_direct)

    best_from_months: list[tuple[int, str]] = []
    for month_row_idx in range(header_start, header_end):
        month_row = raw.iloc[month_row_idx, :]
        month_cells = [
            (col_idx, month)
            for col_idx in range(fixed_len, raw.shape[1])
            if (month := _mes_desde_encabezado(month_row.iloc[col_idx])) is not None
        ]
        if not month_cells:
            continue

        for year_row_idx in range(month_row_idx - 1, header_start - 1, -1):
            year_row = raw.iloc[year_row_idx, :].ffill()
            pairs: list[tuple[int, str]] = []
            for col_idx, month in month_cells:
                year = _anio_desde_encabezado(year_row.iloc[col_idx])
                if year is not None:
                    pairs.append((col_idx, f"{year}_{month}"))

            if len(pairs) > len(best_from_months):
                best_from_months = pairs

    if best_from_months:
        return _deduplicar_y_ordenar_pares_periodo(best_from_months)

    raise ValueError(
        "No se detectaron columnas de periodo reales en el encabezado de la tabla. "
        "Se esperaban etiquetas tipo '2025_1' / '2025_01' o encabezados de anio + mes."
    )


# ==============================
# EXTRACCIÃ“N DE UNA TABLA
# ==============================

def _extraer_tabla(
    raw: pd.DataFrame,
    table_tag: str,
    fixed_cols: list[str],
) -> tuple[pd.DataFrame, list[str]]:
    """
    Extrae el bloque de datos de una tabla A16.x del DataFrame crudo.

    Args:
        raw: DataFrame crudo de la hoja 'Anexo 16'.
        table_tag: identificador de tabla, ej. 'A16', 'A16.1', 'A16.10'.
        fixed_cols: nombres de las columnas fijas (no periodos).

    Returns:
        (df, periods) donde periods proviene de encabezados reales del Excel.

    Raises:
        ValueError: si no se encuentra el encabezado de la tabla.
    """
    fixed_len = len(fixed_cols)

    heading_row = _buscar_fila_titulo(raw, table_tag)
    if heading_row is None:
        raise ValueError(
            f"No se encontrÃ³ el encabezado de '{table_tag}' en la hoja '{NOMBRE_HOJA}'."
        )

    data_start = _buscar_inicio_datos(raw, heading_row + 1, fixed_len=fixed_len, search_down=120)
    period_pairs = _detectar_posiciones_periodo(
        raw,
        heading_row=heading_row,
        data_start=data_start,
        fixed_len=fixed_len,
    )
    periods = [period for _, period in period_pairs]
    selected_cols = list(range(fixed_len)) + [col_idx for col_idx, _ in period_pairs]

    end_row = _buscar_fin_tabla(raw, data_start, fixed_len=fixed_len, blank_run=3)

    block = raw.iloc[data_start: end_row + 1, selected_cols].copy()
    block = block[block.iloc[:, :fixed_len].notna().any(axis=1)].reset_index(drop=True)
    block.columns = fixed_cols + periods

    return block, periods


# ==============================
# CARGA COMPLETA (funciÃ³n pÃºblica principal)
# ==============================

def cargar_todas_tablas(
    file_bytes: bytes,
    file_name: str,
) -> tuple[dict[str, pd.DataFrame], list[str]]:
    """
    Lee el Excel del DANE y extrae todas las tablas A16.x.

    Args:
        file_bytes: contenido binario del archivo Excel.
        file_name: nombre del archivo (para detectar .xlsb).

    Returns:
        (tables, year_month) donde:
          - tables: dict con claves 'T_16', 'T_16_1', ..., 'T_16_13'
          - year_month: lista de etiquetas de periodos detectados, ej. ['2021_1', ...]

    Raises:
        RuntimeError / ValueError: ante errores de lectura o formato.
    """
    raw = cargar_crudo(file_bytes, file_name)

    # Cada tabla detecta sus periodos desde encabezados reales del Excel.
    T_16, year_month = _extraer_tabla(
        raw,
        "A16",
        COLUMNAS_FIJAS_TABLAS["A16"],
    )

    tables: dict[str, pd.DataFrame] = {"T_16": T_16}
    period_set: set[str] = set(year_month)

    tag_to_key = {
        "A16.1":  "T_16_1",
        "A16.2":  "T_16_2",
        "A16.3":  "T_16_3",
        "A16.6":  "T_16_6",
        "A16.7":  "T_16_7",
        "A16.8":  "T_16_8",
        "A16.9":  "T_16_9",
        "A16.10": "T_16_10",
        "A16.11": "T_16_11",
        "A16.12": "T_16_12",
        "A16.13": "T_16_13",
    }

    for tag, key in tag_to_key.items():
        df, table_periods = _extraer_tabla(
            raw,
            tag,
            COLUMNAS_FIJAS_TABLAS[tag],
        )
        tables[key] = df
        period_set.update(table_periods)

    year_month = sorted(period_set, key=clave_periodo)
    return tables, year_month
