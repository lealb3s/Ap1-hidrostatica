
# -*- coding: utf-8 -*-
"""Pacote de calculo hidrostatico."""

import importlib

ERROS_IMPORT = {}

_MODULOS = [
    "base",
    "leitura",
    "tabela",
    "integracao",
    "hidrostatica",
    "carga",
    "graficos",
    "relatorio",
    "pdf",
]

# Importa os modulos existentes e disponibiliza suas funcoes
# diretamente pelo pacote: import hidro as H.
for _nome in _MODULOS:
    try:
        _mod = importlib.import_module(f".{_nome}", package=__name__)
    except Exception as _e:
        ERROS_IMPORT[_nome] = f"{type(_e).__name__}: {_e}"
        continue

    for _chave in dir(_mod):
        if not _chave.startswith("_") and _chave != "ERROS_IMPORT":
            globals()[_chave] = getattr(_mod, _chave)

# Exporta explicitamente as funcoes essenciais de base.py.
try:
    from .base import fmt, para_float, registrar, historico_df
except Exception as _e:
    ERROS_IMPORT["base"] = f"{type(_e).__name__}: {_e}"

# Verifica se as funcoes essenciais estao disponiveis.
_essenciais = ("fmt", "para_float", "registrar", "historico_df")
_faltantes = [
    nome for nome in _essenciais
    if not callable(globals().get(nome))
]

if _faltantes:
    ERROS_IMPORT.setdefault(
        "base",
        "Funcoes essenciais ausentes: " + ", ".join(_faltantes)
    )

del importlib
