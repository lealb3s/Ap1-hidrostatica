# -*- coding: utf-8 -*-
"""Etapa 8: condicao de carga e somatorio de pesos (Modulos 8 e 9 do AP1.2)."""

import numpy as np
import pandas as pd
import streamlit as st

import hidro as H
from .comum import W, rerodar, botao_proximo, exige_completa, principais, opcoes


def _achados(achados):
    erros = [a for a in achados if a.nivel == "ERRO"]
    avisos = [a for a in achados if a.nivel == "AVISO"]
    if not achados:
        st.success("Nenhum problema detectado na condicao de carga.")
        return
    c1, c2 = st.columns(2)
    c1.metric("Erros", len(erros), help="Impedem o calculo do equilibrio.")
    c2.metric("Avisos", len(avisos), help="Permitem continuar, com consequencias.")
    for a in achados:
        icone = "ERRO" if a.nivel == "ERRO" else "AVISO"
        with st.expander(f"[{icone}] {a.titulo}", expanded=(a.nivel == "ERRO")):
            st.markdown(f"**Onde:** {a.onde}")
            st.markdown(f"**O que foi encontrado:** {a.explicacao}")
            st.markdown(f"**Consequencias:** {a.consequencia}")
            if a.sugestao:
                st.markdown(f"**Como resolver:** {a.sugestao}")


def render():
    st.title("8. Condicao de carga")
    if not exige_completa():
        return
    tab = st.session_state.tab
    p = principais()

    if st.session_state.get("carga") is None:
        st.session_state["carga"] = H.condicao_vazia(6)

    st.caption("Cada linha e um item de peso: casco leve, maquinas, tripulacao, "
               "tanques, carga. O aplicativo soma os pesos e os momentos e obtem "
               "Delta, LCG e KG.")

    c1, c2 = st.columns([2, 1])
    with c1:
        st.session_state["nome_condicao"] = st.text_input(
            "Nome da condicao", value=st.session_state.get("nome_condicao", ""),
            placeholder="Partida - 100% suprimentos - atendimento ao publico")
    with c2:
        x0, x1 = float(np.min(tab.x)), float(np.max(tab.x))
        st.caption(f"**Referencia do LCG:** a mesma da coluna X da tabela de cotas, "
                   f"de {H.fmt(x0)} m (AP) a {H.fmt(x1)} m (FP), crescendo de re para "
                   "vante. O VCG e medido a partir da linha de base.")

    a1, a2 = st.tabs(["Itens de peso", "Importar de arquivo"])

    with a1:
        st.caption("A coluna de superficie livre so e preenchida para tanques: e o "
                   "momento de inercia da superficie do liquido, em m4. Deixe zero "
                   "nos demais itens.")
        edit = st.data_editor(st.session_state["carga"], num_rows="dynamic",
                              key="editor_carga", height=340, **W())
        c1, c2, c3 = st.columns(3)
        if c1.button("Aplicar itens", type="primary", **W()):
            st.session_state["carga"] = edit.reset_index(drop=True)
            st.session_state["eq"] = None
            H.registrar("Etapa 8", f"Condicao de carga editada: {len(edit)} item(ns).",
                        autor="usuario")
            rerodar()
        if c2.button("Acrescentar 5 linhas", **W()):
            st.session_state["carga"] = pd.concat(
                [edit.reset_index(drop=True), H.condicao_vazia(5)], ignore_index=True)
            rerodar()
        if c3.button("Limpar tudo", **W()):
            st.session_state["carga"] = H.condicao_vazia(6)
            st.session_state["eq"] = None
            rerodar()

    with a2:
        st.caption("Aceita .xlsx e .csv. Os nomes das colunas sao reconhecidos por "
                   "palavra-chave: basta conter 'peso', 'LCG', 'VCG' e assim por "
                   "diante. As colunas de momento nao sao lidas: sao recalculadas.")
        up = st.file_uploader("Arquivo da condicao de carga",
                              type=["xlsx", "xlsm", "xls", "csv", "txt"],
                              key=f"upl_carga_{st.session_state.uploader_id}")
        if up is not None and st.button("Ler este arquivo", type="primary"):
            try:
                df, notas = H.ler_condicao(up)
                st.session_state["carga"] = df
                st.session_state["eq"] = None
                for n in notas:
                    st.caption(f"- {n}")
                H.registrar("Etapa 8", f"Condicao de carga importada de '{up.name}': "
                                       f"{len(df)} item(ns).", autor="usuario")
                st.success(f"{len(df)} item(ns) importado(s).")
                rerodar()
            except Exception as e:                                   # noqa: BLE001
                st.error(f"Nao foi possivel ler o arquivo: {e}")
        modelo = H.condicao_vazia(3)
        st.download_button(
            "Baixar um modelo em branco (.csv)",
            modelo.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
            "modelo_condicao_de_carga.csv", "text/csv")

    df = st.session_state["carga"]
    st.divider()
    st.subheader("9. Somatorio de pesos")

    achados = H.validar_condicao(df, tab, p)
    st.session_state["achados_carga"] = achados
    _achados(achados)
    if any(a.nivel == "ERRO" for a in achados):
        return

    soma = H.somatorio(df)
    st.session_state["soma"] = soma

    c = st.columns(5)
    c[0].metric("Delta [t]", H.fmt(soma["delta"], 3))
    c[1].metric("LCG [m]", H.fmt(soma["LCG"], 4))
    c[2].metric("KG sem correcao [m]", H.fmt(soma["KG"], 4))
    c[3].metric("GG0 sup. livre [m]", H.fmt(soma["GG0"], 4))
    c[4].metric("KG corrigido [m]", H.fmt(soma["KG_corr"], 4))

    st.markdown("#### Memoria do somatorio")
    st.latex(r"\Delta=\sum w_i \qquad LCG=\frac{\sum w_i\,LCG_i}{\Delta} \qquad "
             r"KG=\frac{\sum w_i\,VCG_i}{\Delta} \qquad "
             r"GG_0=\frac{\sum \rho_i\,i_i}{\Delta}")
    st.dataframe(soma["detalhe"], hide_index=True, height=300, **W())
    st.markdown(
        f"Soma dos pesos = **{H.fmt(soma['delta'], 3)} t** &nbsp;&nbsp; "
        f"Soma dos momentos longitudinais = **{H.fmt(soma['soma_mom_l'], 3)} t.m** "
        f"&nbsp;&nbsp; LCG = {H.fmt(soma['soma_mom_l'], 3)} / "
        f"{H.fmt(soma['delta'], 3)} = **{H.fmt(soma['LCG'], 4)} m**")
    st.markdown(
        f"Soma dos momentos verticais = **{H.fmt(soma['soma_mom_v'], 3)} t.m** "
        f"&nbsp;&nbsp; KG = {H.fmt(soma['soma_mom_v'], 3)} / {H.fmt(soma['delta'], 3)} = "
        f"**{H.fmt(soma['KG'], 4)} m**")
    if abs(soma["GG0"]) > 1e-9:
        st.info(
            f"**Superficie livre.** Soma de rho x i = {H.fmt(soma['soma_mom_sl'], 3)} "
            f"t.m, que dividida pelo deslocamento da GG0 = {H.fmt(soma['GG0'], 4)} m. "
            "Essa elevacao virtual do centro de gravidade nao muda o peso nem o "
            "calado: ela reduz o GM, porque o liquido escorrega para o bordo baixo "
            "quando o navio inclina. O KG corrigido e o que entra no calculo de "
            "estabilidade.")
    else:
        st.caption("Nenhum item tem superficie livre informada, entao GG0 = 0 e o KG "
                   "corrigido e igual ao KG.")

    botao_proximo("9. Equilibrio e trim")
