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
"""

# Nucleo: sem qualquer um destes o aplicativo nao tem o que calcular, entao a
# falta de um deve aparecer imediatamente.
from .base import *          # noqa: F401,F403
from .leitura import *       # noqa: F401,F403
from .tabela import *        # noqa: F401,F403
from .integracao import *    # noqa: F401,F403
from .hidrostatica import *  # noqa: F401,F403
from .graficos import *      # noqa: F401,F403
from .relatorio import *     # noqa: F401,F403

# Opcional: o relatorio em PDF depende da biblioteca reportlab. Se o arquivo nao
# tiver sido enviado ou a biblioteca nao estiver instalada, o resto do aplicativo
# continua funcionando e apenas o botao de PDF avisa o que falta.
try:
    from .pdf import *       # noqa: F401,F403
except Exception:            # noqa: BLE001
    pass
