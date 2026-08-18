# Pruebas documentales del trabajo de grado

**Esto no es SAVIP.** La auditoría de citas y la verificación de fuentes
pertenecen al proceso académico de la tesis. La aplicación no incluye módulos,
dependencias, pruebas en tiempo de ejecución ni archivos destinados a auditar
referencias bibliográficas.

## Qué contiene

`test_referencias_documentales.py`, con cuatro comprobaciones:

| Comprobación | Qué verifica |
|---|---|
| `test_referencias_latex_quedan_auditadas_y_sin_alias_duplicados` | La bibliografía de la guía académica no conserva alias duplicados; el registro de auditoría declara 22 entradas citadas, 0 claves sin entrada BibTeX, y hay 22 carpetas de verificación. |
| `test_bibliografia_no_conserva_urls_editoriales_obsoletas` | Ninguna de las cuatro URL editoriales retiradas sobrevive en la bibliografía ni en los registros; las tres fuentes de reemplazo sí están presentes. |
| `test_bibliografia_no_usa_catalogos_o_fichas_comerciales_como_fuente_principal` | Ningún patrón de catálogo o ficha comercial (Amazon, Scribd, academia.edu, WorldCat, fichas de editorial) aparece como fuente; cada carpeta conserva un artefacto material consultado. |
| `test_referencias_citadas_no_tienen_carpetas_solo_txt` | Ninguna referencia citada tiene una carpeta con solo archivos `.txt`, y todas registran su uso en LaTeX. |

Son las mismas cuatro que vivían en
`tests/test_presentacion_resultados_y_referencias.py`, con los mismos umbrales y
las mismas rutas. **Ninguna se debilitó al separarla**: solo se movió.

## Ejecución

```bash
python auditoria_academica/pruebas_documentales/test_referencias_documentales.py
```

Requiere `referencias_bibliograficas/` en la raíz del proyecto. Esa carpeta no se
versiona: contiene los artefactos consultados de terceros y su redistribución no
está resuelta. Si falta, la suite termina con código 2 y lo dice; no aprueba
nada por omisión.

## Por qué está separada

Hasta el 29 de julio de 2026 estas cuatro comprobaciones compartían archivo con
trece pruebas de presentación de la interfaz. El archivo mezclaba dos cosas sin
relación: cómo se muestra un resultado en pantalla y si una cita bibliográfica
está respaldada.

La mezcla tenía una consecuencia concreta: al excluir del control de versiones la
biblioteca de referencias, la suite del producto dejó de poder ejecutarse en un
clon limpio. Un clon recién hecho daba 13 de 17 con cuatro `FileNotFoundError`,
de modo que un defecto de reproducibilidad del producto y una dependencia
legítima del proceso académico eran indistinguibles en el mismo informe.

Tras la separación:

- `tests/test_presentacion_resultados.py` — 13 comprobaciones, corre en un clon
  limpio sin insumos externos. Forma parte de las 28 suites del producto.
- `auditoria_academica/pruebas_documentales/` — 4 comprobaciones, académicas,
  fuera de las 28 suites y fuera de `packaging/SAVIP.spec`.

## Relación con el empaquetado

`packaging/SAVIP.spec` excluye `auditoria_academica` por nombre, además de
`tests`, `pruebas` y `docs`. El ejecutable no contiene tesis, auditorías,
referencias bibliográficas, pruebas ni documentos de remediación.
