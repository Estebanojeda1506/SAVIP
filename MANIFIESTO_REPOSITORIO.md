# Manifiesto del repositorio final de SAVIP

Este repositorio es un **export limpio**: contiene únicamente lo necesario para
ejecutar SAVIP, instalar sus dependencias, entender su estructura, reproducir sus
resultados y compilar la documentación final. Se construyó copiando lo esencial
desde el árbol de trabajo histórico, que **permanece intacto en local** y no se
publicó.

Fecha del export: 18 de agosto de 2026. Versión: ver `VERSION`.

## Qué contiene

| Categoría | Contenido |
|---|---|
| `ESENCIAL_EJECUCION` | `aplicacion.py`, `app_icociv/` (incluidos los recursos de interfaz y `iccp_historico.json`), `VERSION` |
| `ESENCIAL_DEPENDENCIAS` | `requirements.txt`, `requirements-build.txt`, `requirements-lock.txt` |
| `ESENCIAL_REPRODUCIBILIDAD` | `tests/`, `pruebas/`, `packaging/`, `scripts/`, `auditoria_academica/`, `.gitignore`, `.gitattributes` |
| `ESENCIAL_DOCUMENTACION_FINAL` | `README.md`, `README_EJECUTABLE.txt`, `CHANGELOG.md`, `documentacion_latex/` (seis documentos vigentes), `docs/documentacion_tecnica/` (documentación técnica), `docs/referencias/`, `docs/auditoria_criterios_estadisticos.md`, `docs/mapa_reorganizacion_modulos.md`, este manifiesto |

## Qué se dejó fuera, y por qué

Todo lo siguiente es `PRESCINDIBLE`: no hace falta para ejecutar, instalar,
entender ni reproducir. Su exclusión es **limpieza técnica**, no ocultamiento;
nada de lo excluido es una cita, una referencia bibliográfica, una licencia ni una
atribución de terceros.

| Categoría excluida | Motivo |
|---|---|
| Anexos de datos del DANE (`*.xlsb`) y del ICCP (`*.xlsx`), documentos institucionales de terceros (`EQUIVALENCIA_ICCP/`, `Anexo ICCP dic 2021/`) | Datos y documentos de terceros; se obtienen de la publicación oficial. Ya excluidos por `.gitignore` desde el 29-jul-2026 |
| `referencias_bibliograficas/` (PDF de artículos citados) | Material de terceros con derechos de autor; la bibliografía sí se conserva en cada `referencias.bib` y en `docs/referencias/` |
| Artefactos de remediación y auditoría (`06_REMEDIACIONES/`, `15_PRUEBAS_ROJAS/`, `ESTADO_SESION.md`, `SAVIP_AUDITORIA_*`, `docs/remediacion_*`, `auditoria_horizonte_20.md`) | Historia de proceso ya superada; el resultado vive en el código, las pruebas y el documento |
| Andamiaje de asistencia (`.claude/`, `.codex/`, `.agents/`, `.specify/`, `CLAUDE.md`, prompts, notas de sesión y planes ya ejecutados de `docs/documentacion_tecnica/`) | No es código ni documentación del producto |
| Salidas y entornos generados (`build/`, `dist/`, `release/`, `.venv-build/`, `logs/`, `tmp/`, `output/`, `reportes_generados/`, `sesiones/`, `__pycache__/`) | Se regeneran; no son fuentes |
| Comprimidos y respaldos (`*.zip`) | Artefactos de entrega, no fuentes |
| `documentacion_latex/historico/` y documentación superseded (`documentacion/`, `legado/`, `anexos anteproyecto/`, `pruebas app/`) | Versiones anteriores, explícitamente no vigentes |
| 139 imágenes (≈21,9 MiB) de capturas de revisión de PDF | Ningún `.tex` las referencia: el documento dibuja sus figuras con TikZ |
| PDF compilados (`*.pdf`) | Decisión del 29-jul-2026: se reconstruyen desde las fuentes para que binario y texto no puedan divergir |

## Verificación de este export

Comprobado el 18 de agosto de 2026, ejecutando **desde este repositorio** y sin
acceso a ninguno de los archivos excluidos:

- `python aplicacion.py --autocomprobacion` → **7/7 comprobaciones superadas**
  (dependencias, recursos internos, datos ICCP, empalme, flujo de proyección,
  exportables DOCX/PDF/CSV y escritura fuera del *bundle*).
- Importación de todos los paquetes: correcta. Catálogo activo de 10 modelos,
  `N₀ = 6`, 35 criterios en la matriz.
- `tests/test_imports_modulos.py`, `tests/test_auditoria_formulas_estadisticas.py`,
  `tests/test_empalme_iccp_icociv.py`, `tests/test_cierre_metodologico.py` → verdes.
- Documento final compilado desde este repositorio: **168 páginas**, 0 errores,
  0 referencias indefinidas, 0 citas indefinidas, 0 *rerun* pendiente.
- Auditoría de secretos sobre 217 archivos de texto: **ninguno**. Ningún `.env`,
  token, clave privada ni credencial.

Las pruebas que necesitan el anexo oficial se **omiten solas** cuando el archivo
no está presente, de modo que la suite corre en una copia limpia.

## Autoría y atribución

El autor del código propio, de la integración, de la redacción propia y de los
*commits* de este repositorio es **Carlos Esteban Ojeda Calvache**.

Eso no alcanza al conocimiento tomado de terceros. Los índices ICOCIV e ICCP son
producción oficial del **DANE**; los métodos estadísticos empleados proceden de
la literatura citada en el punto de uso y listada en la bibliografía de cada
documento; y las bibliotecas de terceros conservan sus propias licencias, según
`requirements.txt`.
