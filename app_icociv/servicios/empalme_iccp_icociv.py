"""Cálculo de actualización de precios con empalme ICCP -> ICOCIV."""

from __future__ import annotations

import json
import math
import re
import unicodedata
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from app_icociv.config.rutas import ruta_recurso


PERIODO_TRANSICION = "2021_12"
# Recurso interno de solo lectura: debe resolverse via ruta_recurso para que
# funcione tanto desde codigo fuente como desde el ejecutable empaquetado.
RUTA_ICCP_JSON = ruta_recurso("app_icociv/datos/iccp_historico.json")
TIPOS_SERIE_ICCP = {
    "total_iccp": "Total ICCP",
    "canasta_general": "Canasta general",
    "grupo_obra": "Grupo de obra",
}
SERIES_CANASTA_GENERAL = {
    "costos indirectos",
    "equipos",
    "mano de obra",
    "materiales",
    "transporte",
}

MESES = {
    "enero": 1,
    "ene": 1,
    "febrero": 2,
    "feb": 2,
    "marzo": 3,
    "mar": 3,
    "abril": 4,
    "abr": 4,
    "mayo": 5,
    "may": 5,
    "junio": 6,
    "jun": 6,
    "julio": 7,
    "jul": 7,
    "agosto": 8,
    "ago": 8,
    "septiembre": 9,
    "setiembre": 9,
    "sep": 9,
    "octubre": 10,
    "oct": 10,
    "noviembre": 11,
    "nov": 11,
    "diciembre": 12,
    "dic": 12,
}


def cargar_iccp_historico() -> dict[str, dict[str, float]]:
    """Devuelve los índices ICCP históricos internos por grupo y periodo."""
    return _cargar_payload_iccp()["grupos"]


def grupos_iccp() -> list[str]:
    """Lista de grupos ICCP disponibles para selección."""
    return sorted(cargar_iccp_historico())


def series_iccp_por_tipo(datos_iccp: dict[str, dict[str, float]] | None = None) -> dict[str, list[str]]:
    grupos = datos_iccp or cargar_iccp_historico()
    total = [nombre for nombre in grupos if _normalizar_texto(nombre) == "total iccp"]
    canasta = [nombre for nombre in grupos if _normalizar_texto(nombre) in SERIES_CANASTA_GENERAL]
    excluidas = set(total) | set(canasta)
    return {
        "total_iccp": total,
        "canasta_general": canasta,
        "grupo_obra": [nombre for nombre in grupos if nombre not in excluidas],
    }


def obtener_indice_iccp(
    fecha: Any,
    grupo_iccp: str,
    datos_iccp: dict[str, dict[str, float]] | None = None,
) -> float:
    """Busca un índice ICCP sin permitir periodos posteriores a 2021_12."""
    periodo = normalizar_periodo_empalme(fecha)
    if _clave_periodo(periodo) > _clave_periodo(PERIODO_TRANSICION):
        raise ValueError("El ICCP solo está disponible hasta diciembre de 2021.")
    datos = datos_iccp or cargar_iccp_historico()
    if grupo_iccp not in datos:
        raise ValueError(f"No existe el grupo ICCP seleccionado: {grupo_iccp}.")
    try:
        return _numero_finito(datos[grupo_iccp][periodo], f"ICCP {grupo_iccp} {periodo}")
    except KeyError as exc:
        raise ValueError(f"No existe índice ICCP para {grupo_iccp} en {periodo}.") from exc


def obtener_indice_icociv(fecha: Any, indices_icociv: dict[str, Any]) -> float:
    """Busca un índice ICOCIV en la serie seleccionada por el usuario."""
    periodo = normalizar_periodo_empalme(fecha)
    serie = {normalizar_periodo_empalme(k): v for k, v in (indices_icociv or {}).items()}
    try:
        return _numero_finito(serie[periodo], f"ICOCIV {periodo}")
    except KeyError as exc:
        raise ValueError(f"No existe índice ICOCIV para el periodo {periodo} en la ruta seleccionada.") from exc


def validar_fechas_empalme(fecha_inicial: Any, fecha_final: Any) -> tuple[str, str]:
    """Normaliza y valida el rango mensual del empalme."""
    inicial = normalizar_periodo_empalme(fecha_inicial)
    final = normalizar_periodo_empalme(fecha_final)
    if _clave_periodo(inicial) > _clave_periodo(final):
        raise ValueError("La fecha inicial no puede ser posterior a la fecha final.")
    return inicial, final


def calcular_empalme_iccp_icociv(
    entrada: dict[str, Any],
    indices_icociv: dict[str, Any],
    datos_iccp: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    """Calcula empalme general o acero según el campo ``calculo_acero``."""
    if entrada.get("calculo_acero"):
        return calcular_empalme_acero(entrada, indices_icociv, datos_iccp)
    return calcular_empalme_general(entrada, indices_icociv, datos_iccp)


def calcular_empalme_general(
    entrada: dict[str, Any],
    indices_icociv: dict[str, Any],
    datos_iccp: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    """Calcula actualización general con ICCP, ICOCIV o empalme completo."""
    precio = _positivo(entrada.get("precio_base"), "precio base")
    anticipo = _numero_no_negativo(entrada.get("anticipo_amortizado", 0), "anticipo amortizado")
    base = precio - anticipo
    if base <= 0:
        raise ValueError("La base ajustable P - A debe ser mayor que cero.")
    return _calcular_base(
        entrada=entrada,
        base=base,
        precio_base=precio,
        anticipo=anticipo,
        indices_icociv=indices_icociv,
        datos_iccp=datos_iccp,
        tipo_calculo="general",
    )


def calcular_empalme_acero(
    entrada: dict[str, Any],
    indices_icociv: dict[str, Any],
    datos_iccp: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    """Calcula el caso especial de acero definido en los lineamientos."""
    p0 = _positivo(entrada.get("p0"), "P0")
    ix = _positivo_opcional(entrada.get("ix"), "Ix")
    q = _positivo_opcional(entrada.get("q"), "q")
    resultado = _calcular_base(
        entrada=entrada,
        base=p0,
        precio_base=p0,
        anticipo=0.0,
        indices_icociv=indices_icociv,
        datos_iccp=datos_iccp,
        tipo_calculo="acero",
    )
    valor_facturado = ix * q if ix is not None and q is not None else None
    resultado.update(
        {
            "p0": p0,
            "ix": ix,
            "q": q,
            "valor_facturado_total": valor_facturado,
            "z": valor_facturado - (resultado["r_total"] + p0) if valor_facturado is not None else None,
            "z_observacion": "" if valor_facturado is not None else "Para calcular Z debe ingresar Ix y q.",
            "tipo_calculo": "Cálculo especial acero",
        }
    )
    return resultado


def normalizar_periodo_empalme(valor: Any) -> str:
    """Acepta AAAA-MM, AAAA_M, fechas ISO o meses en español y devuelve AAAA_M."""
    if hasattr(valor, "year") and hasattr(valor, "month"):
        return _periodo(int(valor.year), int(valor.month))
    texto = str(valor or "").strip()
    if not texto:
        raise ValueError("Falta una fecha del análisis.")

    limpio = _sin_acentos(texto.lower()).replace("/", "_").replace("-", "_")
    partes = [p for p in re.split(r"[_\s]+", limpio) if p]
    if len(partes) >= 2 and partes[0].isdigit() and partes[1].isdigit():
        return _periodo(int(partes[0]), int(partes[1]))

    anio = re.search(r"\b(19|20)\d{2}\b", limpio)
    mes = next((numero for nombre, numero in MESES.items() if re.search(rf"\b{nombre}\b", limpio)), None)
    if anio and mes:
        return _periodo(int(anio.group(0)), mes)
    raise ValueError(f"Fecha no reconocida: {valor}. Use formato AAAA-MM o mes AAAA.")


def _calcular_base(
    entrada: dict[str, Any],
    base: float,
    precio_base: float,
    anticipo: float,
    indices_icociv: dict[str, Any],
    datos_iccp: dict[str, dict[str, float]] | None,
    tipo_calculo: str,
) -> dict[str, Any]:
    inicial, final = validar_fechas_empalme(entrada.get("fecha_inicial"), entrada.get("fecha_final"))
    caso = _caso_fechas(inicial, final)
    serie_iccp = _resolver_serie_iccp(entrada, datos_iccp)
    ruta_icociv = str(entrada.get("ruta_icociv") or "").strip()

    i0_iccp = i_iccp = factor_iccp = None
    i0_icociv = i_icociv = factor_icociv = None
    r1 = r2 = 0.0

    if caso in {"solo_iccp", "empalme_completo"}:
        if not serie_iccp["serie_iccp"]:
            raise ValueError("Debe seleccionar una serie ICCP válida.")
        i0_iccp = obtener_indice_iccp(inicial, serie_iccp["serie_iccp"], datos_iccp)
        i_iccp = obtener_indice_iccp(final if caso == "solo_iccp" else PERIODO_TRANSICION, serie_iccp["serie_iccp"], datos_iccp)
        factor_iccp = _factor(i_iccp, i0_iccp, "ICCP")
        r1 = base * (factor_iccp - 1.0)

    if caso in {"solo_icociv", "empalme_completo"}:
        if not ruta_icociv:
            raise ValueError("Debe seleccionar una ruta ICOCIV.")
        i0_icociv = obtener_indice_icociv(inicial if caso == "solo_icociv" else PERIODO_TRANSICION, indices_icociv)
        i_icociv = obtener_indice_icociv(final, indices_icociv)
        factor_icociv = _factor(i_icociv, i0_icociv, "ICOCIV")
        r2 = (base + r1) * (factor_icociv - 1.0)

    r_total = r1 + r2
    valor_actualizado = base + r_total
    diferencia_porcentual = (r_total / base) * 100.0
    tipo_visible = "general" if tipo_calculo == "general" else "Cálculo especial acero"
    resultado = {
        "tipo_calculo": tipo_visible,
        "caso": caso,
        "item": entrada.get("item", ""),
        "insumo": entrada.get("insumo", entrada.get("item", "")),
        "codigo_item": entrada.get("codigo_item", ""),
        "unidad": entrada.get("unidad", ""),
        "cantidad": _numero_opcional(entrada.get("cantidad")),
        "precio_base": precio_base,
        "anticipo_amortizado": anticipo,
        "base_ajustable": base,
        "fecha_inicial": inicial,
        "fecha_final": final,
        **serie_iccp,
        "ruta_iccp": serie_iccp["ruta_iccp_completa"],
        "i0_iccp": i0_iccp,
        "i_iccp": i_iccp,
        "factor_iccp": factor_iccp,
        "r1": r1,
        "ruta_icociv": ruta_icociv,
        "i0_icociv": i0_icociv,
        "i_icociv": i_icociv,
        "factor_icociv": factor_icociv,
        "r2": r2,
        "r_total": r_total,
        "valor_actualizado": valor_actualizado,
        "diferencia_absoluta": r_total,
        "diferencia_porcentual": diferencia_porcentual,
        "observacion_tecnica": entrada.get("observacion_tecnica", ""),
        "fecha_calculo": datetime.now().isoformat(timespec="seconds"),
    }
    resultado["trazabilidad_formula"] = _trazabilidad(resultado)
    return resultado


def _resolver_serie_iccp(
    entrada: dict[str, Any],
    datos_iccp: dict[str, dict[str, float]] | None,
) -> dict[str, str]:
    canasta = str(entrada.get("canasta_general_iccp") or "").strip()
    grupo = str(entrada.get("grupo_obra_iccp") or "").strip()
    if canasta and grupo:
        raise ValueError("Seleccione solo una serie ICCP: Canasta general o Grupo de obra, no ambas.")

    tipo = str(entrada.get("tipo_serie_iccp") or "").strip()
    serie = str(entrada.get("serie_iccp") or entrada.get("grupo_iccp") or canasta or grupo or "").strip()
    disponibles = series_iccp_por_tipo(datos_iccp)
    if not tipo and serie:
        tipo = next((clave for clave, series in disponibles.items() if serie in series), "grupo_obra")
    if canasta:
        tipo = "total_iccp" if canasta in disponibles["total_iccp"] else "canasta_general"
        serie = canasta
    if grupo:
        tipo, serie = "grupo_obra", grupo

    tipo_visible = TIPOS_SERIE_ICCP.get(tipo, "")
    if not tipo_visible:
        raise ValueError("Seleccione un tipo de serie ICCP válido.")
    if serie not in disponibles.get(tipo, []):
        raise ValueError(f"La serie ICCP '{serie}' no pertenece a {tipo_visible}.")
    return {
        "tipo_serie_iccp": tipo,
        "tipo_serie_iccp_visible": tipo_visible,
        "serie_iccp": serie,
        "codigo_serie_iccp": "",
        "nombre_serie_iccp": serie,
        "ruta_iccp_completa": serie if tipo == "total_iccp" else f"{tipo_visible} > {serie}",
    }


def _caso_fechas(inicial: str, final: str) -> str:
    transicion = _clave_periodo(PERIODO_TRANSICION)
    ini = _clave_periodo(inicial)
    fin = _clave_periodo(final)
    if ini <= transicion < fin:
        return "empalme_completo"
    if fin <= transicion:
        return "solo_iccp"
    return "solo_icociv"


def _trazabilidad(r: dict[str, Any]) -> str:
    lineas = [f"Base = P - A = {r['base_ajustable']:.6f}"]
    if r["factor_iccp"] is not None:
        lineas.append(
            f"R1 = Base * [(I_ICCP/I0_ICCP)-1] = {r['base_ajustable']:.6f} "
            f"* [({r['i_iccp']:.6f}/{r['i0_iccp']:.6f})-1] = {r['r1']:.6f}"
        )
    if r["factor_icociv"] is not None:
        lineas.append(
            f"R2 = (Base + R1) * [(I_ICOCIV/I0_ICOCIV)-1] = "
            f"({r['base_ajustable']:.6f} + {r['r1']:.6f}) "
            f"* [({r['i_icociv']:.6f}/{r['i0_icociv']:.6f})-1] = {r['r2']:.6f}"
        )
    lineas.append(f"R = R1 + R2 = {r['r_total']:.6f}")
    lineas.append(f"Valor actualizado = Base + R = {r['valor_actualizado']:.6f}")
    return "\n".join(lineas)


@lru_cache(maxsize=1)
def _cargar_payload_iccp() -> dict[str, Any]:
    return json.loads(RUTA_ICCP_JSON.read_text(encoding="utf-8"))


def _numero_finito(valor: Any, campo: str) -> float:
    try:
        numero = float(valor)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"El valor de {campo} no es numérico.") from exc
    if not math.isfinite(numero):
        raise ValueError(f"El valor de {campo} no es válido.")
    return numero


def _positivo(valor: Any, campo: str) -> float:
    numero = _numero_finito(valor, campo)
    if numero <= 0:
        raise ValueError(f"El {campo} debe ser mayor que cero.")
    return numero


def _positivo_opcional(valor: Any, campo: str) -> float | None:
    if valor in (None, ""):
        return None
    numero = _numero_finito(valor, campo)
    if numero == 0:
        return None
    if numero < 0:
        raise ValueError(f"El {campo} no puede ser negativo.")
    return numero


def _numero_no_negativo(valor: Any, campo: str) -> float:
    numero = _numero_finito(0 if valor in (None, "") else valor, campo)
    if numero < 0:
        raise ValueError(f"El {campo} no puede ser negativo.")
    return numero


def _numero_opcional(valor: Any) -> float | None:
    if valor in (None, ""):
        return None
    return _numero_finito(valor, "cantidad")


def _factor(indice: float, indice_base: float, etiqueta: str) -> float:
    if indice_base == 0:
        raise ValueError(f"I0 {etiqueta} no puede ser cero.")
    return indice / indice_base


def _periodo(anio: int, mes: int) -> str:
    if not 1 <= mes <= 12:
        raise ValueError("El mes debe estar entre 1 y 12.")
    return f"{anio}_{mes}"


def _clave_periodo(periodo: str) -> tuple[int, int]:
    anio, mes = normalizar_periodo_empalme(periodo).split("_")
    return int(anio), int(mes)


def _sin_acentos(texto: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFD", texto)
        if unicodedata.category(char) != "Mn"
    )


def _normalizar_texto(texto: str) -> str:
    return re.sub(r"\s+", " ", _sin_acentos(texto).casefold()).strip()
