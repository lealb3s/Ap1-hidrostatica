# -*- coding: utf-8 -*-
"""
Etapa 9: equilibrio longitudinal, trim e lamina d'agua.
Cobre os Modulos 10, 11, 12 e 13 do AP1.2.
"""

import numpy as np
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt

import hidro as H
from .comum import (W, exige_completa, botao_proximo, opcoes, origem_texto,
                    principais)


def render():
    st.title("9. Equilibrio e trim")
    if not exige_completa():
        return
    tab = st.session_state.tab
    opt = opcoes()
    df_ht = st.session_state.get("df_ht")

    # O somatorio e refeito aqui a partir dos itens de peso, e nao herdado da tela
    # anterior: assim esta pagina funciona mesmo que o usuario venha direto para
    # ela, e o resultado nunca fica preso a uma versao antiga da condicao.
    carga = st.session_state.get("carga")
    soma = None
    if carga is not None and len(carga):
        erros = [a for a in H.validar_condicao(carga, tab, principais())
                 if a.nivel == "ERRO"]
        if erros:
            st.error("A condicao de carga tem erro que impede o calculo: "
                     + "; ".join(a.titulo for a in erros) +
                     ". Volte a **etapa 8** para corrigir.")
            return
        soma = H.somatorio(carga)
        st.session_state["soma"] = soma

    if soma is None or not np.isfinite(soma.get("delta", np.nan)) or soma["delta"] <= 0:
        st.warning("Monte a condicao de carga na **etapa 8** antes de calcular o "
                   "equilibrio: sem deslocamento nao ha calado.")
        return
    if df_ht is None or not len(df_ht):
        st.warning("A Hydrostatic Table ainda nao foi calculada. Va a **etapa 6**, "
                   "gere a tabela, e volte aqui: e nela que o calado correspondente ao "
                   "deslocamento e localizado.")
        return

    c1, c2 = st.columns([1, 2])
    with c1:
        modo = st.radio("Forma do MTC", ["aproximado", "exato"],
                        format_func=lambda k: {"aproximado": "Aproximado (com BM_l)",
                                               "exato": "Exato (com GM_l)"}[k])
        refinar = st.checkbox("Refinar T0 por busca direta", value=True,
                              help="Alem de interpolar na Hydrostatic Table, resolve "
                                   "rho x Vol(T) = Delta no proprio nucleo. Mostra "
                                   "quanto a interpolacao custou em precisao.")
    with c2:
        if modo == "aproximado":
            st.caption("MTC = Delta x BM_l / (100 L). Dispensa o KG e e a forma "
                       "admitida por padrao pelo enunciado.")
        else:
            st.caption("MTC = Delta x GM_l / (100 L), com GM_l = KM_l - KG corrigido. "
                       "Mais correta, mas so existe porque a condicao de carga "
                       "forneceu o KG.")

    try:
        eq = H.equilibrio(tab, opt, soma, df_ht, modo_mtc=modo, refinar=refinar)
    except Exception as e:                                           # noqa: BLE001
        st.error(f"Nao foi possivel calcular o equilibrio: {e}")
        return
    st.session_state["eq"] = eq

    if eq["busca"]["extrapolou"]:
        st.error(
            f"O deslocamento da condicao ({H.fmt(eq['delta'], 3)} t) esta **fora** da "
            f"faixa da Hydrostatic Table, que vai de {H.fmt(eq['busca']['D_min'], 3)} a "
            f"{H.fmt(eq['busca']['D_max'], 3)} t. O calado foi extrapolado e nao tem "
            "base nos dados. Volte a etapa 6 e amplie a faixa de calados.")

    c = st.columns(6)
    c[0].metric("Delta [t]", H.fmt(eq["delta"], 3))
    c[1].metric("T0 [m]", H.fmt(eq["T0"], 4))
    c[2].metric("Calado na popa Ta [m]", H.fmt(eq["Ta"], 4))
    c[3].metric("Calado na proa Tf [m]", H.fmt(eq["Tf"], 4))
    c[4].metric("Compasso t [cm]", H.fmt(eq["t_cm"], 2))
    c[5].metric("Angulo [graus]", H.fmt(eq["theta"], 3))
    st.info(f"**{eq['sentido'].capitalize()}.** LCG = {H.fmt(eq['LCG'], 4)} m e LCB = "
            f"{H.fmt(eq['LCB'], 4)} m, uma diferenca de "
            f"{H.fmt(eq['LCG'] - eq['LCB'], 4)} m. "
            + ("Com o centro de gravidade a vante do centro de carena, o navio afunda "
               "a proa." if eq["M_trim"] > 0 else
               "Com o centro de gravidade a re do centro de carena, o navio afunda a "
               "popa." if eq["M_trim"] < 0 else
               "Os dois coincidem, entao o navio flutua em quilha paralela."))

    a1, a2, a3, a4 = st.tabs(["Lamina d'agua", "Tabela de resultados",
                              "Auditoria do calculo", "Exportar"])

    # --- Modulo 12 ---------------------------------------------------------
    with a1:
        mostrar = st.checkbox("Marcar LCF, LCB e LCG no desenho", value=True)
        try:
            fig = H.plot_lamina_dagua(tab, eq, opt.get("origem_x", "tabela"), mostrar)
            st.pyplot(fig, **W())
            st.download_button("Baixar a lamina d'agua (PNG)", H.fig_para_png(fig),
                               "lamina_dagua.png", "image/png")
            st.session_state["img_lamina"] = H.fig_para_b64(fig)
        except Exception as e:                                       # noqa: BLE001
            st.error(f"Nao foi possivel desenhar a lamina d'agua: {e}")
        st.caption("A linha e tracada entre os pontos (AP, Ta) e (FP, Tf) calculados. "
                   "Mudar qualquer peso, LCG, VCG ou a densidade na etapa 8 refaz o "
                   "desenho automaticamente.")

    # --- tabela-resumo -----------------------------------------------------
    with a2:
        dfr = H.tabela_resultado(eq, soma, st.session_state.get("nome_condicao", ""))
        st.session_state["df_resultado_carga"] = dfr
        mostra = H.resultado_para_exibir(dfr)
        for grupo in mostra["Grupo"].unique():
            st.markdown(f"**{grupo}**")
            st.dataframe(mostra[mostra["Grupo"] == grupo][["Grandeza", "Valor",
                                                           "Unidade"]],
                         hide_index=True, **W())

    # --- Modulo 13 ---------------------------------------------------------
    with a3:
        st.markdown("#### De onde veio cada numero")
        st.markdown("**1. Deslocamento da condicao de carga**")
        st.markdown(f"Delta = soma dos pesos = **{H.fmt(eq['delta'], 3)} t** "
                    f"(etapa 8, {soma.get('n_itens', '-')} itens)")

        st.markdown("**2. Calado correspondente, na Hydrostatic Table**")
        b = eq["busca"]
        st.markdown(
            f"Interpolacao linear entre as linhas Delta = {H.fmt(b['D_inf'], 3)} t "
            f"(T = {H.fmt(b['T_inf'], 4)} m) e Delta = {H.fmt(b['D_sup'], 3)} t "
            f"(T = {H.fmt(b['T_sup'], 4)} m) &rarr; **T0 = {H.fmt(b['T0'], 4)} m**")
        if eq["refino"]:
            rf = eq["refino"]
            dif = abs(rf["T"] - b["T0"])
            st.markdown(
                f"Refinamento por busca direta: {rf['iteracoes']} iteracoes, "
                f"**T0 = {H.fmt(rf['T'], 4)} m** "
                f"(deslocamento obtido {H.fmt(rf['delta_obtido'], 3)} t). "
                f"A interpolacao da tabela diferiu em {H.fmt(dif, 5)} m.")

        st.markdown("**3. Hidrostatica nesse calado**, calculada pelo nucleo do AP1.1")
        st.markdown(
            f"LCB = {H.fmt(eq['LCB'], 4)} m &nbsp; LCF = {H.fmt(eq['LCF'], 4)} m "
            f"&nbsp; BM_l = {H.fmt(eq['BML'], 3)} m &nbsp; KM_l = {H.fmt(eq['KML'], 3)} m "
            f"&nbsp; KM_t = {H.fmt(eq['KMT'], 4)} m")
        if np.isfinite(eq["GML"]):
            st.markdown(f"GM_l = KM_l - KG = {H.fmt(eq['KML'], 3)} - "
                        f"{H.fmt(eq['KG'], 4)} = **{H.fmt(eq['GML'], 3)} m** &nbsp;&nbsp; "
                        f"GM_t = {H.fmt(eq['GMT'], 4)} m")

        st.markdown("**4. MTC**")
        if eq["modo_mtc"] == "aproximado":
            st.latex(r"MTC=\frac{\Delta\,BM_l}{100\,L}")
            st.markdown(f"MTC = ({H.fmt(eq['delta'], 3)} x {H.fmt(eq['BML'], 3)}) / "
                        f"(100 x {H.fmt(eq['L'], 3)}) = **{H.fmt(eq['MTC'], 4)} t.m/cm**")
        else:
            st.latex(r"MTC=\frac{\Delta\,GM_l}{100\,L}")
            st.markdown(f"MTC = ({H.fmt(eq['delta'], 3)} x {H.fmt(eq['GML'], 3)}) / "
                        f"(100 x {H.fmt(eq['L'], 3)}) = **{H.fmt(eq['MTC'], 4)} t.m/cm**")

        st.markdown("**5. Momento de trim e compasso**")
        st.latex(r"M_{trim}=\Delta\,(LCG-LCB) \qquad t=\frac{M_{trim}}{MTC}")
        st.markdown(
            f"M_trim = {H.fmt(eq['delta'], 3)} x ({H.fmt(eq['LCG'], 4)} - "
            f"{H.fmt(eq['LCB'], 4)}) = **{H.fmt(eq['M_trim'], 3)} t.m**  \n"
            f"t = {H.fmt(eq['M_trim'], 3)} / {H.fmt(eq['MTC'], 4)} = "
            f"**{H.fmt(eq['t_cm'], 3)} cm** = {H.fmt(eq['t_m'], 5)} m")

        st.markdown("**6. Calados nas perpendiculares**")
        st.latex(r"T_a=T_0-\frac{LCF-x_{AP}}{L}\,t \qquad "
                 r"T_f=T_0+\frac{x_{FP}-LCF}{L}\,t")
        st.markdown(
            f"O navio gira em torno do LCF, e nao da meia-nau: o calado no LCF "
            f"permanece igual a T0.  \n"
            f"Braco ate a popa = LCF - x_AP = {H.fmt(eq['LCF'], 4)} - "
            f"{H.fmt(eq['xa'], 4)} = {H.fmt(eq['braco_re'], 4)} m  \n"
            f"Braco ate a proa = x_FP - LCF = {H.fmt(eq['xf'], 4)} - "
            f"{H.fmt(eq['LCF'], 4)} = {H.fmt(eq['braco_vante'], 4)} m  \n"
            f"Ta = {H.fmt(eq['T0'], 4)} - ({H.fmt(eq['braco_re'], 4)}/"
            f"{H.fmt(eq['L'], 3)}) x {H.fmt(eq['t_m'], 5)} = **{H.fmt(eq['Ta'], 4)} m**  \n"
            f"Tf = {H.fmt(eq['T0'], 4)} + ({H.fmt(eq['braco_vante'], 4)}/"
            f"{H.fmt(eq['L'], 3)}) x {H.fmt(eq['t_m'], 5)} = **{H.fmt(eq['Tf'], 4)} m**")

        st.markdown("**7. Conferencias**")
        d1 = abs((eq["Tf"] - eq["Ta"]) - eq["t_m"])
        st.markdown(f"Tf - Ta = {H.fmt(eq['Tf'] - eq['Ta'], 6)} m deve ser igual ao "
                    f"compasso {H.fmt(eq['t_m'], 6)} m &rarr; diferenca "
                    f"{d1:.2e} m")
        media = 0.5 * (eq["Ta"] + eq["Tf"])
        st.markdown(f"Calado medio (Ta + Tf)/2 = {H.fmt(media, 4)} m. So coincide com "
                    f"T0 = {H.fmt(eq['T0'], 4)} m quando o LCF esta na meia-nau; aqui a "
                    f"diferenca e de {H.fmt(abs(media - eq['T0']), 4)} m.")
        st.caption("**Convencao de sinais adotada:** x cresce de re para vante, na mesma "
                   "referencia da tabela de cotas. Momento de trim positivo significa "
                   "LCG a vante do LCB, e portanto aproamento, com Tf maior que Ta.")
        st.caption(f"LCB, LCF e LCG mostrados aqui estao na referencia do arquivo. Na "
                   f"apresentacao escolhida na etapa 1 ({origem_texto(opt)}), o LCG "
                   f"seria {H.fmt(H.converter_origem(eq['LCG'], tab, opt['origem_x']), 4)} m.")

    with a4:
        xls = H.excel_condicao(st.session_state["carga"], soma, eq,
                               st.session_state.get("nome_condicao", ""))
        st.download_button("Baixar a condicao e o resultado (.xlsx)", xls,
                           "condicao_de_carga.xlsx",
                           "application/vnd.openxmlformats-officedocument."
                           "spreadsheetml.sheet", type="primary", **W())
        st.caption("Tres abas: o resultado por grupos, a condicao de carga com os "
                   "momentos recalculados, e a auditoria passo a passo.")

    botao_proximo("Relatorio final")
