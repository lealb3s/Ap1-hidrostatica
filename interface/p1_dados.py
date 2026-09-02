# -*- coding: utf-8 -*-
"""Etapa 1: dados principais da embarcacao e convencoes de calculo."""

import streamlit as st
from .comum import W, botao_proximo, origem_texto, principais, opcoes


def render():
    st.title("1. Dados do navio")
    st.caption("Servem para os coeficientes de forma e para o aplicativo perceber quando a "
               "tabela de cotas nao combina com a embarcacao.")

    p = principais()
    opt = opcoes()

    c1, c2, c3 = st.columns(3)
    with c1:
        p["nome"] = st.text_input("Nome da embarcacao", value=p.get("nome", ""))
        p["LPP"] = st.number_input("LPP - comprimento entre perpendiculares (m)",
                                   value=float(p.get("LPP", 0.0)), min_value=0.0,
                                   step=0.1, format="%.4f")
    with c2:
        p["B"] = st.number_input("B - boca (m)", value=float(p.get("B", 0.0)),
                                 min_value=0.0, step=0.1, format="%.4f")
        p["D"] = st.number_input("D - pontal (m)", value=float(p.get("D", 0.0)),
                                 min_value=0.0, step=0.1, format="%.4f")
    with c3:
        p["Td"] = st.number_input("Td - calado de projeto (m)",
                                  value=float(p.get("Td", 0.0)), min_value=0.0,
                                  step=0.1, format="%.4f")
        opt["rho"] = st.number_input(
            "rho - densidade da agua (t/m3)", value=float(opt.get("rho", 1.025)),
            min_value=0.100, max_value=2.000, step=0.001, format="%.4f",
            help="Agua salgada cerca de 1,025 | agua doce 1,000. "
                 "E um dado de entrada: muda o deslocamento e o TPC, nao o volume.")

    with st.expander("Convencoes de calculo (padroes ja adequados na maioria dos casos)"):
        c1, c2 = st.columns(2)
        with c1:
            opt["origem_x"] = st.selectbox(
                "Como apresentar LCB e LCF",
                ["tabela", "pp_re", "meia_nau"],
                index=["tabela", "pp_re", "meia_nau"].index(opt.get("origem_x", "tabela")),
                format_func=lambda k: {"tabela": "x como esta no arquivo",
                                       "pp_re": "x = 0 na perpendicular de re",
                                       "meia_nau": "x = 0 na meia-nau"}[k],
                help="Muda apenas a apresentacao. O calculo interno usa sempre o x do arquivo.")
            st.caption(origem_texto(opt))
            opt["L_ref"] = st.selectbox(
                "Comprimento L dos coeficientes", ["LPP", "LWL"],
                index=0 if opt.get("L_ref") == "LPP" else 1,
                format_func=lambda k: {"LPP": "LPP informado acima",
                                       "LWL": "comprimento na linha d'agua"}[k])
        with c2:
            opt["B_ref"] = st.selectbox(
                "Boca B dos coeficientes", ["BWL", "B"],
                index=0 if opt.get("B_ref") == "BWL" else 1,
                format_func=lambda k: {"BWL": "boca na linha d'agua (calculada)",
                                       "B": "boca informada acima"}[k])
            opt["eixo_IL"] = st.selectbox(
                "Eixo de referencia para I_l (usado em BM_l)", ["LCF", "meia_nau"],
                index=0 if opt.get("eixo_IL") == "LCF" else 1,
                format_func=lambda k: {"LCF": "eixo transversal pelo LCF (padrao)",
                                       "meia_nau": "eixo transversal pela meia-nau"}[k],
                help="BM_l e definido em relacao ao eixo que passa pelo centro de flutuacao. "
                     "A opcao pela meia-nau serve so para comparacao.")
            opt["volume_adotado"] = st.selectbox(
                "Volume adotado nas propriedades derivadas",
                ["longitudinal", "vertical", "media"],
                index=["longitudinal", "vertical", "media"].index(
                    opt.get("volume_adotado", "longitudinal")),
                help="O aplicativo calcula o volume por dois caminhos independentes e "
                     "compara. Aqui voce escolhe qual deles alimenta Delta, BM e os "
                     "coeficientes.")

    botao_proximo("2. Tabela de cotas")
