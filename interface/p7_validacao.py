# -*- coding: utf-8 -*-
"""Etapa 7: validacao dos resultados e historico completo."""

import numpy as np
import pandas as pd
import streamlit as st

import hidro as H
from .comum import (W, exige_completa, botao_proximo, calado_maximo,
                    opcoes, principais)


def render():
    st.title("7. Validacao")
    a0, a1, a2, a3 = st.tabs(["Validacao analitica", "Consistencia interna",
                              "Comparar com outro software", "Historico"])

    # --- Validacao 1: barcaca paralelepipedica, de solucao exata conhecida -----
    with a0:
        st.caption("Uma barcaca paralelepipedica tem solucao fechada. Rodar o mesmo "
                   "nucleo de calculo sobre ela mostra se o erro vem do metodo ou da "
                   "geometria do casco real.")
        st.latex(r"\nabla=LBT\quad KB=\frac{T}{2}\quad LCB=LCF=\frac{L}{2}\quad "
                 r"A_{WP}=LB\quad BM_t=\frac{B^2}{12T}\quad C_B=C_M=C_P=C_{WP}=1")
        c1, c2, c3, c4, c5 = st.columns(5)
        Lb = c1.number_input("L (m)", 1.0, 1000.0, 40.0, step=1.0)
        Bb = c2.number_input("B (m)", 0.5, 200.0, 10.0, step=0.5)
        Db = c3.number_input("Pontal (m)", 0.5, 100.0, 5.0, step=0.5)
        Tb = c4.number_input("Calado de teste (m)", 0.1, 99.0, 2.0, step=0.1)
        nb = c5.number_input("Balizas e linhas d'agua", 3, 101, 11, step=2)
        if Tb > Db:
            st.error("O calado de teste nao pode passar do pontal da barcaca.")
        elif st.button("Executar a validacao analitica", type="primary"):
            tb = H.barcaca_teste(Lb, Bb, Db, int(nb), int(nb))
            ob = dict(opcoes())
            ob.update({"LPP": Lb, "B": Bb, "L_ref": "LPP", "B_ref": "BWL"})
            rb = H.hidrostatica(tb, Tb, ob)
            st.session_state["df_val_ana"] = H.validacao_analitica(rb, Lb, Bb, Tb,
                                                                  ob["rho"])
            H.registrar("Etapa 7", f"Validacao analitica executada com barcaca "
                                   f"{Lb} x {Bb} x {Db} m no calado {Tb} m.",
                        autor="usuario")
        dfa = st.session_state.get("df_val_ana")
        if dfa is not None and len(dfa):
            st.dataframe(dfa.style.format({"Analitico": "{:.6f}", "Aplicativo": "{:.6f}",
                                           "Erro (%)": "{:.6f}"}),
                         hide_index=True, height=420, **W())
            emax = float(np.nanmax(dfa["Erro (%)"]))
            if emax < 1e-6:
                st.success(f"Erro maximo de {emax:.2e} %. O nucleo de calculo reproduz "
                           "exatamente a solucao analitica: o que sobra de erro nos "
                           "cascos reais vem da discretizacao da tabela de cotas, e nao "
                           "das formulas.")
            elif emax < 0.5:
                st.success(f"Erro maximo de {H.fmt(emax, 6)} %, dentro do esperado para "
                           "a discretizacao usada.")
            else:
                st.error(f"Erro maximo de {H.fmt(emax, 4)} %. Investigue o metodo de "
                         "integracao e o refinamento antes de confiar nos resultados.")

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
        opt = opcoes()
        Tmax_d = calado_maximo()
        props = ["VOL", "DESL", "LCB", "LCF", "KB", "BMT", "KMT", "AWP", "CB"]
        base = pd.DataFrame({
            "Condicao": ["1 - calado baixo", "2 - intermediario", "3 - de projeto"],
            "T (m)": [round(Tmax_d * 0.3, 3), round(Tmax_d * 0.6, 3),
                      round(float(principais().get("Td") or Tmax_d * 0.9), 3)]})
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
