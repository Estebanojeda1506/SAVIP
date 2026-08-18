"""Controlador principal entre la UI PySide6 y el backend ICOCIV."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import math

import pandas as pd

from app_icociv.datos.cargador_datos import cargar_todas_tablas
from app_icociv.proyeccion.servicio_proyeccion import (
    construir_serie,
    ejecutar_proyeccion,
    resolver_fila_seleccionada,
)
from app_icociv.utilidades.nomenclatura_icociv import (
    construir_ruta_con_tabla,
    nombre_nivel,
    nombre_tabla_icociv,
)
from app_icociv.utilidades.utilidades import ANIO_BASE, filtrar_dataframe


class ControladorPrincipal:
    """Orquesta carga, selección de tabla/índice, proyección y serializacion."""

    def __init__(self) -> None:
        self.ruta_archivo: Path | None = None
        self.tablas: dict[str, pd.DataFrame] = {}
        self.periodos: list[str] = []
        self.fuente_actual: str | None = None
        self.fila_actual: pd.DataFrame | None = None
        self.serie_actual: pd.DataFrame | None = None
        self.proyeccion_actual: dict[str, Any] | None = None

    @property
    def archivo_cargado(self) -> bool:
        return bool(self.tablas)

    def cargar_archivo(self, ruta_archivo: str | Path) -> dict[str, Any]:
        ruta = Path(ruta_archivo)
        with ruta.open("rb") as archivo:
            archivo_bytes = archivo.read()

        self.tablas, self.periodos = cargar_todas_tablas(archivo_bytes, ruta.name)
        self.ruta_archivo = ruta
        self.fuente_actual = None
        self.fila_actual = None
        self.serie_actual = None
        self.proyeccion_actual = None

        return {
            "archivo": str(ruta),
            "periodos": self.periodos,
            "tablas": list(self.tablas.keys()),
        }

    def opciones_grupo(self) -> list[dict[str, Any]]:
        if "T_16" not in self.tablas:
            return []
        return self._opciones(self.tablas["T_16"], "Grupos_Obra")

    def obtener_estado_jerarquia(self, seleccion: dict[str, Any]) -> dict[str, Any]:
        estado = {
            "nivel2": None,
            "nivel3": None,
            "nivel4": None,
            "nivel5": None,
            "nivel6": None,
            "mostrar_chk_t16_1": False,
            "mostrar_chk_t16_2": False,
            "mostrar_chk_t16_3": False,
        }
        if not self.archivo_cargado or seleccion.get("idx_g") is None:
            return estado

        idx_g = seleccion["idx_g"]
        tabla_grupos = self.tablas["T_16"]
        if idx_g >= len(tabla_grupos):
            return estado

        codigo_grupo = tabla_grupos.at[idx_g, "Codigo_Grupos"]

        if seleccion.get("chk_T16"):
            df_l2 = filtrar_dataframe(
                self.tablas["T_16_6"],
                {"Codigo_Grupos": codigo_grupo},
                dropna_col="Grupo_Costos",
            )
            estado["nivel2"] = self._descriptor_nivel(
                nombre_nivel("grupo_costos"), df_l2, "Grupo_Costos"
            )
            idx_l2 = seleccion.get("idx_l2")
            if self._indice_valido(df_l2, idx_l2):
                grupo_costos = str(df_l2.at[idx_l2, "Grupo_Costos"])
                df_l3 = filtrar_dataframe(
                    self.tablas["T_16_7"],
                    {"Codigo_Grupos": codigo_grupo, "Grupo_Costos": grupo_costos},
                    dropna_col="Insumos",
                )
                estado["nivel3"] = self._descriptor_nivel(nombre_nivel("insumo"), df_l3, "Insumos")
            return estado

        df_l2 = filtrar_dataframe(
            self.tablas["T_16_1"],
            {"Codigo_Grupos": codigo_grupo},
            dropna_col="Subclases",
        )
        estado["nivel2"] = self._descriptor_nivel(nombre_nivel("subclase_cpc"), df_l2, "Subclases")
        estado["mostrar_chk_t16_1"] = True

        idx_l2 = seleccion.get("idx_l2")
        if not self._indice_valido(df_l2, idx_l2):
            return estado

        cod_subclase = df_l2.at[idx_l2, "Cod_Subclases"]
        if seleccion.get("chk_T16_1"):
            df_l3 = filtrar_dataframe(
                self.tablas["T_16_8"],
                {"Codigo_Grupos": codigo_grupo, "Cod_Subclases": cod_subclase},
                dropna_col="Grupos_costos",
            )
            estado["nivel3"] = self._descriptor_nivel(
                nombre_nivel("grupo_costos"), df_l3, "Grupos_costos"
            )
            idx_l3 = seleccion.get("idx_l3")
            if self._indice_valido(df_l3, idx_l3):
                grupo_costos = str(df_l3.at[idx_l3, "Grupos_costos"])
                df_l4 = filtrar_dataframe(
                    self.tablas["T_16_9"],
                    {
                        "Codigo_Grupos": codigo_grupo,
                        "Cod_Subclases": cod_subclase,
                        "Grupo_Costos": grupo_costos,
                    },
                    dropna_col="Insumos",
                )
                estado["nivel4"] = self._descriptor_nivel(nombre_nivel("insumo"), df_l4, "Insumos")
            return estado

        df_l3 = filtrar_dataframe(
            self.tablas["T_16_2"],
            {"Codigo_Grupos": codigo_grupo, "Cod_Subclases": cod_subclase},
            dropna_col="Tip_obra",
        )
        estado["nivel3"] = self._descriptor_nivel(nombre_nivel("tipologia_obra"), df_l3, "Tip_obra")
        estado["mostrar_chk_t16_2"] = True

        idx_l3 = seleccion.get("idx_l3")
        if not self._indice_valido(df_l3, idx_l3):
            return estado

        cod_tip_obra = df_l3.at[idx_l3, "Cod_tip_obra"]
        if seleccion.get("chk_T16_2"):
            df_l4 = filtrar_dataframe(
                self.tablas["T_16_10"],
                {
                    "Codigo_Grupos": codigo_grupo,
                    "Cod_Subclases": cod_subclase,
                    "Cod_tip_obra": cod_tip_obra,
                },
                dropna_col="Grupo_Costos",
            )
            estado["nivel4"] = self._descriptor_nivel(
                nombre_nivel("grupo_costos"), df_l4, "Grupo_Costos"
            )
            idx_l4 = seleccion.get("idx_l4")
            if self._indice_valido(df_l4, idx_l4):
                grupo_costos = str(df_l4.at[idx_l4, "Grupo_Costos"])
                df_l5 = filtrar_dataframe(
                    self.tablas["T_16_11"],
                    {
                        "Codigo_Grupos": codigo_grupo,
                        "Cod_Subclases": cod_subclase,
                        "Cod_tip_obra": cod_tip_obra,
                        "Grupo_Costos": grupo_costos,
                    },
                    dropna_col="Insumos",
                )
                estado["nivel5"] = self._descriptor_nivel(nombre_nivel("insumo"), df_l5, "Insumos")
            return estado

        df_l4 = filtrar_dataframe(
            self.tablas["T_16_3"],
            {
                "Codigo_Grupos": codigo_grupo,
                "Cod_Subclases": cod_subclase,
                "Cod_tip_obra": cod_tip_obra,
            },
            dropna_col="Cap_const",
        )
        estado["nivel4"] = self._descriptor_nivel(nombre_nivel("capitulo_constructivo"), df_l4, "Cap_const")
        estado["mostrar_chk_t16_3"] = True

        idx_l4 = seleccion.get("idx_l4")
        if not self._indice_valido(df_l4, idx_l4) or not seleccion.get("chk_T16_3"):
            return estado

        cod_capitulo = df_l4.at[idx_l4, "cod_agreg_niv_obra_cap"]
        df_l5 = filtrar_dataframe(
            self.tablas["T_16_12"],
            {
                "Codigo_Grupos": codigo_grupo,
                "Cod_Subclases": cod_subclase,
                "Cod_tip_obra": cod_tip_obra,
                "cod_agreg_nivel_obra_capitulo": cod_capitulo,
            },
            dropna_col="Grupo_Costos",
        )
        estado["nivel5"] = self._descriptor_nivel(nombre_nivel("grupo_costos"), df_l5, "Grupo_Costos")

        idx_l5 = seleccion.get("idx_l5")
        if self._indice_valido(df_l5, idx_l5):
            grupo_costos = str(df_l5.at[idx_l5, "Grupo_Costos"])
            df_l6 = filtrar_dataframe(
                self.tablas["T_16_13"],
                {
                    "Codigo_Grupos": codigo_grupo,
                    "Cod_Subclases": cod_subclase,
                    "Cod_tip_obra": cod_tip_obra,
                    "cod_agreg_nivel_obra_capitulo": cod_capitulo,
                    "Grupo_Costos": grupo_costos,
                },
                dropna_col="Insumos",
            )
            estado["nivel6"] = self._descriptor_nivel(nombre_nivel("insumo"), df_l6, "Insumos")

        return estado

    def ejecutar_analisis(
        self,
        seleccion: dict[str, Any],
        anio: int,
        mes: int,
        origen_horizonte: str = "predeterminado",
    ) -> dict[str, Any]:
        if not self.archivo_cargado:
            raise ValueError("Primero debe cargar un archivo Excel.")

        fuente, fila = resolver_fila_seleccionada(self.tablas, self.periodos, seleccion)
        serie_df = construir_serie(fila, self.periodos)
        proyeccion = ejecutar_proyeccion(
            serie_df=serie_df,
            year_proj=anio,
            month_proj=mes,
            anio_base=ANIO_BASE,
            origen_horizonte=origen_horizonte,
        )

        self.fuente_actual = fuente
        self.fila_actual = fila
        self.serie_actual = serie_df
        self.proyeccion_actual = proyeccion
        ruta_jerarquica = self.construir_ruta_jerarquica(seleccion)
        trazabilidad = (proyeccion.get("analisis_horizontes_completo") or {}).get("trazabilidad")
        if isinstance(trazabilidad, dict):
            ruta_sin_tabla = [item for item in ruta_jerarquica if item.get("nivel") != "Tabla ICOCIV"]
            trazabilidad.update(
                {
                    "ruta_jerarquica": ruta_jerarquica,
                    "tabla_icociv": nombre_tabla_icociv(fuente),
                    "identificador_fila": str(fila.index[0]) if not fila.empty else "",
                    "nombre_serie": ruta_sin_tabla[-1]["valor"] if ruta_sin_tabla else nombre_tabla_icociv(fuente),
                    "fecha_corte": str(serie_df["Periodo"].iloc[-1]) if not serie_df.empty else "",
                    "configuracion_modelos": list((proyeccion.get("stats") or {}).get("modelos_evaluados") or []),
                }
            )

        return {
            "fuente": fuente,
            "fuente_visible": nombre_tabla_icociv(fuente),
            "fila": fila,
            "serie_df": serie_df,
            "proyeccion": proyeccion,
            "ruta_jerarquica": ruta_jerarquica,
        }

    def nombre_fuente_seleccion(self, seleccion: dict[str, Any]) -> str:
        """Resuelve la tabla ICOCIV que corresponde a la selección actual."""
        if not self.archivo_cargado or seleccion.get("idx_g") is None:
            return ""
        try:
            fuente, _ = resolver_fila_seleccionada(self.tablas, self.periodos, seleccion)
        except Exception:
            return ""
        return nombre_tabla_icociv(fuente)

    def construir_ruta_jerarquica(self, seleccion: dict[str, Any]) -> list[dict[str, str]]:
        ruta: list[dict[str, str]] = []
        if not self.archivo_cargado or seleccion.get("idx_g") is None:
            return ruta

        grupo = self._texto_seleccion(self.tablas["T_16"], seleccion["idx_g"], "Grupos_Obra")
        if grupo:
            ruta.append({"nivel": nombre_nivel("grupo_obra"), "valor": grupo})

        estado = self.obtener_estado_jerarquia(seleccion)
        for clave in ("nivel2", "nivel3", "nivel4", "nivel5", "nivel6"):
            descriptor = estado.get(clave)
            idx = seleccion.get(f"idx_l{clave[-1]}")
            if descriptor and self._indice_valido(descriptor["dataframe"], idx):
                valor = self._texto_seleccion(
                    descriptor["dataframe"],
                    idx,
                    descriptor["columna"],
                )
                if valor:
                    ruta.append({"nivel": descriptor["etiqueta"], "valor": valor})
        return construir_ruta_con_tabla(self.fuente_actual, ruta)

    def crear_datos_sesion(
        self,
        usuario: str,
        seleccion: dict[str, Any],
        parametros_proyeccion: dict[str, Any],
        ruta_jerarquica: list[dict[str, str]],
    ) -> dict[str, Any]:
        if self.proyeccion_actual is None or self.serie_actual is None:
            raise ValueError("No hay una proyección ejecutada para guardar.")

        return {
            "usuario": usuario,
            "archivo_excel": str(self.ruta_archivo or ""),
            "seleccion": seleccion,
            "parametros_proyeccion": parametros_proyeccion,
            "resultado_proyeccion": self._proyeccion_serializable(self.proyeccion_actual),
            "serie_historica": self.serie_actual.to_dict(orient="records"),
            "ruta_jerarquica": ruta_jerarquica,
            "fuente": self.fuente_actual,
            "fuente_visible": nombre_tabla_icociv(self.fuente_actual),
        }

    def _descriptor_nivel(self, etiqueta: str, dataframe: pd.DataFrame, columna: str) -> dict[str, Any]:
        return {
            "etiqueta": etiqueta,
            "columna": columna,
            "opciones": self._opciones(dataframe, columna),
            "dataframe": dataframe,
        }

    def _opciones(self, dataframe: pd.DataFrame, columna: str) -> list[dict[str, Any]]:
        opciones: list[dict[str, Any]] = []
        for indice in dataframe.index.tolist():
            valor = dataframe.at[indice, columna]
            if pd.isna(valor):
                continue
            opciones.append({"indice": int(indice), "texto": str(valor)})
        return opciones

    def _texto_seleccion(self, dataframe: pd.DataFrame, indice: int | None, columna: str) -> str:
        if not self._indice_valido(dataframe, indice):
            return ""
        valor = dataframe.at[indice, columna]
        return "" if pd.isna(valor) else str(valor)

    @staticmethod
    def _indice_valido(dataframe: pd.DataFrame, indice: int | None) -> bool:
        return indice is not None and 0 <= int(indice) < len(dataframe)

    @staticmethod
    def _proyeccion_serializable(proyeccion: dict[str, Any]) -> dict[str, Any]:
        stats = proyeccion.get("stats", {})
        def numero(valor: Any) -> float | None:
            try:
                valor_float = float(valor)
            except (TypeError, ValueError):
                return None
            return valor_float if math.isfinite(valor_float) else None

        def entero(valor: Any) -> int | None:
            try:
                return int(valor)
            except (TypeError, ValueError):
                return None

        backtesting = proyeccion.get("backtesting", {}) or {}
        predicciones = backtesting.get("predicciones")
        if isinstance(predicciones, pd.DataFrame):
            predicciones_serializadas = predicciones.to_dict(orient="records")
        else:
            predicciones_serializadas = []
        proyecciones = proyeccion.get("proyecciones")
        if isinstance(proyecciones, pd.DataFrame):
            proyecciones_serializadas = proyecciones.to_dict(orient="records")
        else:
            proyecciones_serializadas = []

        return {
            "proyeccion_generada": bool(proyeccion.get("proyeccion_generada", True)),
            "periodo_solicitado": proyeccion.get("periodo_solicitado"),
            "periodo_proj": proyeccion.get("periodo_proj"),
            "model_name": proyeccion.get("model_name"),
            "horizonte_solicitado": entero(proyeccion.get("horizonte_solicitado")),
            "horizonte_permitido": entero(proyeccion.get("horizonte_permitido")),
            "factibilidad": proyeccion.get("factibilidad", {}),
            "horizonte_info": proyeccion.get("horizonte_info", {}),
            "resultado_horizonte_solicitado": proyeccion.get("resultado_horizonte_solicitado", {}),
            "analisis_horizontes_completo": proyeccion.get("analisis_horizontes_completo", {}),
            "y_proj": numero(proyeccion.get("y_proj")),
            "ci_lo": numero(proyeccion.get("ci_lo")),
            "ci_hi": numero(proyeccion.get("ci_hi")),
            "ci80_lo": numero(proyeccion.get("ci80_lo")),
            "ci80_hi": numero(proyeccion.get("ci80_hi")),
            "ci95_lo": numero(proyeccion.get("ci95_lo")),
            "ci95_hi": numero(proyeccion.get("ci95_hi")),
            "factor_actualizacion": numero(proyeccion.get("factor_actualizacion")),
            "variacion_acumulada": numero(proyeccion.get("variacion_acumulada")),
            "proyecciones": proyecciones_serializadas,
            "outliers": proyeccion.get("outliers", []),
            "estadisticas": {
                "r2": numero(stats.get("r2")),
                "r2_ajustado": numero(stats.get("r2_ajustado")),
                "aic": numero(stats.get("aic")),
                "jb_p": numero(stats.get("jb_p")),
                "kurt_ex": numero(stats.get("kurt_ex")),
                "aicc": numero(stats.get("aicc")),
                "n": entero(stats.get("n")),
                "width95": numero(stats.get("width95")),
                "durbin_watson": numero(stats.get("durbin_watson")),
                "mae_ajuste": numero(stats.get("mae_ajuste")),
                "rmse_ajuste": numero(stats.get("rmse_ajuste")),
                "mape_ajuste": numero(stats.get("mape_ajuste")),
            },
            "validacion_serie": proyeccion.get("validacion_serie", {}),
            "analisis_serie": proyeccion.get("analisis_serie", {}),
            "diagnostico_residuos": proyeccion.get("diagnostico_residuos", {}),
            "backtesting": {
                "ejecutado": bool(backtesting.get("ejecutado", False)),
                "metodo": backtesting.get("metodo"),
                "entrenamiento_inicial": entero(backtesting.get("entrenamiento_inicial")),
                "iteraciones": entero(backtesting.get("iteraciones")),
                "metricas": backtesting.get("metricas", {}),
                "predicciones": predicciones_serializadas,
                "errores": backtesting.get("errores", []),
                "interpretacion": backtesting.get("interpretacion", ""),
            },
            "justificacion_modelo": proyeccion.get("justificacion_modelo", ""),
            "interpretacion_estadistica": proyeccion.get("interpretacion_estadistica", []),
        }
