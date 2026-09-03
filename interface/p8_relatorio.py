# -*- coding: utf-8 -*-
"""Relatorio final: um documento com tudo o que foi feito."""

import numpy as np
import pandas as pd
import streamlit as st

import hidro as H
from .comum import W, exige_tabela, origem_texto, principais, opcoes
from .p5_calado import resumo_df


def _pdf_bytes() -> bytes:
    """Gera o PDF uma unica vez e guarda o resultado."""
    if st.session_state.get("relatorio_pdf") is None:
        ctx = st.session_state.get("relatorio_ctx")
        if ctx is None:
            return b""
        try:
            st.session_state["relatorio_pdf"] = H.gerar_relatorio_pdf(ctx)
        except Exception as e:
            st.error(f"Nao foi possivel montar o PDF: {e}. O relatorio em HTML continua "
                     "disponivel e pode ser salvo como PDF pelo navegador.")
            st.session_state["relatorio_pdf"] = b""
    return st.session_state["relatorio_pdf"]


def render():
    st.title("Relatorio final")
    st.caption("Dados, interpretacao da tabela, problemas detectados, decisoes tomadas, "
               "interpolacoes, metodos de integracao, memoria de calculo, graficos, "
               "Hydrostatic Table, curvas, validacoes e historico completo.")
    if not exige_tabela():
        return

    if st.session_state.df_ht is not None and H.coluna_calado(st.session_state.df_ht) is None:
        st.session_state.df_ht = None
        st.warning("A Hydrostatic Table guardada era de uma versao anterior e foi "
                   "descartada. Refaca o calculo na etapa 6 para inclui-la no relatorio.")

    tab = st.session_state.tab
    opt = opcoes()
    completa = bool(np.isfinite(tab.Y).all())

    c1, c2, c3 = st.columns(3)
    c1.metric("Eventos no historico", len(st.session_state.get("hist", [])))
    c2.metric("Celulas interpoladas", tab.n_interpolados())
    c3.metric("Avisos ignorados", len(st.session_state.avisos_ignorados))

    c1, c2 = st.columns(2)
    with c1:
        inc_linhas = st.checkbox("Plano de linhas", value=True)
        inc_3d = st.checkbox("Casco 3D", value=True)
    with c2:
        inc_curvas = st.checkbox("Hydrostatic Curves",
                                 value=st.session_state.df_ht is not None)
        inc_calc = st.checkbox("Memoria de calculo do calado atual", value=True)

    if not completa:
        st.warning("A tabela ainda tem lacunas. O relatorio sai sem as secoes de calculo.")

    if st.button("Gerar o relatorio", type="primary", **W()):
        with st.spinner("Montando o relatorio..."):
            achados = st.session_state.get("achados")
            if achados is None:
                achados = H.diagnosticar(tab, principais())
            ctx = {
                "principais": {**principais(),
                               "densidade rho (t/m3)": opt.get("rho")},
                "tab": tab, "opt": opt, "unidade_origem": tab.unidade,
                "origem_txt": origem_texto(opt),
                "arquivo": st.session_state.arquivo_nome or "(entrada manual)",
                "aba": st.session_state.aba_sel or "-",
                "notas_deteccao": (st.session_state.deteccao.notas
                                   if st.session_state.deteccao else []),
                "tab_original_df": (st.session_state.tab_arquivo_df
                                    if st.session_state.tab_arquivo_df is not None
                                    else tab.como_df()),
                "achados": achados,
                "avisos_ignorados": st.session_state.avisos_ignorados,
                "interpolacoes": st.session_state.interp_regs,
                "aud_x": " ; ".join(f"estacoes {a}-{b}: {m}" for a, b, m in
                                    H.planejar_integracao(tab.x, opt["metodo_x"])),
                "aud_z": " ; ".join(f"WL {a}-{b}: {m}" for a, b, m in
                                    H.planejar_integracao(tab.z, opt["metodo_z"])),
                "historico": H.historico_df(),
                "df_ht": st.session_state.df_ht,
                "df_val_int": st.session_state.get("df_val_int"),
                "df_val_ana": st.session_state.get("df_val_ana"),
                "df_val_max": st.session_state.df_val_max,
                "interpretacao_evol": st.session_state.get("interp_evol", ""),
            }
            if st.session_state.get("ht_params"):
                ctx["Tmin"], ctx["Tmax"], ctx["dT"] = st.session_state["ht_params"]

            T = float(st.session_state.get("T_sel") or 0.0)
            if completa and inc_calc and T > 1e-9:
                r = st.session_state.get("r_atual")
                if r is None or abs(float(r.get("T", -1)) - T) > 1e-12:
                    r = H.hidrostatica(tab, T, opt)
                ctx["resultado"] = r
                ctx["LCF_apr"] = H.converter_origem(r["LCF"], tab, opt["origem_x"])
                ctx["df_resumo"] = resumo_df(r, tab, opt)
                df_ar = st.session_state.get("df_areas")
                if df_ar is None or not len(df_ar):
                    df_ar = pd.DataFrame({"Baliza": tab.rotulos, "x (m)": tab.x,
                                          "A_i (m2)": r["_vol"]["A"]})
                ctx["df_areas"] = df_ar
                ctx["img_areas"] = st.session_state.get("img_areas") or H.fig_para_b64(
                    H.plot_areas_seccionais(tab, r["_vol"]["A"], T, opt["origem_x"]))
            if inc_linhas:
                ctx["img_linhas"] = H.fig_para_b64(
                    H.plot_plano_de_linhas(tab, T if completa else None))
            if inc_3d and completa:
                ctx["img_3d"] = H.fig_para_b64(H.plot_3d(tab, T))
            if inc_curvas and st.session_state.df_ht is not None:
                ctx["img_curvas"] = st.session_state.get("img_curvas") or H.fig_para_b64(
                    H.plot_curvas(st.session_state.df_ht))
                ctx["img_combinado"] = st.session_state.get("img_combinado") or \
                    H.fig_para_b64(H.plot_diagrama_combinado(st.session_state.df_ht))

            tabela_calados = None
            if st.session_state.get("ht_params"):
                Tmin, Tmax, dTp = st.session_state["ht_params"]
                n = int(np.floor((Tmax - Tmin) / dTp + 1e-9)) + 1 if dTp > 0 else 0
                if n > 0:
                    tabela_calados = H.auditoria_por_calado(
                        tab, [Tmin + k * dTp for k in range(n)],
                        opt["metodo_x"], opt["metodo_z"])
            ctx["df_aud_calado"] = tabela_calados
            st.session_state["relatorio_html"] = H.gerar_relatorio(ctx)
            st.session_state["relatorio_ctx"] = ctx
            st.session_state["relatorio_pdf"] = None
            H.registrar("Relatorio", "Relatorio completo gerado.", autor="usuario")
        st.success("Relatorio gerado.")

    html = st.session_state.get("relatorio_html")
    if html:
        nome = (principais().get("nome") or "embarcacao").replace(" ", "_")
        c1, c2, c3 = st.columns(3)
        pdf = _pdf_bytes()
        if pdf:
            c1.download_button("Baixar em PDF", pdf,
                               f"relatorio_hidrostatico_{nome}.pdf", "application/pdf",
                               type="primary", **W())
        c2.download_button("Baixar o relatorio (.html)", html.encode("utf-8"),
                           f"relatorio_hidrostatico_{nome}.html", "text/html", **W())
        if st.session_state.df_ht is not None:
            xls = H.excel_hydrostatic_table(st.session_state.df_ht, tab,
                                            principais(), H.historico_df(),
                                            pd.DataFrame(st.session_state.interp_regs))
            c3.download_button("Baixar a Hydrostatic Table (.xlsx)", xls,
                               "hydrostatic_table.xlsx",
                               "application/vnd.openxmlformats-officedocument."
                               "spreadsheetml.sheet", **W())
        st.caption("O PDF ja vem paginado e pronto para imprimir ou anexar. O .html abre "
                   "em qualquer navegador, com as tabelas completas.")
        with st.expander("Pre-visualizar"):
            st.components.v1.html(html, height=700, scrolling=True)
