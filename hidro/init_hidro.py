# -*- coding: utf-8 -*-
"""
Pacote de calculo hidrostatico.

Cada modulo cuida de uma etapa, na ordem em que os dados percorrem o programa:

    base.py          constantes, leitura de numeros, unidades, historico
    leitura.py       abre o arquivo e descobre o layout da tabela de cotas
    tabela.py        modelo da tabela, diagnostico geometrico e interpolacao
    integracao.py    Trapezio, Simpson 1/3 e Simpson 3/8 com auditoria
    hidrostatica.py  areas, volumes, centros, metacentro, coeficientes, WSA
    graficos.py      plano de linhas, casco 3D e curvas
    relatorio.py     relatorio HTML e exportacao para Excel
    pdf.py           relatorio final em PDF (opcional: exige a biblioteca reportlab)

Para mexer em uma formula, abra o modulo correspondente: nada mais precisa mudar.

Se um arquivo faltar ou tiver erro, o pacote NAO interrompe a importacao aqui: o
motivo fica guardado em ERROS_IMPORT e o app.py mostra na tela qual arquivo esta
faltando. Interromper aqui produzia apenas um traceback, sem dizer o que enviar.
"""

import importlib

ERROS_IMPORT = {}

_MODULOS = ["base", "leitura", "tabela", "integracao", "hidrostatica",
            "graficos", "relatorio", "pdf"]

for _nome in _MODULOS:
    try:
        _mod = importlib.import_module(f".{_nome}", __name__)
    except Exception as _e:                       # noqa: BLE001
        ERROS_IMPORT[_nome] = f"{type(_e).__name__}: {_e}"
        continue
    for _chave in dir(_mod):
        if not _chave.startswith("_"):
            globals()[_chave] = getattr(_mod, _chave)

del importlib
