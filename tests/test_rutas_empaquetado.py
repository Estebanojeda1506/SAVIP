"""Pruebas del módulo de rutas usado por el empaquetado.

Protegen las invariantes que hacen que el ejecutable funcione: los recursos
internos deben resolverse tanto desde código fuente como congelados, y las
salidas deben escribirse siempre FUERA de la carpeta interna del ejecutable.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_icociv.config import rutas


RECURSOS_INTERNOS = (
    "app_icociv/datos/iccp_historico.json",
    "app_icociv/interfaz/tema/plantilla.qss",
)


def test_recursos_internos_existen_desde_codigo_fuente() -> None:
    for relativa in RECURSOS_INTERNOS:
        assert rutas.ruta_recurso(relativa).is_file(), f"Falta el recurso {relativa}"


def test_version_se_lee_del_archivo_unico() -> None:
    """La versión debe venir del archivo VERSIÓN, sin duplicarse en el código."""
    esperada = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert esperada, "El archivo VERSIÓN esta vacio."
    assert rutas.version_aplicacion() == esperada
    assert rutas.VERSION == esperada


def test_ruta_recurso_congelado_usa_meipass(monkeypatch=None) -> None:
    """Congelado, los recursos se buscan en _MEIPASS y no junto al código."""
    original_frozen = getattr(sys, "frozen", None)
    original_meipass = getattr(sys, "_MEIPASS", None)
    try:
        sys.frozen = True  # type: ignore[attr-defined]
        sys._MEIPASS = r"C:\ruta\simulada\_internal"  # type: ignore[attr-defined]
        resuelta = rutas.ruta_recurso("app_icociv/datos/iccp_historico.json")
        assert str(resuelta).startswith(r"C:\ruta\simulada\_internal")
        assert rutas.es_ejecutable_congelado() is True
    finally:
        if original_frozen is None:
            delattr(sys, "frozen")
        else:
            sys.frozen = original_frozen  # type: ignore[attr-defined]
        if original_meipass is None:
            if hasattr(sys, "_MEIPASS"):
                delattr(sys, "_MEIPASS")
        else:
            sys._MEIPASS = original_meipass  # type: ignore[attr-defined]


def test_salidas_nunca_dentro_del_bundle() -> None:
    """Reportes, sesiones y logs deben quedar fuera de _MEIPASS/_internal.

    Es la invariante crítica del empaquetado: escribir dentro del bundle
    fallaría en Program Files (solo lectura) y se perdería en modo onefile.
    """
    original_frozen = getattr(sys, "frozen", None)
    original_meipass = getattr(sys, "_MEIPASS", None)
    bundle = Path(r"C:\ruta\simulada\_internal")
    try:
        sys.frozen = True  # type: ignore[attr-defined]
        sys._MEIPASS = str(bundle)  # type: ignore[attr-defined]

        for destino in (rutas.carpeta_datos_usuario(), rutas.carpeta_logs()):
            assert bundle not in destino.parents, f"{destino} quedaria dentro del bundle"
            assert str(destino) != str(bundle)
        # La carpeta de datos de usuario debe llamarse SAVIP bajo el perfil.
        assert rutas.carpeta_datos_usuario().name == "SAVIP"
    finally:
        if original_frozen is None:
            delattr(sys, "frozen")
        else:
            sys.frozen = original_frozen  # type: ignore[attr-defined]
        if original_meipass is None:
            if hasattr(sys, "_MEIPASS"):
                delattr(sys, "_MEIPASS")
        else:
            sys._MEIPASS = original_meipass  # type: ignore[attr-defined]


def test_asegurar_carpeta_es_idempotente_y_no_lanza(tmp_path=None) -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        objetivo = Path(tmp) / "nivel1" / "nivel2"
        assert rutas.asegurar_carpeta(objetivo).is_dir()
        # Segunda llamada sobre una carpeta existente no debe fallar.
        assert rutas.asegurar_carpeta(objetivo).is_dir()


def test_spec_declara_los_recursos_internos() -> None:
    """El .spec debe empaquetar cada recurso que la aplicación resuelve."""
    spec = (ROOT / "packaging" / "SAVIP.spec").read_text(encoding="utf-8")
    assert "iccp_historico.json" in spec
    assert "plantilla.qss" in spec
    assert "VERSION" in spec
    # Defensa contra distribuciones infladas por librerías ajenas al proyecto.
    assert '"torch"' in spec


if __name__ == "__main__":
    for nombre, funcion in sorted(globals().items()):
        if nombre.startswith("test_") and callable(funcion):
            funcion()
            print(f"OK {nombre}")
    print("OK: rutas de empaquetado.")
