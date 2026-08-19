"""Genera de forma determinista (sin aleatoriedad) `serie_drift.csv` y
`serie_holt.csv`, los fixtures del caso 7777777 (hallazgo H-13) que consume
`pruebas/prueba_horizonte_dinamico_ui_reportes.py`.

Micro-remediacion final post-R2 residual, 18-08-2026. Ambos archivos
faltaban en este checkout desde la exportacion limpia del repositorio y no
tenian historial en Git aqui (nunca estuvieron versionados en SAVIP_REPO_
FINAL). Son series sinteticas, no datos DANE.

Regla de generacion:
    Indice(i) = 100.0 + pendiente * i + amplitud * sin(i * frecuencia)
    i = 0..72  (73 observaciones mensuales, periodos 2020-01 a 2026-01)

73 observaciones para que, al proyectar hacia 2027-01 con
`ejecutar_proyeccion(serie, 2027, 1, 2021)`, `horizonte_solicitado` resulte
exactamente 12 (lo que exigen las pruebas que consumen estos fixtures).

`serie_drift.csv` y `serie_holt.csv` usan amplitud/frecuencia distintas
solo para ser trayectorias diferentes -H-13 exige
`not drift["Indice"].equals(holt["Indice"])`-. El nombre de cada archivo es
historico (ver "CIERRE H-9" y "AUDITORIA 09-08-2026 (C-01)" en el script
que los consume): bajo la seleccion vigente por RMSE fuera de muestra
global, ningun archivo garantiza que su modelo homonimo gane, y las
pruebas que los usan ya no lo exigen (verifican coherencia informe-modelo,
no la identidad del ganador).

Ejecutar desde la raiz del repositorio: python tests/fixtures/horizonte_dinamico/generar_fixtures.py
"""
from __future__ import annotations

import math
from pathlib import Path

N = 73
DESTINO = Path(__file__).resolve().parent


def _escribir(nombre: str, amplitud: float, frecuencia: float, pendiente: float = 0.5) -> None:
    periodos = [f"{2020 + i // 12}_{i % 12 + 1}" for i in range(N)]
    valores = [100.0 + pendiente * i + amplitud * math.sin(i * frecuencia) for i in range(N)]
    ruta = DESTINO / nombre
    with ruta.open("w", encoding="utf-8", newline="\n") as f:
        f.write("Periodo,Indice\n")
        for periodo, valor in zip(periodos, valores):
            f.write(f"{periodo},{valor:.6f}\n")
    print(f"escrito {ruta.name}: {N} filas, ultimo periodo {periodos[-1]}")


if __name__ == "__main__":
    _escribir("serie_drift.csv", amplitud=2.5, frecuencia=0.9)
    _escribir("serie_holt.csv", amplitud=4.0, frecuencia=0.55, pendiente=0.7)
