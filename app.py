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

comum.iniciar_estado()
pagina = comum.barra_lateral()
TELAS[pagina]()
