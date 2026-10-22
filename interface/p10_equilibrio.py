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


def _assinatura_df(df):
    """Assinatura simples da Hydrostatic Table original da sessao."""
    if df is None or not len(df):
        return None
    try:
        return (tuple(df.columns.astype(str)),
                tuple(pd.util.hash_pandas_object(df, index=True).to_numpy(dtype=np.uint64)))
    except Exception:
        return (tuple(df.columns.astype(str)), len(df))


def _preparar_sequencia(df_ht_original):
    """Inicia/reinicia a cadeia quando a Hydrostatic Table original muda."""
    assinatura = _assinatura_df(df_ht_original)
    antiga = st.session_state.get("trim_assinatura_original")
    if assinatura != antiga:
        st.session_state["trim_assinatura_original"] = assinatura
        st.session_state["trim_df_ht_base"] = None
        st.session_state["trim_condicao_num"] = 1
        st.session_state["trim_historico"] = []


def render():
    st.title("9. Equilibrio e trim")
    if not exige_completa():
        return
    tab = st.session_state.tab
    opt = opcoes()
    df_ht_original = st.session_state.get("df_ht")
    _preparar_sequencia(df_ht_original)
    df_ht_base = st.session_state.get("trim_df_ht_base")
    df_ht = df_ht_base if df_ht_base is not None else df_ht_original
    numero_condicao = int(st.session_state.get("trim_condicao_num", 1))
    historico = st.session_state.get("trim_historico", [])

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

    st.info(
        f"**Condição {numero_condicao} — tabela-base usada:** "
        + ("Hydrostatic Table original da etapa 6." if numero_condicao == 1
           else f"tabela interpolada e finalizada da Condição {numero_condicao - 1}.")
    )
    if numero_condicao > 1:
        st.caption(
            "A tabela original continua preservada. Esta condição usa exclusivamente "
            "a tabela derivada da condição imediatamente anterior."
        )

    c1, c2 = st.columns([1, 2])
    with c1:
        modo = st.radio("Forma do MTC", ["aproximado", "exato"],
                        format_func=lambda k: {"aproximado": "Aproximado (com BM_l)",
                                               "exato": "Exato (com GM_l)"}[k])
    with c2:
        if modo == "aproximado":
            st.caption("MTC = Delta x BM_l / (100 L). O BM_l vem da interpolação "
                       "da Hydrostatic Table-base da condição.")
        else:
            st.caption("MTC = Delta x GM_l / (100 L), com GM_l = KM_l - KG corrigido. "
                       "KM_l também vem da interpolação da Hydrostatic Table-base.")

    try:
        eq = H.equilibrio(tab, opt, soma, df_ht, modo_mtc=modo, refinar=False,
                           referencia_lcg=opt.get("referencia_lcg", "ap"))
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
    st.info(f"**{eq['sentido'].capitalize()}.** LCG = {H.fmt(eq['LCG'], 4)} m | "
            f"LCB final = {H.fmt(eq['LCB_final'], 4)} m | "
            f"diferença final = {H.fmt(eq['LCB_final'] - eq['LCG'], 6)} m. "
            f"LCB(T0) = {H.fmt(eq['LCB_T0'], 4)} m foi usado apenas para obter a "
            f"estimativa inicial de trim por MTC. "
            + ("O equilibrio final foi fechado por volume e momento longitudinal."
               if eq.get("equilibrio_final_exato") else
               "O refinamento final nao convergiu completamente; confira a auditoria."))

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

        st.markdown("**2. Referencia longitudinal do LCG**")
        st.markdown(
            f"LCG informado = **{H.fmt(eq['LCG_informado'], 4)} m**; referencia escolhida = "
            f"**{eq['referencia_lcg']}**; LCG convertido para a referencia da tabela = "
            f"**{H.fmt(eq['LCG'], 4)} m**."
        )

        st.markdown("**3. Calado correspondente, na Hydrostatic Table**")
        b = eq["busca"]
        st.markdown(
            f"Interpolacao linear entre as linhas Delta = {H.fmt(b['D_inf'], 3)} t "
            f"(T = {H.fmt(b['T_inf'], 4)} m) e Delta = {H.fmt(b['D_sup'], 3)} t "
            f"(T = {H.fmt(b['T_sup'], 4)} m) &rarr; **T0 = {H.fmt(b['T0'], 4)} m**")
        st.markdown(
            "A condição usa somente interpolação linear na tabela-base. Não é feita "
            "uma nova busca de calado diretamente na geometria do casco.")

        st.markdown("**3. Hidrostatica em T0**, interpolada da tabela-base")
        st.markdown(
            f"LCB(T0) = {H.fmt(eq['LCB_T0'], 4)} m &nbsp; LCF(T0) = {H.fmt(eq['LCF'], 4)} m "
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

        st.markdown("**5. Momento de trim e estimativa inicial por MTC**")
        st.latex(r"M_{trim,0}=\Delta\,(LCG-LCB_{T0}) \qquad "
                 r"t_{MTC}=\frac{M_{trim,0}}{MTC}")
        st.markdown(
            f"M_trim,0 = {H.fmt(eq['delta'], 3)} x ({H.fmt(eq['LCG'], 4)} - "
            f"{H.fmt(eq['LCB_T0'], 4)}) = **{H.fmt(eq['M_trim'], 3)} t.m**  \n"
            f"t_MTC = **{H.fmt(eq['t_cm_mtc'], 3)} cm** = {H.fmt(eq['t_m_mtc'], 5)} m. "
            "Esse valor e usado como estimativa inicial, pois MTC usa hidrostatica de "
            "linha d'agua horizontal.")

        st.markdown("**6. Equilibrio final da lamina d'agua inclinada**")
        st.markdown(
            "A partir da estimativa por MTC, o aplicativo resolve simultaneamente "
            "<b>deslocamento = Delta</b> e <b>LCB final = LCG</b> para a linha d'agua "
            "inclinada. Portanto, Ta e Tf abaixo sao os calados da condicao final, "
            "e nao uma simples copia da aproximacao por MTC.", unsafe_allow_html=True)
        st.markdown(
            f"Ta = **{H.fmt(eq['Ta'], 4)} m**  \n"
            f"Tf = **{H.fmt(eq['Tf'], 4)} m**  \n"
            f"t final = Tf - Ta = **{H.fmt(eq['t_m'], 5)} m** = **{H.fmt(eq['t_cm'], 3)} cm**  \n"
            f"LCB final = **{H.fmt(eq['LCB_final'], 6)} m**  \n"
            f"LCG = **{H.fmt(eq['LCG'], 6)} m**  \n"
            f"erro LCB - LCG = **{H.fmt(eq['LCB_final'] - eq['LCG'], 8)} m**")

        st.markdown("**7. Conferencias**")
        d1 = abs((eq["Tf"] - eq["Ta"]) - eq["t_m"])
        st.markdown(f"Tf - Ta = {H.fmt(eq['Tf'] - eq['Ta'], 6)} m; compasso final = "
                    f"{H.fmt(eq['t_m'], 6)} m &rarr; diferenca {d1:.2e} m")
        st.markdown(f"LCB final - LCG = {H.fmt(eq['LCB_final'] - eq['LCG'], 10)} m. "
                    f"Momento residual final = {H.fmt(eq['M_residual_final'], 8)} t.m.")
        media = 0.5 * (eq["Ta"] + eq["Tf"])
        st.markdown(f"Calado medio geométrico (Ta + Tf)/2 = {H.fmt(media, 4)} m; "
                    f"T0 interpolado = {H.fmt(eq['T0'], 4)} m. A diferença é "
                    f"{H.fmt(abs(media - eq['T0']), 4)} m devido ao trim e à posição do LCF.")
        st.caption("**Convencao de sinais adotada:** x cresce de re para vante, na mesma "
                   "referencia da tabela de cotas. Momento de trim positivo significa "
                   "LCG a vante do LCB, e portanto aproamento, com Tf maior que Ta.")
        st.caption(f"LCB, LCF e LCG mostrados aqui estao na referencia do arquivo. Na "
                   f"apresentacao escolhida na etapa 1 ({origem_texto(opt)}), o LCG "
                   f"seria {H.fmt(H.converter_origem(eq['LCG'], tab, opt['origem_x']), 4)} m.")

    st.divider()
    st.subheader("Encadeamento das condições de carga")
    st.markdown(
        "Ao finalizar esta condição, o aplicativo cria **uma nova Hydrostatic Table "
        "por interpolação da tabela usada nesta condição**. Essa nova tabela passa "
        "a ser a única tabela-base da próxima condição.")

    if st.button(
        f"Finalizar Condição {numero_condicao} e usar sua tabela na próxima carga",
        type="primary", **W()
    ):
        try:
            nome = st.session_state.get("nome_condicao", "").strip() or f"Condição {numero_condicao}"
            nova_tabela = H.reinterpolar_tabela_hidrostatica(
                df_ht, [eq["T0"], eq["Ta"], eq["Tf"]]
            )
            registro = {
                "numero": numero_condicao,
                "nome": nome,
                "delta": eq["delta"],
                "T0": eq["T0"],
                "Ta": eq["Ta"],
                "Tf": eq["Tf"],
                    "LCG": eq["LCG"],
                "LCB": eq["LCB_final"],
                "LCF": eq.get("LCF_final", eq["LCF"]),
                "t_cm": eq["t_cm"],
                "tabela": nova_tabela.copy(),
            }
            historico = list(st.session_state.get("trim_historico", []))
            historico.append(registro)
            st.session_state["trim_historico"] = historico
            st.session_state["trim_df_ht_base"] = nova_tabela
            st.session_state["trim_condicao_num"] = numero_condicao + 1
            st.session_state["eq"] = None
            H.registrar(
                "Etapa 9",
                f"Condição {numero_condicao} finalizada; a tabela hidrostatica "
                f"interpolada passou a ser a base da Condição {numero_condicao + 1}.",
                autor="usuario",
            )
            st.success(
                f"Condição {numero_condicao} finalizada. A próxima condição usará "
                "a tabela hidrostatica recém-interpolada."
            )
            st.dataframe(nova_tabela, hide_index=True, **W())
        except Exception as e:
            st.error(f"Não foi possível preparar a tabela da próxima condição: {e}")

    if historico:
        st.markdown("#### Histórico da sequência")
        resumo_hist = pd.DataFrame([{
            "Condição": h["numero"], "Nome": h["nome"], "Delta (t)": h["delta"],
            "T0 (m)": h["T0"], "Ta (m)": h["Ta"], "Tf (m)": h["Tf"],
            "Trim (cm)": h["t_cm"],
        } for h in historico])
        st.dataframe(resumo_hist, hide_index=True, **W())

    if st.button("Reiniciar sequência e voltar à Hydrostatic Table original", **W()):
        st.session_state["trim_df_ht_base"] = None
        st.session_state["trim_condicao_num"] = 1
        st.session_state["trim_historico"] = []
        st.session_state["eq"] = None
        H.registrar("Etapa 9", "Sequência de condições reiniciada na Hydrostatic Table original.",
                    nivel="DECISAO", autor="usuario")
        st.rerun()

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
