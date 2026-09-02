# -*- coding: utf-8 -*-
"""Etapa 6: Hydrostatic Table e Hydrostatic Curves."""

import numpy as np
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt

import hidro as H
from .comum import (W, exige_completa, botao_proximo, calado_maximo,
                    numero_seguro, slider_seguro, rerodar)


def _coluna_T(df):
    return [c for c in df.columns if c.startswith("T (calado)")][0]


def _calcular():
    tab = st.session_state.tab
    opt = st.session_state.opt
    Tmax_d = calado_maximo()

    st.caption(f"O calculo e repetido para uma sequencia de calados. A tabela de cotas "
               f"cobre ate T = {H.fmt(Tmax_d)} m.")
    if Tmax_d < 1e-6:
        st.error("A altura coberta pela tabela e praticamente nula. Volte a etapa 2 e "
                 "corrija as alturas das linhas d'agua.")
        return

    c1, c2, c3 = st.columns(3)
    with c1:
        Tmin = numero_seguro("Calado inicial (m)", 0.001, Tmax_d,
                             max(Tmax_d / 10, 0.001), passo=0.05, key="ht_tmin")
    with c2:
        Tmax = numero_seguro("Calado final (m)", 0.002, Tmax_d, Tmax_d,
                             passo=0.05, key="ht_tmax")
    with c3:
        dT = numero_seguro("Passo entre calados (m)", 0.001, max(Tmax_d, 0.002),
                           max(Tmax_d / 20, 0.01), passo=0.05, key="ht_dt")

    if Tmax <= Tmin:
        st.error("O calado final precisa ser maior que o inicial.")
        return
    n_prev = int(np.floor((Tmax - Tmin) / dT + 1e-9)) + 1
    if n_prev < 3:
        st.warning(f"Com esses valores sairiam apenas {n_prev} calado(s). Curvas precisam de "
                   "varios pontos: diminua o passo ou amplie a faixa.")
    else:
        st.info(f"Serao calculados {n_prev} calados.")

    if st.button("Calcular a Hydrostatic Table", type="primary", **W()):
        barra = st.progress(0.0)
        with st.spinner("Percorrendo a faixa de calados..."):
            df_ht, brutos = H.tabela_hidrostatica(tab, Tmin, Tmax, dT, opt, barra)
        barra.empty()
        if not len(df_ht):
            st.error("Nenhum calado valido foi calculado. Reveja a faixa escolhida.")
            return
        st.session_state.df_ht = df_ht
        st.session_state.brutos_ht = brutos
        st.session_state["ht_params"] = (Tmin, Tmax, dT)
        H.registrar("Etapa 6", f"Hydrostatic Table calculada para {len(df_ht)} calados "
                               f"({H.fmt(Tmin)} a {H.fmt(Tmax)} m, passo {H.fmt(dT)} m).",
                    autor="usuario")
        rerodar()


def _verificar(df_ht):
    checagens = []
    for chave, esperado in [("VOL", "crescente"), ("DESL", "crescente"),
                            ("AWP", "nao decrescente"), ("KB", "crescente"),
                            ("TPC", "nao decrescente")]:
        col = f"{H.PROPRIEDADES[chave][0]} [{H.PROPRIEDADES[chave][1]}]"
        if col not in df_ht.columns:
            continue
        v = df_ht[col].to_numpy(float)
        if len(v) < 2:
            continue
        d = np.diff(v)
        ok = np.all(d > -1e-9) if esperado == "crescente" else \
            np.all(d > -1e-6 * max(np.nanmax(np.abs(v)), 1))
        checagens.append({"Curva": f"T x {H.PROPRIEDADES[chave][0]}",
                          "Esperado": esperado, "Situacao": "OK" if ok else "INCOERENTE"})
    return pd.DataFrame(checagens)


def render():
    st.title("6. Tabela e curvas")
    if not exige_completa():
        return
    tab = st.session_state.tab
    opt = st.session_state.opt

    a1, a2, a3, a4 = st.tabs(["Hydrostatic Table", "Curvas", "Diagrama combinado",
                              "Consultar um calado"])

    with a1:
        _calcular()
        df_ht = st.session_state.df_ht
        if df_ht is not None and len(df_ht):
            st.dataframe(df_ht.style.format("{:.4f}"), height=430, **W())
            c1, c2 = st.columns(2)
            with c1:
                xls = H.excel_hydrostatic_table(df_ht, tab, st.session_state.principais,
                                                H.historico_df(),
                                                pd.DataFrame(st.session_state.interp_regs))
                st.download_button("Baixar em Excel (.xlsx)", xls, "hydrostatic_table.xlsx",
                                   "application/vnd.openxmlformats-officedocument."
                                   "spreadsheetml.sheet", **W())
            with c2:
                st.download_button("Baixar em CSV", df_ht.to_csv(index=False, sep=";",
                                                                 decimal=",").encode("utf-8-sig"),
                                   "hydrostatic_table.csv", "text/csv", **W())

            st.markdown("#### Comportamento das curvas")
            dfc = _verificar(df_ht)
            if len(dfc):
                st.dataframe(dfc, hide_index=True, **W())
                if (dfc["Situacao"] == "INCOERENTE").any():
                    st.warning("Alguma curva nao segue o comportamento fisico esperado. "
                               "Isso aponta problema na tabela de cotas, e nao no metodo de "
                               "integracao. Reveja a etapa 3 antes de usar estes resultados.")
                else:
                    st.success("Todas as curvas verificadas seguem o comportamento esperado.")

    df_ht = st.session_state.df_ht
    faltando = df_ht is None or not len(df_ht)

    with a2:
        if faltando:
            st.info("Calcule a Hydrostatic Table na primeira aba.")
        else:
            escolhidas = st.multiselect("Curvas a exibir", H.CURVAS_OBRIGATORIAS,
                                        default=H.CURVAS_OBRIGATORIAS,
                                        format_func=lambda k: f"T x {H.PROPRIEDADES[k][0]}")
            if escolhidas:
                fig = H.plot_curvas(df_ht, escolhidas)
                st.pyplot(fig, **W())
                st.download_button("Baixar as curvas (PNG)", H.fig_para_png(fig),
                                   "hydrostatic_curves.png", "image/png")
                st.session_state["img_curvas"] = H.fig_para_b64(fig)
            st.caption("Calado no eixo vertical, como e usual em arquitetura naval.")

    with a3:
        if faltando:
            st.info("Calcule a Hydrostatic Table na primeira aba.")
        else:
            fig = H.plot_diagrama_combinado(df_ht)
            st.pyplot(fig, **W())
            st.download_button("Baixar o diagrama (PNG)", H.fig_para_png(fig),
                               "diagrama_hidrostatico.png", "image/png")
            st.session_state["img_combinado"] = H.fig_para_b64(fig)
            st.caption("Cada curva foi dividida pelo proprio maximo para caber no mesmo "
                       "eixo; o fator de escala aparece na legenda.")

    with a4:
        if faltando:
            st.info("Calcule a Hydrostatic Table na primeira aba.")
        else:
            colT = _coluna_T(df_ht)
            Ts = df_ht[colT].to_numpy(float)
            if len(Ts) < 2:
                st.warning("A Hydrostatic Table tem um unico calado, entao nao ha o que "
                           "interpolar. Volte a primeira aba e amplie a faixa ou reduza o "
                           "passo.")
                st.dataframe(df_ht.T, **W())
            else:
                Tq = slider_seguro("Calado de consulta (m)", Ts.min(), Ts.max(),
                                   float(np.median(Ts)), key="consulta_T",
                                   ajuda="Interpolacao linear entre os calados calculados.")
                saida = H.consultar_curva(df_ht, Tq)
                st.dataframe(pd.DataFrame([{"Propriedade": k, "Valor": v}
                                           for k, v in saida.items()]),
                             hide_index=True, height=520, **W())

    botao_proximo("7. Validacao")
