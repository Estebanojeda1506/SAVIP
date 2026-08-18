"""Convierte el BibTeX verificado del proyecto a RIS sin dependencias externas."""

from __future__ import annotations

import re
import sys
from pathlib import Path


def convertir(texto: str) -> str:
    entradas = re.findall(r"@(\w+)\{([^,]+),\s*(.*?)\n\}", texto, re.S)
    salida: list[str] = []
    for tipo, clave, cuerpo in entradas:
        campos_crudos = {
            nombre.lower(): valor
            for nombre, valor in re.findall(
                r"(\w+)\s*=\s*(\{(?:[^{}]|\{[^{}]*\})*\}|\"[^\"]*\")\s*,?",
                cuerpo,
                re.S,
            )
        }
        campos = {nombre: limpiar(valor) for nombre, valor in campos_crudos.items()}
        salida.append(f"TY  - { {'article': 'JOUR', 'book': 'BOOK'}.get(tipo.lower(), 'ELEC') }")
        autor_crudo = campos_crudos.get("author", "")
        autores = [campos.get("author", "")] if autor_crudo.startswith("{{") else campos.get("author", "").split(" and ")
        for autor in autores:
            if autor.strip():
                salida.append(f"AU  - {autor.strip()}")
        agregar(salida, "TI", campos.get("title"))
        agregar(
            salida,
            "T2",
            campos.get("journal") or campos.get("publisher") or campos.get("institution"),
        )
        if campos.get("year") not in {None, "s.f."}:
            agregar(salida, "PY", campos.get("year"))
        agregar(salida, "VL", campos.get("volume"))
        agregar(salida, "IS", campos.get("number"))
        paginas = re.split(r"--|–", campos.get("pages", ""), maxsplit=1)
        if paginas and paginas[0]:
            agregar(salida, "SP", paginas[0])
        if len(paginas) == 2:
            agregar(salida, "EP", paginas[1])
        agregar(salida, "DO", campos.get("doi"))
        agregar(salida, "UR", campos.get("url") or campos.get("howpublished"))
        agregar(salida, "N1", campos.get("note"))
        agregar(salida, "ID", clave)
        salida.extend(["ER  -", ""])
    assert entradas and salida.count("ER  -") == len(entradas)
    return "\n".join(salida).rstrip() + "\n"


def limpiar(valor: str) -> str:
    valor = valor.strip().strip('"')
    if valor.startswith("{") and valor.endswith("}"):
        valor = valor[1:-1]
    valor = valor.replace(r"\url{", "").replace(r"\_", "_")
    if valor.endswith("}") and ("http://" in valor or "https://" in valor):
        valor = valor[:-1]
    return valor.replace("{", "").replace("}", "").replace("--", "–").strip()


def agregar(salida: list[str], etiqueta: str, valor: str | None) -> None:
    if valor:
        salida.append(f"{etiqueta}  - {valor}")


if __name__ == "__main__":
    origen, destino = map(Path, sys.argv[1:3])
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(convertir(origen.read_text(encoding="utf-8")), encoding="utf-8")
