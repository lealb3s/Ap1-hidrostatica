# -*- coding: utf-8 -*-
"""Etapa 3: diagnostico da geometria, plano de linhas e casco 3D."""

import numpy as np
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt

import hidro as H
from .comum import (W, exige_tabela, botao_proximo, slider_seguro,
                    calado_maximo, principais)


def _achados():
    tab = st.session_state.tab
    achados = H.diagnosticar(tab, principais())
    st.session_state.achados = achados

    erros = [a for a in achados if a.nivel == "ERRO"]
    avisos = [a for a in achados if a.nivel == "AVISO"]
    if not achados:
        st.success("Nenhum problema detectado. Ainda assim, olhe o plano de linhas antes "
                   "de calcular: o desenho revela erros que numero nenhum denuncia.")
        return
    c1, c2 = st.columns(2)
    c1.metric("Erros", len(erros), help="Impedem um calculo confiavel.")
    c2.metric("Avisos", len(avisos), help="Permitem continuar, com consequencias conhecidas.")

    for a in achados:
        icone = "ERRO" if a.nivel == "ERRO" else "AVISO"
        with st.expander(f"[{icone}] {a.titulo}", expanded=(a.nivel == "ERRO")):
            st.markdown(f"**Onde:** {a.onde}")
            st.markdown(f"**O que foi encontrado:** {a.explicacao}")
            st.markdown(f"**Consequencias:** {a.consequencia}")
            if a.sugestao:
                st.markdown(f"**Como resolver:** {a.sugestao}")
            if a.nivel == "AVISO":
                texto = f"[{a.codigo}] {a.titulo} - {a.consequencia}"
                marcado = st.checkbox("Estou ciente e desejo prosseguir assim mesmo",
                                      key=f"ign_{a.codigo}",
                                      value=texto in st.session_state.avisos_ignorados)
                if marcado and texto not in st.session_state.avisos_ignorados:
                    st.session_state.avisos_ignorados.append(texto)
                    H.registrar("Etapa 3", f"Aviso {a.codigo} ignorado: {a.titulo}",
                                nivel="DECISAO", autor="usuario", consequencia=a.consequencia)
                elif not marcado and texto in st.session_state.avisos_ignorados:
                    st.session_state.avisos_ignorados.remove(texto)


def render():
    st.title("3. Conferir a geometria")
    if not exige_tabela():
        return
    tab = st.session_state.tab
    T = float(st.session_state.get("T_sel") or 0.0)

    a1, a2, a3 = st.tabs(["Diagnostico", "Plano de linhas", "Casco 3D"])

    with a1:
        st.caption("O aplicativo detecta e explica. Ele nao corrige nada sozinho.")
        _achados()

    with a2:
        st.caption(f"Linha d'agua desenhada no calado T = {H.fmt(T)} m "
                   "(ajustavel na barra lateral).")
        if np.isfinite(tab.Y).sum() < 4:
            st.warning("Ha poucos valores validos para desenhar.")
        fig = H.plot_plano_de_linhas(tab, T)
        st.pyplot(fig, **W())
        st.download_button("Baixar o plano de linhas (PNG)", H.fig_para_png(fig),
                           "plano_de_linhas.png", "image/png")
        plt.close(fig)
        st.caption("Compare com a forma esperada do casco. Bicos, cruzamentos e secoes "
                   "invertidas denunciam erro na tabela de cotas.")

    with a3:
        st.caption("Superficie que passa pelos pontos da tabela, sem alisamento. "
                   "E ilustrativa e nao substitui software de modelagem naval.")
        if not np.isfinite(tab.Y).all():
            st.info("O 3D so e gerado com a tabela completa. Volte a etapa 2 para "
                    "preencher as lacunas.")
        else:
            c1, c2 = st.columns([1, 3])
            with c1:
                sup = st.checkbox("Mostrar superficie", value=True)
                exa = st.slider("Exagero visual de y e z", 1.0, 6.0, 1.0, 0.5,
                                help="1,0 mantem a escala real. Serve so para enxergar "
                                     "melhor; nao altera nenhum calculo.")
                elev = st.slider("Elevacao da camera", 0, 80, 22)
                azim = st.slider("Rotacao da camera", -180, 180, -125)
            with c2:
                fig = H.plot_3d(tab, T, sup, exa, elev, azim)
                st.pyplot(fig, **W())
                plt.close(fig)

    botao_proximo("4. Metodos de calculo")
