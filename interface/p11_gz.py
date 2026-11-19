# -*- coding: utf-8 -*-
"""
Etapa 10 (AP1.3): curva de estabilidade estatica transversal GZ.

A tela so monta entradas, chama o nucleo (hidro/estabilidade.py) e mostra os
resultados. Nenhuma formula mora aqui.
"""

import io

import numpy as np
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt

import hidro as H
from .comum import (W, exige_completa, botao_proximo, opcoes, principais,
                    limite_calado, slider_seguro, numero_seguro)


# ---------------------------------------------------------------------------
# utilitarios
# ---------------------------------------------------------------------------

def _csv_br(df: pd.DataFrame) -> bytes:
    """CSV para Excel em portugues: ponto e virgula e virgula decimal."""
    return df.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig")


def _csv_us(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def _fig(fig):
    st.pyplot(fig, **W())
    plt.close(fig)


def _mostrar_df(df: pd.DataFrame, casas=5):
    st.dataframe(df.round(casas), hide_index=True, **W())


def _g(v, uni="") -> str:
    """Quatro algarismos significativos, com virgula decimal (serve a casco em escala de modelo)."""
    if v is None or not np.isfinite(v):
        return "-"
    return (f"{v:.4g}".replace(".", ",") + (f" {uni}" if uni else ""))


def _numeros(texto: str) -> list:
    out = []
    for p in str(texto).replace(";", ",").split(","):
        v = H.para_float(p)
        if np.isfinite(v):
            out.append(float(v))
    return out


# ---------------------------------------------------------------------------
# 1. entrada e calculo
# ---------------------------------------------------------------------------

def _entrada(tab, opt):
    """Le os widgets e devolve o dicionario de entrada (ainda nao calcula)."""
    p = principais()
    carga_soma = st.session_state.get("soma")
    eq = st.session_state.get("eq")
    tem_carga = bool(carga_soma) and float(carga_soma.get("delta") or 0) > 0

    modos = ["Calado", "Deslocamento", "Condicao de carga (etapas 8 e 9)"]
    modo = st.radio("Como definir a condicao de carregamento", modos, horizontal=True,
                    key="gz_modo",
                    help="O deslocamento fixa o volume submerso que o aplicativo mantem "
                         "constante enquanto o casco inclina.")
    im = modos.index(modo)

    c1, c2 = st.columns(2)
    with c1:
        rho = numero_seguro("Densidade da agua (t/m3)", 0.90, 1.30, opt.get("rho", 1.025),
                            0.001, "%.3f", key="gz_rho")
    V_total = H.MotorGZ(tab).V_total
    Tmax = min(limite_calado(), 0.98 * H.calado_max(tab))
    e = {"modo": modo, "rho": float(rho), "T": None, "delta": None}

    with c1:
        if im == 0:
            Td = float(p.get("Td") or 0.0)
            T0 = Td if Td > 0 else 0.6 * Tmax
            e["T"] = slider_seguro("Calado T (m, a partir da linha de base)", 0.02 * Tmax, Tmax,
                                   min(max(T0, 0.02 * Tmax), Tmax), key="gz_T")
            r = H.hidrostatica(tab, e["T"], {**opt, "rho": rho})
            e["delta"] = float(r["DESL"])
            st.caption(f"Deslocamento correspondente: **{H.fmt(e['delta'], 3)} t**  |  "
                       f"KM_t = {H.fmt(r['KMT'], 4)} m  |  KB = {H.fmt(r['KB'], 4)} m")
            e["KM_ref"] = float(r["KMT"])
        elif im == 1:
            dmax = 0.98 * rho * V_total
            e["delta"] = numero_seguro("Deslocamento (t)", 1e-9, dmax,
                                       min(0.4 * dmax, dmax), max(dmax / 500, 1e-6), "%.4f",
                                       key="gz_delta")
        else:
            if not tem_carga:
                st.warning("Nenhuma condicao de carga fechada ainda. Monte a condicao na "
                           "etapa 8 ou escolha outro modo.")
                e["delta"] = None
            else:
                e["delta"] = float(carga_soma["delta"])
                st.caption(f"Condicao de carga: **{H.fmt(e['delta'], 3)} t**, "
                           f"KG = {H.fmt(carga_soma['KG'], 4)} m, "
                           f"GG0 = {H.fmt(carga_soma['GG0'], 4)} m")

    kg_ini = float(carga_soma["KG"]) if (im == 2 and tem_carga) else float(opt.get("KG") or 0.0)
    if kg_ini <= 0 and e.get("KM_ref"):
        kg_ini = round(0.75 * e["KM_ref"], 3)
    gg0_ini = float(carga_soma["GG0"]) if (im == 2 and tem_carga) else 0.0
    with c2:
        e["KG"] = float(st.number_input("KG (m, a partir da linha de base)", 0.0, 1e4,
                                        max(kg_ini, 0.0), 0.01, format="%.4f", key=f"gz_KG_{im}",
                                        help="Mesmo referencial do KB e do KM: linha de base = "
                                             "primeira linha d'agua da tabela."))
        e["GG0"] = float(st.number_input("Correcao de superficie livre GG0 (m)", 0.0, 1e3,
                                         max(gg0_ini, 0.0), 0.001, format="%.4f",
                                         key=f"gz_GG0_{im}",
                                         help="Entra como KG fluido = KG + GG0 (correcao de "
                                              "pequenos angulos)."))
        t_eq = float(eq["t_m"]) if (im == 2 and eq and np.isfinite(eq.get("t_m", np.nan))) else 0.0
        e["compasso"] = float(st.number_input("Compasso fixo (m, positivo pela proa)", -1e3, 1e3,
                                              t_eq, 0.01, format="%.4f", key=f"gz_trim_{im}",
                                              help="O casco inclina com este compasso fixo. "
                                                   "Zero = quilha paralela."))
    c3, c4, c5 = st.columns(3)
    with c3:
        e["phi_max"] = float(st.number_input("Banda maxima (graus)", 60.0, 90.0, 90.0, 5.0,
                                             key="gz_phimax",
                                             help="O enunciado pede de 0 ate, no minimo, 60 graus."))
    with c4:
        e["passo"] = float(st.number_input("Passo (graus)", 0.5, 5.0, 2.5, 0.5, key="gz_passo",
                                           help="O enunciado limita o passo a 5 graus."))
    with c5:
        e["refinar"] = st.checkbox("Refinar o GZ maximo", True, key="gz_refinar",
                                   help="Busca o maximo verdadeiro entre dois angulos da malha.")
    return e


def _calcular(tab, e):
    r = H.curva_gz(tab, e["delta"], e["KG"], e["rho"], e["phi_max"], e["passo"],
                   opcoes().get("metodo_x", "auto"), e["compasso"], e["GG0"], e["refinar"])
    # confronto com a hidrostatica do proprio aplicativo (calado de equilibrio)
    opt = opcoes()
    h = H.hidrostatica(tab, r["resumo"]["T_equilibrio"], {**opt, "rho": e["rho"]})
    r["hid"] = {"KB": h["KB"], "KM_t": h["KMT"], "GM_t": h["KMT"] - r["resumo"]["KG_efetivo"],
                "VOL": h["VOL"]}
    return r


def _aba_calculo(tab, opt):
    e = _entrada(tab, opt)
    ok = e["delta"] is not None and e["delta"] > 0
    chave = {k: v for k, v in e.items()}
    antigo = st.session_state.get("gz")
    if st.button("Calcular curva GZ", type="primary", disabled=not ok):
        try:
            with st.spinner("Recalculando a carena em cada angulo de banda..."):
                r = _calcular(tab, e)
            st.session_state["gz"] = {"res": r, "entrada": chave}
            H.registrar("Etapa 10", "Curva GZ calculada.", autor="usuario",
                        novo=f"Delta={H.fmt(e['delta'], 3)} t, KG={H.fmt(e['KG'], 3)} m, "
                             f"0 a {e['phi_max']:g} graus, passo {e['passo']:g}",
                        consequencia="Resultados da etapa 10 atualizados.")
            antigo = st.session_state["gz"]
        except ValueError as err:
            st.error(str(err))
    if antigo is not None and antigo["entrada"] != chave:
        st.warning("Os parametros mudaram desde o ultimo calculo. Clique em **Calcular curva GZ** "
                   "para atualizar os resultados.")
    if antigo is None:
        st.info("Defina a condicao e clique em **Calcular curva GZ**.")
    with st.expander("Como o GZ e calculado (nao e GM sen(phi))"):
        st.markdown(
            "Para **cada banda** o casco e inclinado e a linha d'agua e reposicionada ate o volume "
            "submerso igual ao do deslocamento. Cada baliza e um poligono (meia-boca da tabela, "
            "espelhada, fechada no conves); o poligono e recortado pela linha d'agua e a area e os "
            "momentos saem exatos pela formula de Gauss. A integracao ao longo do comprimento usa os "
            "mesmos pesos de Trapezio/Simpson do restante do aplicativo.")
        st.latex(r"\nabla_\phi=\sum a_i A_i(\phi)=\frac{\Delta}{\rho}\qquad "
                 r"Y_B=\frac{\sum a_i M_{y,i}}{\nabla}\qquad Z_B=\frac{\sum a_i M_{z,i}}{\nabla}")
        st.latex(r"GZ = Y_B\cos\phi + (Z_B-KG)\sin\phi \qquad "
                 r"M_{endireit.}=\Delta\,GZ")
        st.caption("Hipoteses: compasso fixo, casco fechado no conves (sem alagamento), "
                   "interpolacao linear entre pontos da tabela, sem apendices nem superestrutura.")


# ---------------------------------------------------------------------------
# 2. resultados
# ---------------------------------------------------------------------------

def _aba_resultados():
    g = st.session_state.get("gz")
    if g is None:
        st.info("Calcule a curva na aba anterior.")
        return
    r, R = g["res"], g["res"]["resumo"]
    for a in r["avisos"]:
        st.warning(a)
    c = st.columns(4)
    c[0].metric("Deslocamento", _g(R['delta_t'], "t"))
    c[1].metric("Calado de equilibrio", f"{H.fmt(R['T_equilibrio'], 4)} m")
    c[2].metric("KG efetivo", f"{H.fmt(R['KG_efetivo'], 4)} m")
    c[3].metric("Reserva de empuxo", f"{H.fmt(R['reserva_empuxo_pct'], 1)} %")
    c = st.columns(4)
    c[0].metric("GM inicial (pela curva)", f"{H.fmt(R['GM_numerico'], 4)} m",
                help="Limite de GZ/sen(phi) quando phi tende a zero, extrapolado de 0,5 e 1 grau.")
    c[1].metric("GM inicial (hidrostatica)", f"{H.fmt(r['hid']['GM_t'], 4)} m",
                help="KM_t da Hydrostatic Table do aplicativo menos KG efetivo.")
    c[2].metric("GZ maximo", f"{H.fmt(R['GZ_max'], 4)} m")
    c[3].metric("Banda do GZ maximo", f"{H.fmt(R['ang_GZ_max'], 2)} graus")
    c = st.columns(4)
    c[0].metric("Fim da estabilidade positiva", "-" if not np.isfinite(R["ang_estab_nula"])
                else f"{H.fmt(R['ang_estab_nula'], 2)} graus")
    c[1].metric("Imersao da borda do conves", "-" if not np.isfinite(R["ang_borda_conves"])
                else f"{H.fmt(R['ang_borda_conves'], 2)} graus")
    c[2].metric("Momento de endireit. maximo", _g(R['RM_max_tm'], "t.m"))
    dif = abs(R["GM_numerico"] - r["hid"]["GM_t"])
    c[3].metric("|GM curva - GM hidrostatica|", f"{dif:.2e} m",
                help="Confere o recorte de poligonos com a hidrostatica do aplicativo. Diferencas "
                     "pequenas vem da discretizacao (Simpson de y^3 na hidrostatica contra o "
                     "recorte exato das secoes) e crescem quando o calado se aproxima do conves.")

    _fig(H.plot_curva_gz(r["df"], R))

    st.markdown("**Regioes de braco de endireitamento**")
    reg = pd.DataFrame(R["regioes"]).rename(columns={"sinal": "GZ", "de": "de (graus)",
                                                      "ate": "ate (graus)"})
    _mostrar_df(reg, 2)
    st.markdown("**Tabela numerica usada no grafico**")
    _mostrar_df(r["df"], 5)
    st.caption("Banda positiva = boreste para baixo. Calado no plano de centro = altura da linha "
               "d'agua sobre a linha de base, medida no plano diametral do casco inclinado.")


# ---------------------------------------------------------------------------
# 3. secao inclinada
# ---------------------------------------------------------------------------

def _aba_secao(tab):
    g = st.session_state.get("gz")
    if g is None:
        st.info("Calcule a curva na primeira aba.")
        return
    r, R = g["res"], g["res"]["resumo"]
    motor = r["motor"]
    c1, c2 = st.columns([2, 1])
    with c1:
        ph = slider_seguro("Banda (graus)", 0.0, float(g["entrada"]["phi_max"]), 30.0, 0.5,
                           key="gz_sec_phi")
    with c2:
        i0 = int(np.argmax([c[0] for c in motor.cheio]))
        rot = [str(x) for x in tab.rotulos]
        i = st.selectbox("Baliza", range(len(rot)), index=i0, format_func=lambda k: rot[k],
                         key="gz_sec_est")
    res = motor.resolver(R["V_m3"], float(ph))
    gz = res["Yb"] * res["cs"] + (res["Zb"] - R["KG_efetivo"]) * res["sn"]
    cols = st.columns(4)
    cols[0].metric("GZ", f"{H.fmt(gz, 4)} m")
    cols[1].metric("Y_B (de B ao plano de centro)", f"{H.fmt(res['Yb'], 4)} m")
    cols[2].metric("KB na banda", f"{H.fmt(res['Zb'], 4)} m")
    cols[3].metric("Borda do conves", "imersa" if res["folga_borda"] >= 0 else "fora d'agua")
    _fig(H.plot_secao_inclinada(motor, res, R["KG_efetivo"], i))


# ---------------------------------------------------------------------------
# 4. validacao 1 - barcaca, solucao analitica
# ---------------------------------------------------------------------------

def _aba_val1():
    st.markdown(
        "Barcaca prismatica de secao retangular, com **solucao analitica independente**: "
        "o GZ exato vem da integracao da altura molhada h(y) = clamp(c + y tan phi, 0, D), sem "
        "recorte de poligonos. Onde a formula de parede vertical vale, ela tambem e mostrada.")
    c = st.columns(5)
    L = c[0].number_input("L (m)", 1.0, 1e3, 40.0, 1.0, key="v1_L")
    B = c[1].number_input("B (m)", 0.5, 1e3, 10.0, 0.5, key="v1_B")
    D = c[2].number_input("D (m)", 0.5, 1e3, 5.0, 0.5, key="v1_D")
    T = c[3].number_input("T (m)", 0.05, 1e3, 2.0, 0.1, key="v1_T")
    KG = c[4].number_input("KG (m)", 0.0, 1e3, 3.0, 0.1, key="v1_KG")
    rho = 1.025
    if not (0 < T < D):
        st.error("O calado precisa ficar entre 0 e o pontal.")
        return
    texto = st.text_input("Angulos de banda (graus, separados por virgula; no minimo cinco)",
                          "10, 20, 30, 40, 50, 60, 70", key="v1_ang")
    ang = sorted({a for a in _numeros(texto) if 0 < a < 90})
    if len(ang) < 5:
        st.warning("Informe pelo menos cinco angulos entre 0 e 90 graus.")
        return
    tab = H.barcaca_teste(L, B, D, 11, 11)
    motor = H.MotorGZ(tab)
    V = L * B * T
    cmp = H.comparar_curvas(ang, [H.barcaca_gz_analitico(B, D, T, KG, a)["GZ_exato"] for a in ang],
                            motor, V, KG)
    ana = [H.barcaca_gz_analitico(B, D, T, KG, a) for a in ang]
    cmp["Parede vertical (m)"] = [a["GZ_parede"] for a in ana]
    cmp["Parede vertical vale?"] = ["sim" if a["parede_valida"] else "nao (borda imersa ou bojo emerso)"
                                    for a in ana]
    cmp = cmp.rename(columns={"GZ referencia (m)": "GZ analitico exato (m)"})
    cmp_plot = cmp.rename(columns={"GZ analitico exato (m)": "GZ referencia (m)"})
    fino = np.arange(0.0, 85.0, 1.0)
    linha = (fino, [H.barcaca_gz_analitico(B, D, T, KG, a)["GZ_exato"] for a in fino])
    _fig(H.plot_comparacao_gz(cmp_plot, "Analitico exato (integral)", linha))
    _mostrar_df(cmp, 8)
    erro = float(np.max(np.abs(cmp["Diferenca absoluta (m)"])))
    pct = cmp["Diferenca (%)"].abs().max()
    st.success(f"Diferenca absoluta maxima: **{erro:.2e} m**"
               + (f"  |  diferenca percentual maxima: **{pct:.2e} %**" if np.isfinite(pct) else "")
               + f"  |  {len(ang)} angulos comparados.")
    st.caption("A diferenca percentual so e calculada onde |GZ de referencia| >= 0,005 m; perto de "
               "zero o denominador explode e vale so a diferenca absoluta.")
    gmv = H.barcaca_gz_analitico(B, D, T, KG, ang[0])
    st.markdown(f"Dados: KB = T/2 = {H.fmt(T / 2, 4)} m, BM = B^2/(12T) = {H.fmt(gmv['BM'], 4)} m, "
                f"GM = KB + BM - KG = {H.fmt(gmv['GM'], 4)} m, deslocamento = "
                f"{H.fmt(rho * V, 2)} t (rho = 1,025 t/m3).")
    with st.expander("Calculo manual de um angulo (procedimento para o relatorio)"):
        a_sel = st.selectbox("Angulo", ang, key="v1_manual")
        d = H.barcaca_gz_analitico(B, D, T, KG, a_sel)
        st.latex(r"h(y)=\mathrm{clamp}(c+y\tan\phi,\,0,\,D),\quad \int_{-B/2}^{B/2}h\,dy=BT")
        st.latex(r"Y_B=\frac{\int y\,h\,dy}{A},\quad Z_B=\frac{\int h^2/2\,dy}{A},\quad "
                 r"GZ=Y_B\cos\phi+(Z_B-KG)\sin\phi")
        _mostrar_df(pd.DataFrame({"Grandeza": list(d["passos"].keys()),
                                  "Valor": list(d["passos"].values())}), 6)
        st.markdown(f"Y_B = {H.fmt(d['Yb'], 6)} m  |  Z_B = {H.fmt(d['Zb'], 6)} m  |  "
                    f"**GZ = {H.fmt(d['GZ_exato'], 6)} m**")
    st.session_state["gz_val1"] = {"df": cmp, "param": {"L": L, "B": B, "D": D, "T": T, "KG": KG}}


# ---------------------------------------------------------------------------
# 5. validacao 2 - software ou referencia tecnica
# ---------------------------------------------------------------------------

def _aba_val2():
    g = st.session_state.get("gz")
    if g is None:
        st.info("Calcule a curva GZ da sua embarcacao na primeira aba. A referencia precisa ser "
                "comparada na MESMA condicao (deslocamento, KG, compasso, densidade).")
        return
    r, R = g["res"], g["res"]["resumo"]
    st.markdown(
        f"**Condicao comparada:** deslocamento {H.fmt(R['delta_t'], 3)} t, KG efetivo "
        f"{H.fmt(R['KG_efetivo'], 4)} m, compasso {H.fmt(R['compasso_m'], 3)} m, "
        f"rho {H.fmt(R['rho'], 3)} t/m3. Use exatamente estes valores no software de referencia.")
    ref_nome = st.text_input("Identificacao da referencia (software e versao, ou livro/artigo, "
                             "pagina e exemplo)", "", key="v2_nome")
    modo = st.radio("Como informar a curva de referencia", ["Enviar arquivo", "Colar a tabela"],
                    horizontal=True, key="v2_modo")
    df_ref = None
    try:
        if modo == "Enviar arquivo":
            arq = st.file_uploader("Arquivo com duas colunas: banda (graus) e GZ (m)",
                                   type=["csv", "txt", "tsv", "xlsx", "xls"], key="v2_arq")
            if arq is not None:
                if arq.name.lower().endswith((".xlsx", ".xls")):
                    df_ref = H.ler_curva_referencia(pd.read_excel(arq, header=None))
                else:
                    df_ref = H.ler_curva_referencia(arq.getvalue())
        else:
            txt = st.text_area("Cole aqui (banda e GZ, uma linha por angulo)", "", height=150,
                               key="v2_txt")
            if txt.strip():
                df_ref = H.ler_curva_referencia(txt)
    except Exception as err:                                        # noqa: BLE001
        st.error(f"Nao consegui ler a referencia: {err}")
    st.download_button("Baixar arquivo modelo", H.modelo_curva_referencia().encode("utf-8"),
                       "modelo_referencia_GZ.csv", "text/csv")
    with st.expander("Como obter a curva no Maxsurf Stability"):
        st.markdown(
            "1. Abra o mesmo casco, com a mesma tabela de cotas e a mesma escala.\n"
            "2. Defina o *loadcase* com o mesmo deslocamento e o mesmo KG (e o mesmo compasso); "
            "use a densidade da agua da sua analise.\n"
            "3. Rode a analise de estabilidade (GZ) de 0 ate a banda maxima, com passo de 5 graus ou menos.\n"
            "4. Copie ou exporte a tabela de resultados (banda em graus e GZ em metros) e cole ou envie aqui.\n"
            "5. Anote a versao do software e as opcoes (trim livre ou fixo, pontos de alagamento).")
    if df_ref is None:
        return
    if len(df_ref) < 3:
        st.warning("A referencia precisa de pelo menos tres angulos (o ideal e de cinco ou mais).")
    if df_ref["Banda (graus)"].max() > 90 or df_ref["Banda (graus)"].min() < 0:
        st.error("Os angulos de referencia precisam estar entre 0 e 90 graus.")
        return
    try:
        cmp = H.comparar_curvas(df_ref["Banda (graus)"], df_ref["GZ (m)"], r["motor"],
                                R["V_m3"], R["KG_efetivo"])
    except ValueError as err:
        st.error(str(err))
        return
    _fig(H.plot_comparacao_gz(cmp, ref_nome or "Referencia"))
    _mostrar_df(cmp, 5)
    d = cmp["Diferenca absoluta (m)"].to_numpy()
    p = cmp["Diferenca (%)"].abs()
    c = st.columns(4)
    c[0].metric("Maior diferenca absoluta", f"{np.max(np.abs(d)):.4f} m")
    c[1].metric("Diferenca RMS", f"{np.sqrt(np.mean(d ** 2)):.4f} m")
    c[2].metric("Maior diferenca (%)", "-" if not np.isfinite(p.max()) else f"{p.max():.2f} %")
    gmax_ref = float(df_ref["GZ (m)"].max())
    c[3].metric("GZ max: referencia", f"{gmax_ref:.4f} m",
                help=f"Aplicativo (refinado): {R['GZ_max']:.4f} m.")
    with st.expander("Causas provaveis de diferenca (para a discussao do relatorio)"):
        st.markdown(
            "- **Trim**: o aplicativo mantem o compasso fixo; o Maxsurf pode estar com trim livre.\n"
            "- **Geometria**: a malha de balizas e linhas d'agua e a interpolacao linear entre "
            "pontos nao reproduzem a superficie suave do modelo original.\n"
            "- **Conves e alagamento**: o aplicativo fecha o casco no conves (ultima linha d'agua); "
            "o software pode considerar superestrutura, pontos de alagamento ou apendices.\n"
            "- **Condicao**: deslocamento, KG, correcao de superficie livre e densidade precisam ser "
            "os mesmos; basta uma casa de diferenca no KG para mudar GZ de forma sistematica.\n"
            "- **Integracao**: regras de Simpson/Trapezio e numero de balizas.\n"
            "- **Valores proximos de zero**: o percentual perde sentido; use a diferenca absoluta.")
    st.session_state["gz_val2"] = {"df": cmp, "nome": ref_nome}


# ---------------------------------------------------------------------------
# 6. exportacao
# ---------------------------------------------------------------------------

def _excel(g) -> bytes:
    r, R, e = g["res"], g["res"]["resumo"], g["entrada"]
    bio = io.BytesIO()
    entradas = pd.DataFrame([
        ("Modo da condicao", e["modo"]), ("Deslocamento (t)", R["delta_t"]),
        ("Volume deslocado (m3)", R["V_m3"]), ("Densidade (t/m3)", R["rho"]),
        ("KG informado (m)", R["KG"]), ("GG0 (m)", R["GG0"]), ("KG efetivo (m)", R["KG_efetivo"]),
        ("Compasso fixo (m, + proa)", R["compasso_m"]), ("Banda maxima (graus)", e["phi_max"]),
        ("Passo (graus)", e["passo"]), ("Calado de equilibrio (m)", R["T_equilibrio"]),
    ], columns=["Parametro", "Valor"])
    resumo = pd.DataFrame([
        ("KB (m)", R["KB"]), ("GM inicial pela curva (m)", R["GM_numerico"]),
        ("GM inicial pela hidrostatica (m)", r["hid"]["GM_t"]), ("GZ maximo (m)", R["GZ_max"]),
        ("Banda do GZ maximo (graus)", R["ang_GZ_max"]),
        ("Fim da estabilidade positiva (graus)", R["ang_estab_nula"]),
        ("Imersao da borda do conves (graus)", R["ang_borda_conves"]),
        ("Momento de endireitamento maximo (t.m)", R["RM_max_tm"]),
        ("Momento de endireitamento maximo (kN.m)", R["RM_max_kNm"]),
        ("Reserva de empuxo (%)", R["reserva_empuxo_pct"]),
    ], columns=["Resultado", "Valor"])
    with pd.ExcelWriter(bio, engine="openpyxl") as xw:
        entradas.to_excel(xw, sheet_name="Entradas", index=False)
        r["df"].to_excel(xw, sheet_name="GZ", index=False)
        resumo.to_excel(xw, sheet_name="Resumo", index=False)
        pd.DataFrame(R["regioes"]).to_excel(xw, sheet_name="Regioes", index=False)
        v1 = st.session_state.get("gz_val1")
        if v1:
            v1["df"].to_excel(xw, sheet_name="Validacao1_barcaca", index=False)
            pd.DataFrame(list(v1["param"].items()), columns=["Parametro", "Valor"]).to_excel(
                xw, sheet_name="Validacao1_dados", index=False)
        v2 = st.session_state.get("gz_val2")
        if v2:
            v2["df"].to_excel(xw, sheet_name="Validacao2_referencia", index=False)
    return bio.getvalue()


def _aba_exportar():
    g = st.session_state.get("gz")
    if g is None:
        st.info("Calcule a curva na primeira aba.")
        return
    df = g["res"]["df"]
    st.markdown("Os arquivos trazem os angulos calculados, GZ, momento de endireitamento, "
                "os parametros usados e, se voce ja rodou, as duas validacoes.")
    c = st.columns(3)
    c[0].download_button("Excel completo (.xlsx)", _excel(g), "curva_GZ.xlsx",
                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    c[1].download_button("CSV (Excel em portugues: ; e virgula)", _csv_br(df), "curva_GZ_br.csv",
                         "text/csv")
    c[2].download_button("CSV (ponto decimal)", _csv_us(df), "curva_GZ.csv", "text/csv")


# ---------------------------------------------------------------------------
# pagina
# ---------------------------------------------------------------------------

def render():
    st.title("10. Curva de estabilidade (GZ)")
    st.caption("AP1.3 - braco de endireitamento calculado a partir da geometria do casco, com a "
               "carena recalculada em cada banda.")
    if not exige_completa():
        return
    tab = st.session_state.tab
    opt = opcoes()
    abas = st.tabs(["1. Condicao e calculo", "2. Curva e resultados", "3. Secao inclinada",
                    "4. Validacao 1 (analitica)", "5. Validacao 2 (referencia)", "6. Exportar"])
    with abas[0]:
        _aba_calculo(tab, opt)
    with abas[1]:
        _aba_resultados()
    with abas[2]:
        _aba_secao(tab)
    with abas[3]:
        _aba_val1()
    with abas[4]:
        _aba_val2()
    with abas[5]:
        _aba_exportar()
    botao_proximo("Relatorio final")
