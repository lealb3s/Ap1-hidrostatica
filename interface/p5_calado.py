# -*- coding: utf-8 -*-
"""Etapa 5: propriedades hidrostaticas em um calado, com a memoria de calculo."""

import numpy as np
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt

import hidro as H
from .comum import W, exige_completa, botao_proximo, origem_texto


def resumo_df(r, tab, opt) -> pd.DataFrame:
    linhas = []
    for chave, (rot, uni, casas) in H.PROPRIEDADES.items():
        if chave not in r:
            continue
        v = r[chave]
        if chave in ("LCB", "LCF"):
            v = H.converter_origem(v, tab, opt.get("origem_x", "tabela"))
        linhas.append({"Propriedade": rot, "Valor": v, "Unidade": uni})
    return pd.DataFrame(linhas)


def _mostrar_calculo(chave, r, tab, opt, T):
    rot, uni, casas = H.PROPRIEDADES[chave]
    v, pw = r["_vol"], r["_pw"]
    st.markdown(f"### {rot}   [{uni}]")

    if chave in ("VOL_L", "VOL", "LCB"):
        st.markdown("**Dados usados:** area seccional A(x) de cada baliza no calado atual.")
        st.latex(r"\nabla_L=\int A(x)\,dx \approx \sum a_i A_i \qquad "
                 r"LCB=\frac{\sum a_i A_i x_i}{\nabla}")
        st.dataframe(v["df_L"], hide_index=True, **W())
        st.markdown(f"**Auditoria:** `{H.auditoria_texto(v['aud_L'])}`")
        st.markdown(f"**Resultado:** Vol_L = **{H.fmt(v['VOL_L'])} m3**  |  "
                    f"LCB = {H.fmt(np.sum(v['df_L']['a_i * A * x']))} / {H.fmt(v['VOL_L'])} = "
                    f"**{H.fmt(H.converter_origem(v['LCB'], tab, opt['origem_x']))} m** "
                    f"({origem_texto(opt)})")

    elif chave in ("VOL_V", "KB", "E_VOL"):
        st.markdown("**Dados usados:** area do plano d'agua em cada linha d'agua ate o calado.")
        st.latex(r"\nabla_V=\int_0^T A_{WP}(z)\,dz \qquad KB=\frac{\int_0^T z A_{WP}\,dz}{\nabla_V}")
        st.dataframe(v["df_V"], hide_index=True, **W())
        st.markdown(f"**Auditoria:** `{H.auditoria_texto(v['aud_V'])}`")
        st.markdown(f"**Resultado:** Vol_V = **{H.fmt(v['VOL_V'])} m3**  |  "
                    f"KB = **{H.fmt(v['KB'], 4)} m**  |  E_vol = **{H.fmt(v['E_VOL'], 4)} %**")

    elif chave in ("AWP", "LCF", "IT", "IL", "TPC", "CWP"):
        st.markdown("**Dados usados:** meia-boca de cada baliza na altura do calado.")
        st.latex(r"A_{WP}=2\int y\,dx \quad LCF=\frac{\int 2xy\,dx}{A_{WP}} \quad "
                 r"I_t=\frac{2}{3}\int y^3 dx \quad I_l=\int 2x^2y\,dx-A_{WP}LCF^2")
        st.dataframe(pw["df"], hide_index=True, **W())
        st.markdown(f"**Auditoria:** `{H.auditoria_texto(pw['aud'])}`")
        st.markdown(
            f"**Resultado:** A_WP = **{H.fmt(r['AWP'])} m2**  |  "
            f"LCF = **{H.fmt(H.converter_origem(r['LCF'], tab, opt['origem_x']))} m**  |  "
            f"I_t = **{H.fmt(r['IT'])} m4**  |  I_l = **{H.fmt(r['IL'])} m4** "
            f"({pw['eixo_IL']})  |  TPC = **{H.fmt(r['TPC'], 4)} t/cm**")

    elif chave == "WSA":
        st.markdown("**Dados usados:** contorno submerso de cada baliza.")
        st.latex(r"s_i=y_i(z_{base})+\sum\sqrt{\Delta y^2+\Delta z^2}\qquad WSA=2\int s\,dx")
        st.dataframe(r["_wsa_df"], hide_index=True, **W())
        st.markdown(f"**Resultado:** WSA = **{H.fmt(r['WSA'])} m2**")
        st.caption("Nao inclui popa espelhada, apendices, leme nem helice.")

    elif chave in ("BMT", "KMT", "BML", "KML"):
        st.latex(r"BM_t=\frac{I_t}{\nabla}\quad KM_t=KB+BM_t\quad "
                 r"BM_l=\frac{I_l}{\nabla}\quad KM_l=KB+BM_l")
        st.markdown(
            f"I_t = {H.fmt(r['IT'])} m4  |  I_l = {H.fmt(r['IL'])} m4  |  "
            f"Vol = {H.fmt(r['VOL'])} m3  |  KB = {H.fmt(r['KB'], 4)} m\n\n"
            f"BM_t = **{H.fmt(r['BMT'], 4)} m**  |  KM_t = **{H.fmt(r['KMT'], 4)} m**  |  "
            f"BM_l = **{H.fmt(r['BML'], 4)} m**  |  KM_l = **{H.fmt(r['KML'], 4)} m**")

    elif chave == "DESL":
        st.latex(r"\Delta=\rho\nabla")
        st.markdown(f"Delta = {H.fmt(r['rho'], 4)} x {H.fmt(r['VOL'])} = "
                    f"**{H.fmt(r['DESL'])} t**")

    elif chave in ("CB", "CM", "CP", "AM", "BWL", "LWL"):
        st.latex(r"C_B=\frac{\nabla}{LBT}\quad C_{WP}=\frac{A_{WP}}{LB}\quad "
                 r"C_M=\frac{A_M}{BT}\quad C_P=\frac{\nabla}{A_M L}")
        st.markdown(
            f"L = {H.fmt(r['L_usado'])} m ({opt['L_ref']})  |  B = {H.fmt(r['B_usado'])} m "
            f"({opt['B_ref']})  |  T = {H.fmt(T)} m  |  A_M = {H.fmt(r['AM'])} m2 "
            f"(baliza {tab.rotulos[r['i_AM']]})\n\n"
            f"C_B = **{H.fmt(r['CB'], 4)}**  |  C_WP = **{H.fmt(r['CWP'], 4)}**  |  "
            f"C_M = **{H.fmt(r['CM'], 4)}**  |  C_P = **{H.fmt(r['CP'], 4)}**")
        dif = abs(r["CB"] - r["CM"] * r["CP"])
        if np.isfinite(dif) and dif > 1e-4:
            st.warning(f"C_B difere de C_M x C_P em {H.fmt(dif, 6)}. Como as quatro "
                       "definicoes usam o mesmo L, B e T, a identidade deveria ser exata.")
        else:
            st.success(f"Verificacao C_B = C_M x C_P satisfeita "
                       f"({H.fmt(r['CB'], 5)} = {H.fmt(r['CM'] * r['CP'], 5)}).")

    else:
        st.markdown("**Dados usados:** meias-bocas da baliza do fundo ate o calado.")
        st.latex(r"A_i(T)=2\int_0^T y(x_i,z)\,dz \approx 2\sum a_j y_j")
        i = st.selectbox("Baliza", list(range(tab.n_est)),
                         format_func=lambda i: f"{tab.rotulos[i]}  (x = {H.fmt(tab.x[i], 2)} m)",
                         key="baliza_detalhe")
        det = v["det_A"][i]
        c1, c2 = st.columns([1.4, 1])
        with c1:
            st.dataframe(det["df"], hide_index=True, **W())
            st.markdown(f"**Auditoria:** `{H.auditoria_texto(det['aud'])}`")
            st.markdown(f"**Resultado:** A = 2 x {H.fmt(det['meia_area'])} = "
                        f"**{H.fmt(det['area'])} m2**")
        with c2:
            fig = H.plot_secao(tab, i, T)
            st.pyplot(fig, **W())
            plt.close(fig)


def render():
    st.title("5. Resultados no calado")
    if not exige_completa():
        return
    tab = st.session_state.tab
    opt = st.session_state.opt
    T = float(st.session_state.get("T_sel") or 0.0)

    if T <= 1e-9:
        st.info("Escolha um calado maior que zero no slider da barra lateral.")
        return

    st.caption(f"Calado T = {H.fmt(T)} m, medido a partir da linha de base z = "
               f"{H.fmt(H.z_base(tab))} m. Ajuste na barra lateral.")

    with st.spinner("Calculando..."):
        r = H.hidrostatica(tab, T, opt)
    st.session_state["r_atual"] = r

    c = st.columns(6)
    for col, (k, rot) in zip(c, [("VOL", "Volume"), ("DESL", "Deslocamento"),
                                 ("AWP", "A_WP"), ("KB", "KB"), ("KMT", "KM_t"),
                                 ("TPC", "TPC")]):
        _, uni, casas = H.PROPRIEDADES[k]
        col.metric(f"{rot} [{uni}]", H.fmt(r[k], casas))
    c = st.columns(6)
    for col, (k, rot) in zip(c, [("LCB", "LCB"), ("LCF", "LCF"), ("BMT", "BM_t"),
                                 ("BML", "BM_l"), ("CB", "C_B"), ("WSA", "WSA")]):
        _, uni, casas = H.PROPRIEDADES[k]
        v = H.converter_origem(r[k], tab, opt["origem_x"]) if k in ("LCB", "LCF") else r[k]
        col.metric(f"{rot} [{uni}]", H.fmt(v, casas))
    st.caption(f"LCB e LCF apresentados com {origem_texto(opt)}.")

    a1, a2, a3, a4 = st.tabs(["Todas as propriedades", "Conferencia do volume",
                              "Areas seccionais", "Mostrar calculo"])

    with a1:
        st.dataframe(resumo_df(r, tab, opt), hide_index=True, height=560, **W())

    with a2:
        st.caption("O volume e obtido por dois caminhos independentes. A diferenca entre "
                   "eles mede a qualidade da malha.")
        c1, c2, c3 = st.columns(3)
        c1.metric("Vol longitudinal [m3]", H.fmt(r["VOL_L"]))
        c2.metric("Vol vertical [m3]", H.fmt(r["VOL_V"]))
        c3.metric("Diferenca [%]", H.fmt(r["E_VOL"], 4))
        E = r["E_VOL"]
        if not np.isfinite(E):
            texto = "Nao foi possivel comparar os dois caminhos."
            st.error(texto)
        elif E < 0.5:
            texto = (f"Diferenca de {H.fmt(E, 4)} %, compativel com o erro de discretizacao "
                     "das duas integracoes. A malha descreve a carena de forma coerente.")
            st.success(texto)
        elif E < 2.0:
            texto = (f"Diferenca de {H.fmt(E, 4)} %. Costuma vir de poucas linhas d'agua "
                     "perto do fundo, de mudanca brusca de forma nas extremidades ou do "
                     "trecho parcial ate o calado escolhido.")
            st.warning(texto)
        else:
            texto = (f"Diferenca de {H.fmt(E, 4)} %. Os dois caminhos deveriam dar o mesmo "
                     "volume; uma divergencia desse tamanho aponta malha insuficiente, "
                     "hipotese inadequada no fundo ou erro na tabela de cotas. Deslocamento, "
                     "KB, BM e os coeficientes herdam esse erro.")
            st.error(texto)
        st.session_state["interp_evol"] = texto

    with a3:
        A = r["_vol"]["A"]
        df_areas = pd.DataFrame({
            "Baliza": tab.rotulos,
            "x (m)": [H.converter_origem(v, tab, opt["origem_x"]) for v in tab.x],
            "A_i (m2)": A})
        st.session_state["df_areas"] = df_areas
        c1, c2 = st.columns([1.7, 1])
        with c1:
            fig = H.plot_areas_seccionais(tab, A, T, opt["origem_x"])
            st.pyplot(fig, **W())
            st.session_state["img_areas"] = H.fig_para_b64(fig)
        with c2:
            st.dataframe(df_areas, hide_index=True, height=360, **W())

    with a4:
        st.caption("Dados usados, formula, valores intermediarios, resultado e unidade.")
        chave = st.selectbox("Propriedade", list(H.PROPRIEDADES.keys()),
                             format_func=lambda k: H.PROPRIEDADES[k][0], index=2)
        with st.container(border=True):
            _mostrar_calculo(chave, r, tab, opt, T)

    botao_proximo("6. Tabela e curvas")
