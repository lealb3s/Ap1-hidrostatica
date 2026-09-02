# -*- coding: utf-8 -*-
"""Nucleo hidrostatico: areas seccionais, plano d'agua, volumes, centros,
metacentro, coeficientes, superficie molhada e Hydrostatic Table."""

import io
import re
import base64
import datetime as _dt
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st

from .base import *       # noqa: F401,F403
from .tabela import *     # noqa: F401,F403
from .integracao import *  # noqa: F401,F403


# ============================================================================ #
# S6 - NUCLEO HIDROSTATICO                                                     #
# ============================================================================ #
#
# Convencao interna:
#   z_base  = altura da primeira linha d'agua (linha de base do casco)
#   T       = calado medido a PARTIR de z_base
#   nivel   = z_base + T  (altura absoluta na tabela)
#   x       = como consta na tabela; a origem de apresentacao e escolhida pelo usuario
# ---------------------------------------------------------------------------

def z_base(tab: Tabela) -> float:
    return float(tab.z[0])


def calado_max(tab: Tabela) -> float:
    return float(tab.z[-1] - tab.z[0])


def malha_vertical(tab: Tabela, T: float):
    """Niveis z de z_base ate z_base+T, incluindo o calado como ultimo ponto."""
    zb = z_base(tab)
    nivel = zb + T
    zs = [z for z in tab.z if z <= nivel + 1e-9]
    if not zs:
        zs = [zb]
    if abs(zs[-1] - nivel) > 1e-9:
        zs = zs + [nivel]
    return np.array(zs, float)


def y_interp_z(tab: Tabela, i: int, zq: float) -> float:
    """Meia-boca da baliza i na altura zq (interpolacao linear; extremos mantidos)."""
    y = tab.Y[i]
    if not np.isfinite(y).any():
        return 0.0
    return float(np.interp(zq, tab.z, np.nan_to_num(y, nan=0.0)))


def perfil_secao(tab: Tabela, i: int, T: float):
    """(zs, ys) do contorno submerso da baliza i para o calado T."""
    zs = malha_vertical(tab, T)
    ys = np.array([y_interp_z(tab, i, zz) for zz in zs], float)
    return zs, ys


# --- S6.1 Areas seccionais (Modulo 4) --------------------------------------

def areas_seccionais(tab: Tabela, T: float, metodo="auto"):
    """
    A_i(T) = 2 * integral de y dz, de z_base ate z_base+T, para cada baliza.
    Retorna (A, detalhes) onde detalhes traz a tabela passo a passo por baliza.
    """
    A = np.zeros(tab.n_est)
    detalhes = []
    for i in range(tab.n_est):
        zs, ys = perfil_secao(tab, i, T)
        if len(zs) < 2:
            A[i] = 0.0
            detalhes.append({"baliza": tab.rotulos[i], "df": pd.DataFrame(), "aud": [],
                             "meia_area": 0.0, "area": 0.0})
            continue
        a, mult, plano = pesos_integracao(zs, metodo)
        meia = float(np.dot(a, ys))
        A[i] = 2.0 * meia
        df = pd.DataFrame({"z (m)": zs, "y (m)": ys, "mult.": mult,
                           "a_i": a, "a_i * y": a * ys})
        _, aud = integrar(zs, ys, metodo, "WL")
        detalhes.append({"baliza": tab.rotulos[i], "x": float(tab.x[i]), "df": df,
                         "aud": aud, "meia_area": meia, "area": float(A[i])})
    return A, detalhes


# --- S6.2 Plano d'agua, LCF e inercias (Modulo 5) --------------------------

def plano_dagua(tab: Tabela, T: float, metodo="auto", eixo_IL="LCF"):
    """
    A_WP = 2 * int y dx ; LCF = int x*2y dx / A_WP
    I_t  = (2/3) * int y^3 dx                      (eixo longitudinal de simetria)
    I_l  = int x^2 * 2y dx - A_WP * LCF^2          (eixo transversal pelo LCF)
    """
    nivel = z_base(tab) + T
    x = tab.x
    y = np.array([y_interp_z(tab, i, nivel) for i in range(tab.n_est)], float)
    y = np.clip(y, 0.0, None)

    a, mult, plano = pesos_integracao(x, metodo)
    AWP = 2.0 * float(np.dot(a, y))
    Mx = 2.0 * float(np.dot(a, y * x))                 # momento estatico em relacao a x=0
    LCF = Mx / AWP if abs(AWP) > EPS else np.nan
    IT = (2.0 / 3.0) * float(np.dot(a, y ** 3))
    IL0 = 2.0 * float(np.dot(a, y * x ** 2))           # em relacao a x=0
    if eixo_IL == "LCF" and np.isfinite(LCF):
        IL = IL0 - AWP * LCF ** 2                      # teorema dos eixos paralelos
        eixo_txt = f"eixo transversal pelo LCF (x = {fmt(LCF)} m)"
    else:
        xm = 0.5 * (x[0] + x[-1])
        IL = IL0 - AWP * xm ** 2
        eixo_txt = f"eixo transversal pela meia-nau (x = {fmt(xm)} m)"

    df = pd.DataFrame({"x (m)": x, "y (m)": y, "mult.": mult, "a_i": a,
                       "a_i * y": a * y, "a_i * y * x": a * y * x,
                       "a_i * y^3": a * y ** 3, "a_i * y * x^2": a * y * x ** 2})
    _, aud = integrar(x, y, metodo, "estacoes")

    largura = 2.0 * float(np.max(y)) if len(y) else np.nan
    molhados = np.where(y > 1e-9)[0]
    LWL = float(x[molhados[-1]] - x[molhados[0]]) if len(molhados) >= 2 else float(x[-1] - x[0])

    return {"AWP": AWP, "LCF": LCF, "IT": IT, "IL": IL, "IL0": IL0, "Mx": Mx,
            "y": y, "df": df, "aud": aud, "eixo_IL": eixo_txt,
            "BWL": largura, "LWL": LWL}


# --- S6.3 Volumes (Modulo 6) ----------------------------------------------

def volumes(tab: Tabela, T: float, metodo_x="auto", metodo_z="auto"):
    """
    Vol_L = int A(x) dx        (integracao longitudinal)
    Vol_V = int A_WP(z) dz     (integracao vertical, caminho independente)
    E_vol = |Vol_L - Vol_V| / |Vol_L| * 100
    Tambem devolve LCB (do caminho longitudinal) e KB (do caminho vertical).
    """
    A, det_A = areas_seccionais(tab, T, metodo_z)
    x = tab.x
    ax, multx, _ = pesos_integracao(x, metodo_x)
    VOL_L = float(np.dot(ax, A))
    Mx = float(np.dot(ax, A * x))
    LCB = Mx / VOL_L if abs(VOL_L) > EPS else np.nan
    df_L = pd.DataFrame({"x (m)": x, "A(x) (m2)": A, "mult.": multx, "a_i": ax,
                         "a_i * A": ax * A, "a_i * A * x": ax * A * x})
    _, aud_L = integrar(x, A, metodo_x, "estacoes")

    zs = malha_vertical(tab, T)
    AWPz = np.array([plano_dagua(tab, zz - z_base(tab), metodo_x)["AWP"] for zz in zs], float)
    az, multz, _ = pesos_integracao(zs, metodo_z)
    VOL_V = float(np.dot(az, AWPz))
    Mz = float(np.dot(az, AWPz * (zs - z_base(tab))))
    KB = Mz / VOL_V if abs(VOL_V) > EPS else np.nan
    df_V = pd.DataFrame({"z (m)": zs, "z - z_base (m)": zs - z_base(tab),
                         "A_WP(z) (m2)": AWPz, "mult.": multz, "a_i": az,
                         "a_i * A_WP": az * AWPz,
                         "a_i * A_WP * z": az * AWPz * (zs - z_base(tab))})
    _, aud_V = integrar(zs, AWPz, metodo_z, "WL")

    E = abs(VOL_L - VOL_V) / abs(VOL_L) * 100 if abs(VOL_L) > EPS else np.nan
    return {"A": A, "det_A": det_A, "VOL_L": VOL_L, "VOL_V": VOL_V, "E_VOL": E,
            "LCB": LCB, "KB": KB, "df_L": df_L, "df_V": df_V,
            "aud_L": aud_L, "aud_V": aud_V, "AWPz": AWPz, "zs": zs}


# --- S6.4 Superficie molhada (item 18) -------------------------------------

def superficie_molhada(tab: Tabela, T: float, metodo_x="auto"):
    """
    Metodo do perimetro molhado (girth):
      1) em cada baliza, o contorno submerso e discretizado pelos pontos (y, z)
         da tabela, de z_base ate o calado;
      2) o semi-perimetro vale  s_i = y(z_base) + SOMA sqrt(dy^2 + dz^2)
         (a primeira parcela representa a meia-largura do fundo chato);
      3) WSA = 2 * integral de s(x) dx.
    Limitacao: nao inclui as areas de popa espelhada nem de proa, e depende da
    quantidade de linhas d'agua disponiveis.
    """
    s = np.zeros(tab.n_est)
    for i in range(tab.n_est):
        zs, ys = perfil_secao(tab, i, T)
        comp = float(ys[0])                      # meia-largura do fundo
        comp += float(np.sum(np.sqrt(np.diff(ys) ** 2 + np.diff(zs) ** 2)))
        s[i] = comp
    a, mult, _ = pesos_integracao(tab.x, metodo_x)
    WSA = 2.0 * float(np.dot(a, s))
    df = pd.DataFrame({"x (m)": tab.x, "semi-perimetro s (m)": s, "a_i": a, "a_i * s": a * s})
    return WSA, df


# --- S6.5 Conjunto completo para um calado --------------------------------

def hidrostatica(tab: Tabela, T: float, opt: dict) -> dict:
    """Calcula todas as propriedades hidrostaticas para o calado T."""
    mx = opt.get("metodo_x", "auto")
    mz = opt.get("metodo_z", "auto")
    rho = float(opt.get("rho", 1.025))
    eixo_IL = opt.get("eixo_IL", "LCF")

    v = volumes(tab, T, mx, mz)
    pw = plano_dagua(tab, T, mx, eixo_IL)
    WSA, df_wsa = superficie_molhada(tab, T, mx)

    escolha = opt.get("volume_adotado", "longitudinal")
    VOL = {"longitudinal": v["VOL_L"], "vertical": v["VOL_V"],
           "media": 0.5 * (v["VOL_L"] + v["VOL_V"])}[escolha]

    AWP, LCF, IT, IL = pw["AWP"], pw["LCF"], pw["IT"], pw["IL"]
    KB, LCB = v["KB"], v["LCB"]

    BMT = IT / VOL if abs(VOL) > EPS else np.nan
    BML = IL / VOL if abs(VOL) > EPS else np.nan
    KMT = KB + BMT
    KML = KB + BML
    DESL = rho * VOL
    TPC = rho * AWP / 100.0

    AM = float(np.max(v["A"])) if len(v["A"]) else np.nan
    i_am = int(np.argmax(v["A"])) if len(v["A"]) else -1

    # comprimento e boca de referencia para os coeficientes
    L = float(opt.get("LPP")) if opt.get("L_ref", "LPP") == "LPP" and opt.get("LPP") else pw["LWL"]
    B = float(opt.get("B")) if opt.get("B_ref", "BWL") == "B" and opt.get("B") else pw["BWL"]

    CB = VOL / (L * B * T) if L and B and T > EPS else np.nan
    CWP = AWP / (L * B) if L and B else np.nan
    CM = AM / (B * T) if B and T > EPS else np.nan
    CP = VOL / (AM * L) if AM and L and abs(AM) > EPS else np.nan

    r = {"T": T, "nivel": z_base(tab) + T,
         "VOL_L": v["VOL_L"], "VOL_V": v["VOL_V"], "VOL": VOL, "E_VOL": v["E_VOL"],
         "DESL": DESL, "LCB": LCB, "LCF": LCF, "KB": KB,
         "BMT": BMT, "KMT": KMT, "BML": BML, "KML": KML,
         "AWP": AWP, "IT": IT, "IL": IL, "TPC": TPC, "WSA": WSA,
         "AM": AM, "i_AM": i_am, "BWL": pw["BWL"], "LWL": pw["LWL"],
         "CB": CB, "CWP": CWP, "CM": CM, "CP": CP,
         "L_usado": L, "B_usado": B, "rho": rho,
         "_vol": v, "_pw": pw, "_wsa_df": df_wsa}
    return r


def converter_origem(valor_x, tab: Tabela, origem: str, LPP=None):
    """Converte uma abscissa da referencia da tabela para a referencia de apresentacao."""
    if valor_x is None or not np.isfinite(valor_x):
        return np.nan
    x0, x1 = float(tab.x[0]), float(tab.x[-1])
    if origem == "tabela":
        return valor_x
    if origem == "pp_re":            # x = 0 na perpendicular de re
        return valor_x - min(x0, x1)
    if origem == "meia_nau":         # x = 0 na meia-nau (positivo para vante)
        return valor_x - 0.5 * (x0 + x1)
    return valor_x


# ============================================================================ #
# S7 - HYDROSTATIC TABLE E HYDROSTATIC CURVES                                  #
# ============================================================================ #

def tabela_hidrostatica(tab: Tabela, Tmin, Tmax, dT, opt: dict, barra=None):
    """Executa o calculo para T1, T2, ..., Tn e devolve DataFrame + lista bruta."""
    if dT <= 0:
        raise ValueError("O incremento de calado deve ser positivo.")
    n = int(np.floor((Tmax - Tmin) / dT + 1e-9)) + 1
    calados = [Tmin + k * dT for k in range(n)]
    if calados and abs(calados[-1] - Tmax) > 1e-9 and calados[-1] < Tmax:
        calados.append(Tmax)

    linhas, brutos = [], []
    for k, T in enumerate(calados):
        if T <= 1e-9:
            continue
        r = hidrostatica(tab, T, opt)
        brutos.append(r)
        linha = {}
        for chave, (rot, uni, casas) in PROPRIEDADES.items():
            if chave in r:
                val = r[chave]
                if chave in ("LCB", "LCF"):
                    val = converter_origem(val, tab, opt.get("origem_x", "tabela"),
                                           opt.get("LPP"))
                linha[f"{rot} [{uni}]"] = val
        linhas.append(linha)
        if barra is not None:
            barra.progress(min(1.0, (k + 1) / max(len(calados), 1)))
    return pd.DataFrame(linhas), brutos


def consultar_curva(df: pd.DataFrame, T_consulta: float) -> dict:
    """Interpola numericamente um ponto qualquer das curvas hidrostaticas."""
    colT = [c for c in df.columns if c.startswith("T (calado)")][0]
    Ts = df[colT].to_numpy(float)
    saida = {"T [m]": T_consulta}
    for c in df.columns:
        if c == colT:
            continue
        vals = df[c].to_numpy(float)
        bons = np.isfinite(vals)
        saida[c] = float(np.interp(T_consulta, Ts[bons], vals[bons])) if bons.sum() >= 2 else np.nan
    return saida


def verificacoes_internas(r: dict) -> pd.DataFrame:
    """Validacao 2 do enunciado: consistencia interna."""
    linhas = []

    def add(nome, esperado, obtido, unidade=""):
        erro = abs(obtido - esperado)
        rel = erro / abs(esperado) * 100 if abs(esperado) > EPS else np.nan
        linhas.append({"Verificacao": nome, "Esperado": esperado, "Obtido": obtido,
                       "Erro absoluto": erro, "Erro (%)": rel, "Unidade": unidade})

    add("Volume longitudinal x vertical", r["VOL_L"], r["VOL_V"], "m3")
    add("KM_t = KB + BM_t", r["KB"] + r["BMT"], r["KMT"], "m")
    add("KM_l = KB + BM_l", r["KB"] + r["BML"], r["KML"], "m")
    add("C_B = C_M * C_P", r["CM"] * r["CP"], r["CB"], "-")
    add("Delta = rho * Vol", r["rho"] * r["VOL"], r["DESL"], "t")
    return pd.DataFrame(linhas)


def barcaca_teste(L=40.0, B=10.0, D=5.0, n_est=11, n_wl=11) -> Tabela:
    """Barcaca paralelepipedica para a Validacao 1 (solucao analitica conhecida)."""
    x = np.linspace(0.0, L, n_est)
    z = np.linspace(0.0, D, n_wl)
    Y = np.full((n_est, n_wl), B / 2.0)
    t = nova_tabela(x, z, Y, [str(i) for i in range(n_est)])
    return t


def validacao_analitica(r: dict, L, B, T, rho=1.025) -> pd.DataFrame:
    """Compara o resultado do aplicativo com a solucao analitica da barcaca."""
    ana = {"Vol (m3)": L * B * T, "KB (m)": T / 2.0, "LCB (m)": L / 2.0,
           "LCF (m)": L / 2.0, "A_WP (m2)": L * B, "BM_t (m)": B ** 2 / (12.0 * T),
           "C_B": 1.0, "C_WP": 1.0, "C_M": 1.0, "C_P": 1.0,
           "Delta (t)": rho * L * B * T}
    app = {"Vol (m3)": r["VOL"], "KB (m)": r["KB"], "LCB (m)": r["LCB"],
           "LCF (m)": r["LCF"], "A_WP (m2)": r["AWP"], "BM_t (m)": r["BMT"],
           "C_B": r["CB"], "C_WP": r["CWP"], "C_M": r["CM"], "C_P": r["CP"],
           "Delta (t)": r["DESL"]}
    linhas = []
    for k in ana:
        a, b = ana[k], app[k]
        err = abs(b - a) / abs(a) * 100 if abs(a) > EPS else np.nan
        linhas.append({"Grandeza": k, "Analitico": a, "Aplicativo": b, "Erro (%)": err})
    return pd.DataFrame(linhas)


def auditoria_por_calado(tab: Tabela, calados, metodo_x="auto", metodo_z="auto"):
    """
    Para cada calado, informa quantas linhas d'agua entram na integracao vertical
    e quais regras sao efetivamente aplicadas nos dois eixos.

    Isso responde a pergunta "o metodo se comporta igual em todos os calados?".
    A resposta costuma ser NAO: em calados baixos entram poucas linhas d'agua e o
    aplicativo cai para o Trapezio; alem disso, quando o calado nao coincide com
    uma linha d'agua, o ultimo trecho e parcial e tambem vira Trapezio.
    """
    linhas = []
    plano_x = planejar_integracao(tab.x, metodo_x)
    regra_x = " ; ".join(f"{a}-{b}: {m}" for a, b, m in plano_x)
    for T in calados:
        zs = malha_vertical(tab, T)
        plano_z = planejar_integracao(zs, metodo_z)
        regras = [m for _, _, m in plano_z]
        parcial = abs((z_base(tab) + T) - tab.z[np.searchsorted(
            tab.z, z_base(tab) + T, side="right") - 1]) > 1e-9
        linhas.append({
            "T (m)": float(T),
            "WL usadas": len(zs),
            "Intervalos": len(zs) - 1,
            "Regras no eixo z": " ; ".join(f"{a}-{b}: {m}" for a, b, m in plano_z) or "-",
            "So Simpson?": "sim" if regras and all("Simpson" in m for m in regras) else "nao",
            "Ultimo trecho parcial": "sim" if parcial else "nao",
            "Regras no eixo x": regra_x,
        })
    return pd.DataFrame(linhas)


def coerencia_alturas(tab: Tabela, principais: dict) -> str:
    """
    Verifica se a altura total coberta pelas linhas d'agua faz sentido diante das
    dimensoes informadas. Retorna texto de alerta, ou string vazia se estiver bem.
    Este e o teste que pega o erro mais destrutivo de todos: alturas z lidas da
    linha errada da planilha, o que colapsa a faixa de calados possiveis.
    """
    alt = float(tab.z[-1] - tab.z[0])
    comp = float(abs(tab.x[-1] - tab.x[0]))
    D = principais.get("D") or 0.0
    Td = principais.get("Td") or 0.0
    B = principais.get("B") or 0.0
    problemas = []
    if alt <= 1e-9:
        problemas.append("a altura total coberta e nula")
    if comp > 1e-9 and alt > 1e-9 and alt < 0.02 * comp:
        problemas.append(f"a altura coberta ({fmt(alt)} m) e menos de 2 % do comprimento "
                         f"({fmt(comp)} m), o que nenhuma embarcacao real apresenta")
    if D > 0 and alt > 1e-9 and (alt < 0.3 * D or alt > 3.0 * D):
        problemas.append(f"a altura coberta ({fmt(alt)} m) destoa do pontal informado "
                         f"({fmt(D)} m)")
    if Td > 0 and alt > 1e-9 and alt < Td:
        problemas.append(f"a altura coberta ({fmt(alt)} m) e menor que o proprio calado de "
                         f"projeto ({fmt(Td)} m): o calado de projeto ficaria inalcancavel")
    if B > 0 and alt > 1e-9 and alt < 0.05 * B:
        problemas.append(f"a altura coberta ({fmt(alt)} m) e despropositada diante da boca "
                         f"({fmt(B)} m)")
    return "; ".join(problemas)
