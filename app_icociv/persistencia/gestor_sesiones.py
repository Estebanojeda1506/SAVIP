"""Persistencia local opcional de sesiones ICOCIV en JSON."""

from __future__ import annotations

import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from app_icociv.utilidades.nomenclatura_icociv import ruta_sin_tabla


CARACTERES_INVALIDOS = r'\/:*?"<>|'


def sanitizar_nombre_archivo(nombre: str, reemplazo: str = "_") -> str:
    """Elimina caracteres no seguros para nombres de archivo en Windows."""
    limpio = re.sub(rf"[{re.escape(CARACTERES_INVALIDOS)}]", reemplazo, str(nombre))
    limpio = re.sub(r"\s+", "_", limpio.strip())
    limpio = re.sub(r"_+", "_", limpio)
    return limpio.strip("._ ") or "sesion_icociv"


def _texto_corto(valor: Any, maximo: int = 48) -> str:
    texto = "" if valor is None else str(valor)
    texto = texto.strip()
    if len(texto) > maximo:
        return texto[:maximo].rstrip()
    return texto


def generar_nombre_sesion(
    usuario: str,
    ruta_jerarquica: list[dict[str, str]] | None,
    periodo_proyectado: str,
    fecha: datetime | None = None,
) -> str:
    """Genera un nombre descriptivo para una sesión JSON."""
    fecha = fecha or datetime.now()
    ruta_jerarquica = ruta_sin_tabla(ruta_jerarquica)

    primer_nivel = ruta_jerarquica[0]["valor"] if ruta_jerarquica else "analisis"
    ultimo_nivel = ruta_jerarquica[-1]["valor"] if ruta_jerarquica else "icociv"

    partes = [
        _texto_corto(usuario, 32),
        _texto_corto(primer_nivel),
        _texto_corto(ultimo_nivel),
        periodo_proyectado,
        fecha.strftime("%Y-%m-%d_%H%M"),
    ]
    return sanitizar_nombre_archivo("_".join(filter(None, partes))) + ".json"


def _convertir_json_seguro(valor: Any) -> Any:
    """Convierte estructuras comunes a tipos JSON sin serializacion binaria."""
    if isinstance(valor, Path):
        return str(valor)
    if isinstance(valor, datetime):
        return valor.isoformat(timespec="seconds")
    if isinstance(valor, float) and not math.isfinite(valor):
        return None
    if isinstance(valor, dict):
        return {str(k): _convertir_json_seguro(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_convertir_json_seguro(v) for v in valor]
    if hasattr(valor, "item"):
        try:
            return valor.item()
        except Exception:
            pass
    return valor


def guardar_sesion(ruta_salida: str | Path, datos_sesion: dict[str, Any]) -> Path:
    """Guarda una sesión en JSON local y devuelve la ruta final."""
    ruta = Path(ruta_salida)
    if ruta.suffix.lower() != ".json":
        ruta = ruta.with_suffix(".json")
    ruta.parent.mkdir(parents=True, exist_ok=True)

    datos = _convertir_json_seguro(datos_sesion)
    datos.setdefault("fecha_guardado", datetime.now().isoformat(timespec="seconds"))

    with ruta.open("w", encoding="utf-8") as archivo:
        json.dump(datos, archivo, ensure_ascii=False, indent=2, allow_nan=False)
    return ruta


def cargar_sesion(ruta_sesion: str | Path) -> dict[str, Any]:
    """Carga una sesión JSON previamente guardada."""
    ruta = Path(ruta_sesion)
    with ruta.open("r", encoding="utf-8") as archivo:
        return json.load(archivo)


def listar_sesiones(carpeta_sesiones: str | Path) -> list[Path]:
    """Lista sesiones JSON locales ordenadas por fecha de modificación."""
    carpeta = Path(carpeta_sesiones)
    if not carpeta.exists():
        return []
    return sorted(
        carpeta.glob("*.json"),
        key=lambda ruta: ruta.stat().st_mtime,
        reverse=True,
    )
