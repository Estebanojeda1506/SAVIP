# Empalme ICCP–ICOCIV

## Propósito y fuentes

El módulo actualiza una base contractual cuando el periodo atraviesa la transición de ICCP a ICOCIV en diciembre de 2021. Su fuente histórica interna es `app_icociv/datos/iccp_historico.json`, derivada del `EQUIVALENCIA_ICCP/ANEXO 10 ICCP HISTORICO.xlsx`. Las fórmulas se documentan con `EQUIVALENCIA_ICCP/Lineamientos empalme ICCP a ICOCIV.pdf` y el anexo técnico de equivalencias.

## Series y equivalencia

`series_iccp_por_tipo` separa:

- **Total ICCP:** solo `Total ICCP`.
- **Canasta general:** Equipos, Materiales, Transporte, Mano de obra y Costos indirectos, si existen en el histórico.
- **Grupo de obra:** el resto de grupos del Anexo 10, excluyendo total y canasta.

El servicio rechaza una serie que no pertenezca al tipo seleccionado. La ruta ICOCIV se obtiene del selector jerárquico existente. La equivalencia es manual y debe justificarse técnicamente; el software no afirma equivalencia semántica automática.

## Casos temporales

- Fecha final hasta diciembre de 2021: solo tramo ICCP.
- Fecha inicial posterior a diciembre de 2021: solo tramo ICOCIV.
- Fecha inicial hasta diciembre de 2021 y final posterior: empalme completo.

Los índices ICCP posteriores a diciembre de 2021 se rechazan. Para ICOCIV se usa la serie de la ruta seleccionada. La ventana principal conecta el widget con `_ejecutar_proyeccion_para_empalme`; si la fecha final supera el último dato real, reutiliza el servicio de proyección y conserva su resultado en las pestañas existentes.

## Fórmula general implementada

Variables:

- `P`: precio base contractual.
- `A`: anticipo amortizado.
- `Base = P − A`: valor sujeto a ajuste.
- `I0` e `I`: índices inicial y final de cada tramo.
- `R1`: primer valor parcial de ajuste.
- `R2`: segundo valor parcial de ajuste.
- `R`: suma de los ajustes parciales.

```text
R1 = (P − A) × [(I_ICCP / I0_ICCP) − 1]
R2 = [(P − A) + R1] × [(I_ICOCIV / I0_ICOCIV) − 1]
R = R1 + R2
Valor actualizado = (P − A) + R
```

En un caso de un solo tramo, el ajuste del tramo no aplicable es cero. El servicio guarda además los factores `I/I0`, pero no los confunde con R1 o R2.

## Fórmula especial para acero

- `P0`: valor base del insumo acero.
- `Ix`: valor real facturado por kilogramo.
- `q`: cantidad de kilogramos.
- `Z`: diferencia entre valor facturado y valor ajustado.

```text
R1 = P0 × [(I_ICCP / I0_ICCP) − 1]
R2 = (P0 + R1) × [(I_ICOCIV / I0_ICOCIV) − 1]
R = R1 + R2
Z = (Ix × q) − (R + P0)
```

R se calcula aunque Ix o q falten; en ese caso Z queda en `None` con una observación explícita.

## Interfaz, resultado y tablas

El widget `app_icociv/interfaz/widgets/empalme_iccp_icociv.py` limita las unidades a `m lineal`, `m2`, `m3`, `kg`, `Unidad` y `Global`, además del marcador visual sin selección. Cada cálculo válido alimenta:

1. la tabla de equivalencias: insumo contractual, serie ICCP equivalente y último nivel/ruta ICOCIV;
2. la tabla de valor ajustado: unidad, precio, índices por fecha, R1, R2, R y valor actualizado;
3. el resultado principal y el historial en memoria.

Los encabezados de índices incorporan los periodos usados. Si el índice ICOCIV final es proyectado, el resultado conserva la marca, modelo, horizonte, estado y advertencias.

## Exportación Excel actual

Desde el 19 de julio de 2026, `_generar_excel_empalme` crea **una sola hoja** (`Empalme ICCP-ICOCIV`), conforme al requisito RF-10, con secciones consecutivas:

1. título e información general;
2. trazabilidad del cálculo;
3. equivalencias ICCP-ICOCIV;
4. cálculo del valor ajustado (fórmulas Excel para R1, R2, R y valor actualizado);
5. metodología general y, si hay cálculos de acero, metodología especial y detalle acero (con referencias por fórmula a la fila del mismo cálculo dentro de la hoja);
6. observaciones/notas.

La prueba `test_exportacion_excel_empalme_hoja_unica_y_formulas` verifica que el libro tenga exactamente una hoja, las fórmulas por fila y las referencias internas del detalle de acero.

## Validaciones y errores comunes

- P o P0 deben ser positivos; A no puede ser negativo y `P−A` debe ser mayor que cero.
- La fecha inicial no puede superar la final.
- La serie ICCP debe existir y pertenecer al tipo.
- La ruta ICOCIV es obligatoria cuando el tramo la requiere.
- `I0` no puede ser cero y todos los índices deben ser finitos.
- No calcular con el marcador “Sin selección” como unidad o serie.
- No usar una proyección cuando el servicio estadístico la declara no viable.
- No interpretar R1/R2 sin consultar los lineamientos: en el código actual son valores parciales de ajuste y `R = R1 + R2`.
