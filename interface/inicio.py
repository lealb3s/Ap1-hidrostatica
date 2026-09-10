# -*- coding: utf-8 -*-
"""Tela de abertura: o que o aplicativo faz, o que ele aceita e o roteiro."""

import streamlit as st
from .comum import W, ir_para


def render():
    st.title("Calculo Hidrostatico")
    st.markdown("Da **tabela de cotas** as **curvas hidrostaticas**, mostrando cada conta "
                "pelo caminho.")

    st.divider()
    c1, c2 = st.columns([1, 1], gap="large")

    with c1:
        st.markdown("#### O que voce pode enviar")
        st.markdown("""
Arquivos **.xlsx**, **.xls** e **.csv**, com a tabela de cotas em qualquer destes formatos:

- linhas d'agua nas **colunas** e balizas nas linhas
- linhas d'agua nas **linhas** e balizas nas colunas
- tres colunas simples: **x**, **z**, **y**
- numeros com **virgula** ou com ponto decimal
- separador `;` `,` tabulacao ou `|`

O aplicativo tenta reconhecer a estrutura sozinho e mostra o que entendeu.
Se errar, voce corrige na tela, sem mexer em codigo.
        """)

    with c2:
        st.markdown("#### O roteiro")
        st.markdown("""
1. **Dados do navio** — LPP, boca, pontal, calado de projeto e densidade da agua
2. **Tabela de cotas** — enviar o arquivo, conferir a leitura e completar lacunas
3. **Conferir a geometria** — diagnostico, plano de linhas e casco 3D
4. **Metodos de calculo** — Trapezio, Simpson 1/3 e 3/8, com auditoria
5. **Resultados no calado** — propriedades e memoria de calculo
6. **Tabela e curvas** — Hydrostatic Table e Hydrostatic Curves
7. **Validacao** — consistencia interna, comparacao externa e historico
8. **Relatorio** — um documento com tudo o que foi feito
        """)

    st.divider()
    c1, c2 = st.columns([2, 3])
    with c1:
        if st.button("Comecar pela etapa 1", type="primary", **W()):
            ir_para("1. Dados do navio")
    with c2:
        st.caption("Nada e corrigido em silencio: quando algo estiver estranho na tabela, "
                   "o aplicativo mostra onde esta, explica o efeito no resultado e deixa a "
                   "decisao com voce. Tudo fica registrado no relatorio.")
