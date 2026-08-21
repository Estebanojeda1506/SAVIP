# Datos y fuentes

## Fuentes ICOCIV

- `anex-ICOCIV-may2026.xlsb`: **anexo activo** de la versión 0.3.0-rc2, presente en la
  raíz y no versionado. Cubre enero de 2021 a mayo de 2026 (65 periodos). Es el que
  usan la línea base, el ejecutor de suites y los ejemplos numéricos.
- `anex-ICOCIV-ene2026.xlsb` y `pruebas app/anex-ICOCIV-nov2025.xlsb`: anexos
  históricos, conservados solo para comparación. Rutas, periodos y SHA-256 en
  `docs/datos/FUENTE_DE_DATOS_ACTIVA.md`.
- `Anexos Icociv/`: carpeta reservada para anexos relacionados.
- `anexos anteproyecto/Anexo A...pdf`: ficha metodológica ICOCIV del DANE.
- `anexos anteproyecto/Anexo B...pdf`: metodología general ICOCIV del DANE.

Los anexos son entradas; no sobrescribirlos con salidas de la aplicación. El usuario selecciona el archivo desde la interfaz y el código no debe fijar rutas personales.

## Fuentes ICCP y empalme

- `EQUIVALENCIA_ICCP/ANEXO 10 ICCP HISTORICO.xlsx`: series históricas ICCP.
- `EQUIVALENCIA_ICCP/Lineamientos empalme ICCP a ICOCIV.pdf`: fórmulas y definiciones principales del empalme.
- `EQUIVALENCIA_ICCP/ANEXO TECNICO R3 EQUIVALENCIAS ICCP A ICOCIV.pdf`: equivalencias técnicas de referencia.
- `Anexo ICCP dic 2021/anexos_iccp_dic21.xlsx`: anexo ICCP adicional.
- `app_icociv/datos/iccp_historico.json`: copia estructurada consumida por la aplicación; mantener su trazabilidad con el Anexo 10.

## Fuentes institucionales complementarias

`anexos anteproyecto/` contiene, además de los documentos DANE:

- revisión de precios del Contrato de Obra 1172-2020;
- cartilla INVIAS sobre implementación ICOCIV y reversión de precios;
- concepto de Colombia Compra Eficiente sobre equilibrio económico y ajuste;
- oficio de solicitud de revisión de precios;
- acta de reunión de revisión de precios.

Son fuentes de contraste institucional. El nombre histórico de la carpeta no obliga a mencionar el anteproyecto en el documento final.

## Documentación estadística y académica

- Preliminar: `documentacion_latex/guia_academica_estadistica/main.tex` y su `referencias.bib`.
- Final: `documentacion_latex/documento_tecnico_icociv_iccp/main.tex` y `referencias.bib`.
- Mapas/auditorías: `docs/mapa_reorganizacion_modulos.md`, `docs/auditoria_criterios_estadisticos.md` y `docs/auditoria_horizonte_20.md`.
- Referencias organizadas: `referencias_bibliograficas/usadas_en_documento_latex/` y `usadas_en_otros_componentes/`.

Las carpetas Las versiones anteriores están en `documentacion_latex/historico/`; no tratarlas como documento vigente. Ver `documentacion_latex/LEEME.md`.

## Herramientas y ejemplos Excel

`33333.xlsx` existe en la raíz, pero su propósito no quedó verificable por nombre durante la migración. No documentarlo como fuente oficial ni modificarlo hasta identificar su procedencia. La herramienta Excel externa mencionada en sesiones anteriores no se considera parte del repositorio mientras no esté presente y trazada aquí.

## Salidas generadas

- `reportes_generados/`: PDF, DOCX y otros reportes.
- `sesiones/`: estado JSON.
- `output/` y `tmp/`: salidas o inspecciones temporales.
- auxiliares y `main.pdf` del documento LaTeX.

Una salida generada no debe citarse como fuente primaria si existe el documento DANE/IDU original.

## Archivos que requieren especial cuidado

- anexos `.xlsb`, `.xlsx`, `.pdf` y `.docx` institucionales;
- `iccp_historico.json`;
- bibliografías `.bib` y carpetas de referencias;
- `main.tex`, figuras TikZ y anexos del documento final;
- archivos con cambios previos no confirmados por `git status`.

No duplicar archivos pesados para la migración. Documentar rutas relativas y verificar hash/procedencia si se reemplaza una fuente.
