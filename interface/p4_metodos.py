# -*- coding: utf-8 -*-
"""Etapa 4: regras de integracao e como elas se comportam em cada calado."""

import numpy as np
import pandas as pd
import streamlit as st

import hidro as H
from .comum import (W, exige_completa, botao_proximo, calado_maximo,
                    numero_seguro, opcoes)


def render():
    st.title("4. Metodos de calculo")
    if not exige_completa():
        return
    tab = st.session_state.tab
    opt = opcoes()

    st.caption("As tres regras estao implementadas diretamente no codigo, sem biblioteca "
               "pronta. Veja o arquivo hidro/integracao.py.")
    c1, c2, c3 = st.columns(3)
    c1.latex(r"\frac{h}{2}(f_0+f_1)")
    c1.caption("Trapezio - qualquer numero de intervalos")
    c2.latex(r"\frac{h}{3}(f_0+4f_1+2f_2+\dots+f_n)")
    c2.caption("Simpson 1/3 - numero par de intervalos")
    c3.latex(r"\frac{3h}{8}(f_0+3f_1+3f_2+f_3)")
    c3.caption("Simpson 3/8 - multiplo de tres")

    metodos = ["auto", "simpson13", "simpson38", "trapezio"]
    nomes = {"auto": "Automatico (combina as regras)", "simpson13": "So Simpson 1/3",
             "simpson38": "So Simpson 3/8", "trapezio": "So Trapezio"}
    c1, c2 = st.columns(2)
    with c1:
        opt["metodo_x"] = st.selectbox("Eixo x (ao longo do comprimento)", metodos,
                                       index=metodos.index(opt.get("metodo_x", "auto")),
                                       format_func=lambda k: nomes[k])
    with c2:
        opt["metodo_z"] = st.selectbox("Eixo z (ao longo do calado)", metodos,
                                       index=metodos.index(opt.get("metodo_z", "auto")),
                                       format_func=lambda k: nomes[k])

    if opt["metodo_x"] != "auto" or opt["metodo_z"] != "auto":
        st.warning("Simpson 1/3 exige numero par de intervalos e Simpson 3/8 exige multiplo "
                   "de tres. Quando a conta nao fecha, o trecho que sobra e integrado pelo "
                   "Trapezio e isso aparece na auditoria. Forcar o Trapezio em todo o "
                   "dominio reduz a ordem de precisao e tende a subestimar secoes convexas.")

    st.divider()
    st.markdown("#### Malha vertical de calculo")
    st.caption("Quantas partes cada intervalo entre duas linhas d'agua e dividido antes "
               "de integrar. As linhas d'agua originais continuam sendo nos da malha: "
               "nenhuma geometria nova e inventada.")
    c1, c2 = st.columns([1, 2])
    with c1:
        opt["sub_vertical"] = st.select_slider(
            "Subdivisoes por intervalo", options=[1, 2, 4, 8, 16],
            value=int(opt.get("sub_vertical", 4)))
    with c2:
        if opt["sub_vertical"] == 1:
            st.warning(
                "Sem subdividir, a quantidade de intervalos abaixo do calado muda "
                "conforme T sobe, e com ela a regra aplicada: um intervalo obriga o "
                "Trapezio, dois liberam Simpson 1/3, tres liberam Simpson 3/8. A cada "
                "troca a curva da um salto. Pior: em calados baixos, com um unico "
                "intervalo, o Trapezio joga toda a area para o topo e devolve KB = T, "
                "um valor impossivel. Use 1 apenas para comparar com o calculo manual "
                "feito estritamente sobre as linhas d'agua da tabela.")
        else:
            st.success(
                f"Cada intervalo vertical vira {opt['sub_vertical']} partes, entao a mesma "
                "regra vale em toda a faixa de calados e as curvas ficam continuas. "
                "Este e o ajuste recomendado, sobretudo com poucas linhas d'agua.")

    a1, a2 = st.tabs(["Auditoria calado a calado", "Malha fixa da tabela"])

    with a1:
        st.markdown("#### Como as regras mudam conforme o calado")
        st.caption("A integracao vertical usa apenas as linhas d'agua abaixo do calado. "
                   "Em calados baixos entram poucas, e a regra aplicada muda. Esta tabela "
                   "mostra exatamente o que acontece em cada um.")
        Tmax = calado_maximo()
        c1, c2, c3 = st.columns(3)
        Tmin_a = numero_seguro("Do calado (m)", 0.001, Tmax, max(Tmax / 10, 0.001),
                               passo=0.05, key="aud_tmin")
        Tmax_a = numero_seguro("Ate o calado (m)", 0.002, Tmax, Tmax, passo=0.05,
                               key="aud_tmax")
        dT_a = numero_seguro("Passo (m)", 0.001, max(Tmax, 0.002), max(Tmax / 10, 0.01),
                             passo=0.05, key="aud_dt")
        n = int(np.floor((Tmax_a - Tmin_a) / dT_a + 1e-9)) + 1 if dT_a > 0 else 0
        calados = [Tmin_a + k * dT_a for k in range(max(n, 0))]
        if not calados:
            st.info("Ajuste a faixa: o calado final precisa ser maior que o inicial.")
        else:
            df = H.auditoria_por_calado(tab, calados, opt["metodo_x"], opt["metodo_z"])
            st.dataframe(df, hide_index=True, height=380, **W())
            so_simpson = (df["So Simpson?"] == "sim").sum()
            parciais = (df["Ultimo trecho parcial"] == "sim").sum()
            c1, c2, c3 = st.columns(3)
            c1.metric("Calados avaliados", len(df))
            c2.metric("Integrados so por Simpson", int(so_simpson))
            c3.metric("Com ultimo trecho parcial", int(parciais))
            baixos = df[df["Intervalos"] < 2]
            if len(baixos):
                st.warning(
                    f"Em {len(baixos)} calado(s) sobra apenas um intervalo vertical, o que "
                    "obriga o Trapezio e torna a area seccional pouco confiavel ali. "
                    "E o motivo pelo qual as curvas costumam ficar tortas bem perto do "
                    "fundo. Solucoes: comecar a Hydrostatic Table num calado maior, ou "
                    "reamostrar as linhas d'agua numa malha mais fina abaixo.")
            if parciais:
                st.info(f"Em {int(parciais)} calado(s) o ultimo trecho vertical e parcial "
                        "(o calado cai entre duas linhas d'agua). Esse pedaco e sempre "
                        "integrado pelo Trapezio, mesmo com Simpson escolhido. Isso e "
                        "correto e esperado.")

        with st.expander("Refinar a tabela por interpolacao"):
            st.caption(
                "Acrescenta balizas e linhas d'agua INTERMEDIARIAS entre as originais. "
                "Isso nao cria informacao nova: troca a suposicao de reta entre dois "
                "pontos por uma curva suave que passa exatamente pelos mesmos pontos. "
                "Como um casco de verdade e suave, a curva costuma estar mais perto da "
                "realidade, e areas e volumes deixam de ser subestimados no bojo.")
            c1, c2, c3 = st.columns(3)
            with c1:
                fz = st.select_slider("Linhas d'agua: multiplicar por",
                                      options=[1, 2, 4, 8], value=1)
            with c2:
                fx = st.select_slider("Balizas: multiplicar por",
                                      options=[1, 2, 4], value=1)
            with c3:
                met = st.selectbox(
                    "Curva usada", ["monotona", "linear"],
                    format_func=lambda k: {"monotona": "Cubica monotona (recomendada)",
                                           "linear": "Linear (mantem as retas)"}[k])
            n_est_novo = (tab.n_est - 1) * fx + 1
            n_wl_novo = (tab.n_wl - 1) * fz + 1
            st.caption(f"A tabela passaria de {tab.n_est} x {tab.n_wl} para "
                       f"{n_est_novo} x {n_wl_novo}.")
            if met == "linear" and (fx > 1 or fz > 1):
                st.info("Com a curva linear, refinar nao muda resultado nenhum: os pontos "
                        "novos caem exatamente sobre as retas que ja eram usadas. Serve "
                        "apenas para deixar a malha uniforme.")
            else:
                st.warning(
                    "Os valores gerados aparecem separados dos originais na auditoria e "
                    "no relatorio. A curva monotona passa pelos pontos do arquivo e nunca "
                    "ultrapassa os valores vizinhos, mas continua sendo uma suposicao "
                    "sobre o que existe entre eles.")
            if st.button("Refinar a tabela", type="primary", disabled=(fx == 1 and fz == 1)):
                nova, resumo = H.refinar_tabela(tab, fx, fz, met)
                st.session_state.tab = nova
                st.session_state.df_ht = None
                H.registrar("Etapa 4", f"Tabela refinada para {resumo['balizas']} balizas x "
                                       f"{resumo['linhas_agua']} linhas d'agua por "
                                       f"interpolacao {resumo['metodo']}.",
                            nivel="ALTERACAO", autor="usuario",
                            antes=f"{tab.n_est} x {tab.n_wl}",
                            novo=f"{resumo['balizas']} x {resumo['linhas_agua']}",
                            consequencia=f"{resumo['gerados']} valores passam a ser "
                                         "gerados por interpolacao, e nao lidos do arquivo. "
                                         "Areas, volumes e centros mudam.")
                st.rerun()

    with a2:
        st.caption("Regras aplicadas sobre a malha completa da tabela, antes de recortar "
                   "pelo calado.")
        px = H.planejar_integracao(tab.x, opt["metodo_x"])
        pz = H.planejar_integracao(tab.z, opt["metodo_z"])
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Eixo x (balizas)**")
            st.code(" ; ".join(f"estacoes {a}-{b}: {m}" for a, b, m in px) or "-")
            st.dataframe(pd.DataFrame([{"Trecho": f"{a}-{b}", "Regra": m,
                                        "x inicial": tab.x[a], "x final": tab.x[b],
                                        "h": (tab.x[b] - tab.x[a]) / (b - a)}
                                       for a, b, m in px]), hide_index=True, **W())
        with c2:
            st.markdown("**Eixo z (linhas d'agua)**")
            st.code(" ; ".join(f"WL {a}-{b}: {m}" for a, b, m in pz) or "-")
            st.dataframe(pd.DataFrame([{"Trecho": f"{a}-{b}", "Regra": m,
                                        "z inicial": tab.z[a], "z final": tab.z[b],
                                        "h": (tab.z[b] - tab.z[a]) / (b - a)}
                                       for a, b, m in pz]), hide_index=True, **W())

    botao_proximo("5. Resultados no calado")
