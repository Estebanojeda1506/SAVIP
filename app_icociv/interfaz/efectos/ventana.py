"""Material de fondo de la ventana en Windows, con degradación segura.

Solo se usa la API documentada de DWM (`DwmSetWindowAttribute`) y únicamente en
Windows 11 22H2 (build 22621) o superior, donde `DWMWA_SYSTEMBACKDROP_TYPE`
existe oficialmente. Se descartó el atajo habitual para Windows 10
(`SetWindowCompositionAttribute`), que es una función no documentada y produce
parpadeos al redimensionar.

Si algo no está disponible la aplicación se ve exactamente igual salvo el fondo
de la ventana, que queda opaco. Nunca impide que la ventana abra.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

# Valores de DWMWINDOWATTRIBUTE documentados por Microsoft.
_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_SYSTEMBACKDROP_TYPE = 38

# DWM_SYSTEMBACKDROP_TYPE
_DWMSBT_AUTO = 0
_DWMSBT_NONE = 1
_DWMSBT_MAINWINDOW = 2  # Mica
_DWMSBT_TRANSIENTWINDOW = 3  # Acrylic
_DWMSBT_TABBEDWINDOW = 4  # Mica Alt

_BUILD_MINIMO_MICA = 22621


@dataclass(frozen=True)
class CapacidadesVentana:
    """Qué puede ofrecer el sistema operativo actual."""

    es_windows: bool
    build: int
    admite_material: bool
    admite_modo_oscuro_nativo: bool
    motivo: str

    def como_dict(self) -> dict[str, object]:
        return {
            "es_windows": self.es_windows,
            "build": self.build,
            "admite_material": self.admite_material,
            "admite_modo_oscuro_nativo": self.admite_modo_oscuro_nativo,
            "motivo": self.motivo,
        }


def _build_windows() -> int:
    try:
        return int(getattr(sys, "getwindowsversion")().build)
    except Exception:
        return 0


def detectar_capacidades() -> CapacidadesVentana:
    """Determina, sin efectos secundarios, qué se puede aplicar en este equipo."""
    if sys.platform != "win32":
        return CapacidadesVentana(False, 0, False, False, "El material de ventana solo existe en Windows.")
    build = _build_windows()
    if build >= _BUILD_MINIMO_MICA:
        return CapacidadesVentana(True, build, True, True, f"Windows 11 build {build}: Mica disponible.")
    if build >= 22000:
        return CapacidadesVentana(
            True, build, False, True,
            f"Windows 11 build {build}: anterior a 22H2, se usa fondo opaco.",
        )
    return CapacidadesVentana(
        True, build, False, build >= 18362,
        f"Windows 10 build {build}: sin API documentada de material, se usa fondo opaco.",
    )


def _aplicar_atributo(hwnd: int, atributo: int, valor: int) -> bool:
    try:
        import ctypes
        from ctypes import wintypes

        resultado = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            ctypes.c_uint(atributo),
            ctypes.byref(ctypes.c_int(int(valor))),
            ctypes.sizeof(ctypes.c_int),
        )
        return resultado == 0
    except Exception:
        return False


def aplicar_material(ventana, tema: str | None = "claro", activar: bool = True) -> bool:
    """Aplica Mica al fondo de la ventana. Devuelve si quedó aplicado.

    Requiere que la ventana tenga fondo translúcido para que el material se vea;
    de eso se encarga `preparar_ventana`. Un fallo se traduce en False, sin
    excepción, para que la interfaz siga su curso.
    """
    capacidades = detectar_capacidades()
    if not capacidades.admite_material:
        return False
    try:
        hwnd = int(ventana.winId())
    except Exception:
        return False

    es_oscuro = str(tema).strip().lower() == "oscuro"
    # El modo oscuro nativo tiñe el material y el marco de la ventana.
    _aplicar_atributo(hwnd, _DWMWA_USE_IMMERSIVE_DARK_MODE, 1 if es_oscuro else 0)
    backdrop = _DWMSBT_MAINWINDOW if activar else _DWMSBT_NONE
    return _aplicar_atributo(hwnd, _DWMWA_SYSTEMBACKDROP_TYPE, backdrop)


def sincronizar_modo_oscuro(ventana, tema: str | None) -> bool:
    """Ajusta solo el marco nativo al tema; útil aunque no haya Mica."""
    capacidades = detectar_capacidades()
    if not capacidades.admite_modo_oscuro_nativo:
        return False
    try:
        hwnd = int(ventana.winId())
    except Exception:
        return False
    es_oscuro = str(tema).strip().lower() == "oscuro"
    return _aplicar_atributo(hwnd, _DWMWA_USE_IMMERSIVE_DARK_MODE, 1 if es_oscuro else 0)


def alto_contraste_activo() -> bool:
    """True si Windows está en modo de alto contraste.

    En ese caso la interfaz debe priorizar legibilidad: sin sombras, sin
    transparencias y con los colores del sistema mandando sobre los propios.
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        class HIGHCONTRAST(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.UINT),
                ("dwFlags", wintypes.DWORD),
                ("lpszDefaultScheme", wintypes.LPWSTR),
            ]

        SPI_GETHIGHCONTRAST = 0x0042
        HCF_HIGHCONTRASTON = 0x00000001
        info = HIGHCONTRAST()
        info.cbSize = ctypes.sizeof(HIGHCONTRAST)
        ok = ctypes.windll.user32.SystemParametersInfoW(
            SPI_GETHIGHCONTRAST, ctypes.sizeof(HIGHCONTRAST), ctypes.byref(info), 0
        )
        return bool(ok) and bool(info.dwFlags & HCF_HIGHCONTRASTON)
    except Exception:
        return False


def preparar_ventana(ventana, tema: str | None = "claro") -> dict[str, object]:
    """Configura el fondo de la ventana según lo que admita el equipo.

    Devuelve el resultado para que la interfaz pueda registrarlo y para que las
    pruebas comprueben la degradación sin depender del sistema operativo.
    """
    capacidades = detectar_capacidades()
    alto_contraste = alto_contraste_activo()
    resultado: dict[str, object] = {
        **capacidades.como_dict(),
        "alto_contraste": alto_contraste,
        "material_aplicado": False,
        "modo_oscuro_nativo": False,
    }

    if alto_contraste:
        resultado["motivo"] = "Modo de alto contraste activo: se prioriza la legibilidad."
        return resultado

    resultado["modo_oscuro_nativo"] = sincronizar_modo_oscuro(ventana, tema)
    if capacidades.admite_material:
        resultado["material_aplicado"] = aplicar_material(ventana, tema, activar=True)
    return resultado


__all__ = [
    "CapacidadesVentana",
    "alto_contraste_activo",
    "aplicar_material",
    "detectar_capacidades",
    "preparar_ventana",
    "sincronizar_modo_oscuro",
]
