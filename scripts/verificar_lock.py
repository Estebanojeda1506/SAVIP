"""Verifica que el interprete activo reproduce exactamente requirements-lock.txt.

Correccion RA-02 de la reauditoria de ``0.3.0-rc2``: el ejecutable se construia
desde ``requirements.txt``, que solo fija statsmodels, y el binario resultante
llevaba pandas, numpy, scipy, scikit-learn y matplotlib en versiones distintas
de las del entorno reproducible. Que la autocomprobacion pasara no demostraba
identidad con el entorno congelado.

Este guion es la barrera previa a PyInstaller: compara version a version, deja
las 32 en el registro y **aborta** ante cualquier diferencia, ausencia o
paquete adicional inesperado.

Uso:

    python scripts/verificar_lock.py [--lock requirements-lock.txt] [--json SALIDA.json]

Codigos de salida:

    0   el entorno reproduce el lock exactamente
    1   falta una version, difiere o el lock no se pudo leer
"""
from __future__ import annotations

import argparse
import json
import sys
from importlib import metadata
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

#: Herramientas de compilacion y de empaquetado que no forman parte del
#: entorno de ejecucion declarado. Su presencia en `.venv-build` es esperada y
#: no constituye una desviacion del lock.
TOLERADOS_DE_COMPILACION = {
    "pyinstaller",
    "pyinstaller-hooks-contrib",
    "altgraph",
    "pefile",
    "pywin32",
    "pywin32-ctypes",
    "setuptools",
    "wheel",
    "pip",
}


def normalizar(nombre: str) -> str:
    """Nombre canonico de distribucion: minusculas y guiones (PEP 503)."""
    return nombre.strip().lower().replace("_", "-")


def leer_lock(ruta: Path) -> dict[str, str]:
    """Pares nombre->version del lock, ignorando comentarios y lineas vacias."""
    fijadas: dict[str, str] = {}
    for linea in ruta.read_text(encoding="utf-8-sig").splitlines():
        texto = linea.split("#", 1)[0].strip()
        if not texto:
            continue
        if "==" not in texto:
            raise ValueError(f"El lock debe fijar versiones exactas; linea suelta: {linea!r}")
        nombre, version = texto.split("==", 1)
        fijadas[normalizar(nombre)] = version.strip()
    if not fijadas:
        raise ValueError(f"El lock {ruta} no declara ninguna version.")
    return fijadas


def instaladas() -> dict[str, str]:
    return {
        normalizar(dist.metadata["Name"]): dist.version
        for dist in metadata.distributions()
        if dist.metadata.get("Name")
    }


def comparar(lock: dict[str, str], presentes: dict[str, str]) -> dict[str, list]:
    faltantes, distintas, coinciden = [], [], []
    for nombre, esperada in sorted(lock.items()):
        actual = presentes.get(nombre)
        if actual is None:
            faltantes.append({"paquete": nombre, "esperada": esperada})
        elif actual != esperada:
            distintas.append({"paquete": nombre, "esperada": esperada, "instalada": actual})
        else:
            coinciden.append({"paquete": nombre, "version": actual})
    adicionales = [
        {"paquete": nombre, "instalada": version}
        for nombre, version in sorted(presentes.items())
        if nombre not in lock and nombre not in TOLERADOS_DE_COMPILACION
    ]
    return {
        "coinciden": coinciden,
        "faltantes": faltantes,
        "distintas": distintas,
        "adicionales": adicionales,
    }


#: Paquetes que la reauditoria comparo explicitamente y que se listan aparte
#: en el registro, para que la evidencia sea directamente contrastable.
COMPARACION_EXIGIDA = (
    "pandas", "numpy", "scipy", "scikit-learn", "matplotlib", "statsmodels",
    "pyside6", "reportlab", "python-docx", "openpyxl", "pyxlsb",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", default=str(RAIZ / "requirements-lock.txt"))
    parser.add_argument("--json", default="")
    args = parser.parse_args()

    ruta = Path(args.lock)
    try:
        lock = leer_lock(ruta)
    except (OSError, ValueError) as exc:
        print(f"ERROR: no se pudo leer el lock: {exc}", file=sys.stderr)
        return 1

    presentes = instaladas()
    informe = comparar(lock, presentes)
    informe["lock"] = str(ruta)
    informe["python"] = sys.version.split()[0]
    informe["ejecutable"] = sys.executable
    informe["esperados"] = len(lock)
    informe["verificado"] = not (
        informe["faltantes"] or informe["distintas"] or informe["adicionales"]
    )

    print(f"Lock: {ruta}")
    print(f"Interprete: {sys.executable} (Python {informe['python']})")
    print(f"Paquetes fijados: {len(lock)}   coinciden: {len(informe['coinciden'])}")
    print("\n-- Versiones exactas del entorno de compilacion --")
    for fila in informe["coinciden"]:
        print(f"  OK  {fila['paquete']}=={fila['version']}")

    print("\n-- Comparacion exigida por la reauditoria --")
    for nombre in COMPARACION_EXIGIDA:
        clave = normalizar(nombre)
        esperada = lock.get(clave, "no fijado")
        actual = presentes.get(clave, "AUSENTE")
        marca = "OK " if esperada == actual else "!! "
        print(f"  {marca} {clave}: lock={esperada}  entorno={actual}")

    for etiqueta, filas in (
        ("FALTANTES", informe["faltantes"]),
        ("VERSIONES DISTINTAS", informe["distintas"]),
        ("ADICIONALES NO DECLARADOS", informe["adicionales"]),
    ):
        if filas:
            print(f"\n-- {etiqueta} --", file=sys.stderr)
            for fila in filas:
                print(f"  {fila}", file=sys.stderr)

    if args.json:
        Path(args.json).write_text(
            json.dumps(informe, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    if not informe["verificado"]:
        print(
            "\nERROR: el entorno NO reproduce requirements-lock.txt. "
            "No se compila: un ejecutable con versiones distintas no es reproducible.",
            file=sys.stderr,
        )
        return 1

    print(f"\nOK: las {len(lock)} versiones del lock estan instaladas exactamente.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
