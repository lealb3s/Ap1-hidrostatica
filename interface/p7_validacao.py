# -*- coding: utf-8 -*-
"""Etapa 7: validacao dos resultados e historico completo."""

import numpy as np
import pandas as pd
import streamlit as st

import hidro as H
from .comum import W, exige_completa, botao_proximo, calado_maximo


def render():
    st.title("7. Validacao")
    a1, a2, a3 = st.tabs(["Consistencia interna", "Comparar com outro software",
                          "Historico"])

    with a1:
        r = st.session_state.get("r_atual")
        if r is None:
            st.info("Calcule um calado na etapa 5 para conferir a consistencia interna.")
        else:
            st.caption("Identidades que precisam se verificar sozinhas. As tres primeiras "
                       "sao algebricas e devem dar erro praticamente nulo; a diferenca "
                       "entre os volumes reflete a discretizacao e e a mais informativa "
                       "sobre a qualidade da malha.")
            dfi = H.verificacoes_internas(r)
            extra = pd.DataFrame([{
                "Verificacao": "Celulas geradas por interpolacao",
                "Esperado": 0.0, "Obtido": float(st.session_state.tab.n_interpolados()),
                "Erro absoluto": float(st.session_state.tab.n_interpolados()),
                "Erro (%)": np.nan, "Unidade": "celulas"}])
            dfi = pd.concat([dfi, extra], ignore_index=True)
            st.session_state["df_val_int"] = dfi
            st.dataframe(dfi.style.format({"Esperado": "{:.6f}", "Obtido": "{:.6f}",
                                           "Erro absoluto": "{:.3e}", "Erro (%)": "{:.6f}"}),
                         hide_index=True, **W())

    with a2:
        st.caption("Informe os valores obtidos em um software de referencia (Maxsurf, por "
                   "exemplo) em tres condicoes. O aplicativo calcula os proprios valores nos "
                   "mesmos calados e monta a tabela de erros.")
        st.latex(r"\text{Erro}=\frac{|X_{app}-X_{ref}|}{|X_{ref}|}\times 100")
        if not exige_completa():
            return
        tab = st.session_state.tab
        opt = st.session_state.opt
        Tmax_d = calado_maximo()
        props = ["VOL", "DESL", "LCB", "LCF", "KB", "BMT", "KMT", "AWP", "CB"]
        base = pd.DataFrame({
            "Condicao": ["1 - calado baixo", "2 - intermediario", "3 - de projeto"],
            "T (m)": [round(Tmax_d * 0.3, 3), round(Tmax_d * 0.6, 3),
                      round(float(st.session_state.principais.get("Td") or Tmax_d * 0.9), 3)]})
        for k in props:
            base[H.PROPRIEDADES[k][0]] = 0.0
        ent = st.data_editor(base, num_rows="fixed", key="editor_ref", **W())
        if st.button("Comparar", type="primary"):
            linhas = []
            for _, lin in ent.iterrows():
                T = float(lin["T (m)"])
                if not (0 < T <= Tmax_d):
                    continue
                r = H.hidrostatica(tab, T, opt)
                for k in props:
                    ref = float(lin[H.PROPRIEDADES[k][0]])
                    if abs(ref) < 1e-12:
                        continue
                    val = r[k]
                    if k in ("LCB", "LCF"):
                        val = H.converter_origem(val, tab, opt["origem_x"])
                    linhas.append({"Condicao": lin["Condicao"], "T (m)": T,
                                   "Grandeza": H.PROPRIEDADES[k][0], "Aplicativo": val,
                                   "Referencia": ref,
                                   "Erro (%)": abs(val - ref) / abs(ref) * 100,
                                   "Unidade": H.PROPRIEDADES[k][1]})
            if linhas:
                st.session_state.df_val_max = pd.DataFrame(linhas)
                H.registrar("Etapa 7", f"Comparacao externa registrada ({len(linhas)} "
                                       "grandezas).", autor="usuario")
            else:
                st.warning("Preencha ao menos um valor de referencia diferente de zero.")
        dfm = st.session_state.df_val_max
        if dfm is not None and len(dfm):
            st.dataframe(dfm.style.format({"Aplicativo": "{:.4f}", "Referencia": "{:.4f}",
                                           "Erro (%)": "{:.3f}"}), hide_index=True, **W())
            st.info("**Origens usuais das diferencas:** discretizacao (numero de balizas e "
                    "de linhas d'agua), interpolacao linear entre pontos, tratamento das "
                    "extremidades, referencia longitudinal adotada, superficie moldada "
                    "versus externa e o metodo de integracao. Poucos por cento em volume e "
                    "A_WP sao usuais; diferenca grande em LCB ou LCF quase sempre significa "
                    "origem longitudinal diferente.")

    with a3:
        st.caption("Data e hora, etapa, acao, valor anterior, valor novo, autor e "
                   "consequencias de tudo o que foi feito.")
        h = H.historico_df()
        st.dataframe(h, height=460, **W())
        if st.session_state.avisos_ignorados:
            st.warning("**Avisos que voce optou por ignorar:**\n\n" +
                       "\n".join(f"- {a}" for a in st.session_state.avisos_ignorados))
        st.download_button("Baixar o historico (CSV)",
                           h.to_csv(index=False, sep=";").encode("utf-8-sig"),
                           "historico.csv", "text/csv")

    botao_proximo("Relatorio final")
