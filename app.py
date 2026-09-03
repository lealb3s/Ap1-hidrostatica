# -*- coding: utf-8 -*-
"""
=============================================================================
 APLICATIVO DE CALCULO HIDROSTATICO - AP1.1 Projeto Integrador
 Arquitetura Naval
=============================================================================

 Ponto de entrada. Este arquivo so monta a pagina e chama a tela escolhida;
 toda a logica esta nos pacotes:

     hidro/       calculo (leitura, integracao, hidrostatica, graficos)
     interface/   telas (uma por etapa do roteiro)

 Execucao:  streamlit run app.py
=============================================================================
"""

import streamlit as st

st.set_page_config(page_title="Calculo Hidrostatico", page_icon="~",
                   layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
.block-container{padding-top:2.2rem;padding-bottom:3rem;max-width:1400px}
div[data-testid="stMetricValue"]{font-size:1.3rem}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Conferencia do pacote de calculo
#
# O pacote hidro reune suas funcoes no arquivo hidro/__init__.py. Se esse arquivo
# for enviado vazio ou incompleto, "import hidro" continua funcionando, mas nao
# traz funcao nenhuma junto: o programa so quebra bem mais tarde, com um erro que
# nao diz qual e o problema. Aqui o pacote e remontado na hora, a partir dos
# proprios modulos, para que isso nunca derrube o aplicativo.
# ---------------------------------------------------------------------------
import importlib                                                # noqa: E402
import pkgutil                                                    # noqa: E402

import hidro as _hidro                                            # noqa: E402

if not hasattr(_hidro, "fmt") or not hasattr(_hidro, "gerar_relatorio_pdf"):
    # A lista de modulos e descoberta, e nao escrita a mao: quando o pacote ganha
    # um arquivo novo, ele entra sozinho. Ja perdi o modulo do PDF por causa de
    # uma lista fixa que nao foi atualizada.
    _faltando = []
    for _info in pkgutil.iter_modules(_hidro.__path__):
        try:
            _mod = importlib.import_module(f"hidro.{_info.name}")
        except Exception as _e:                                    # noqa: BLE001
            _faltando.append(f"{_info.name} ({_e})")
            continue
        for _nome in dir(_mod):
            if not _nome.startswith("_"):
                setattr(_hidro, _nome, getattr(_mod, _nome))

_ausentes = [n for n in ("fmt", "hidrostatica", "plot_curvas", "ler_arquivo_bruto",
                         "gerar_relatorio")
             if not hasattr(_hidro, n)]

from interface import comum                                    # noqa: E402
from interface import (inicio, p1_dados, p2_cotas, p3_geometria,  # noqa: E402
                       p4_metodos, p5_calado, p6_curvas,
                       p7_validacao, p8_relatorio)

TELAS = {
    "Inicio": inicio.render,
    "1. Dados do navio": p1_dados.render,
    "2. Tabela de cotas": p2_cotas.render,
    "3. Conferir a geometria": p3_geometria.render,
    "4. Metodos de calculo": p4_metodos.render,
    "5. Resultados no calado": p5_calado.render,
    "6. Tabela e curvas": p6_curvas.render,
    "7. Validacao": p7_validacao.render,
    "Relatorio final": p8_relatorio.render,
}

if _ausentes:
    st.error(
        "Faltam arquivos na pasta **hidro**: o pacote foi carregado sem "
        + ", ".join(f"`{n}`" for n in _ausentes) +
        ". Confira se todos os arquivos .py da pasta hidro foram enviados ao "
        "repositorio, em especial `pdf.py`, e se nenhum ficou vazio.")

comum.iniciar_estado()
pagina = comum.barra_lateral()
TELAS[pagina]()
