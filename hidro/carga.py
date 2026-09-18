# -*- coding: utf-8 -*-
"""
AP1.2 - Condicao de carga, equilibrio longitudinal e trim.

Este modulo NAO recalcula geometria: ele consome a tabela de cotas e a Hydrostatic
Table ja produzidas pelo AP1.1. A cadeia implementada e

    condicao de carga -> Delta, LCG e KG -> hidrostatica em T0 -> momento de trim
    -> calado de popa e de proa -> lamina d'agua

CONVENCAO DE SINAIS (fixada aqui e usada em todo o modulo)

    x cresce de RE para VANTE, na mesma referencia da tabela de cotas.
    AP = menor x da tabela;  FP = maior x da tabela;  L = FP - AP.

    Momento de trim = Delta * (LCG - LCB).
      LCG a vante do LCB  -> momento positivo -> aproa (trim pela PROA), Tf > Ta.
      LCG a re do LCB     -> momento negativo -> apopa (trim pela POPA), Ta > Tf.

    O compasso t e a diferenca Tf - Ta, com o mesmo sinal do momento.
    O calado no LCF permanece igual a T0: e em torno do centro de flutuacao que
    o navio gira, e nao em torno da meia-nau.
"""

import io

import numpy as np
import pandas as pd

from .base import *          # noqa: F401,F403
from .hidrostatica import *  # noqa: F401,F403


COLUNAS_CARGA = ["Item", "Peso (t)", "LCG (m)", "VCG (m)",
                 "i_sup_livre (m4)", "rho_fluido (t/m3)", "Observacao"]

KW_ITEM = ["item", "denominacao", "descricao", "nome", "peso morto", "tanque",
           "carga", "designacao"]
KW_PESO = ["peso", "w", "massa", "weight", "t"]
KW_LCG = ["lcg", "x", "longitudinal", "posicao longitudinal"]
KW_VCG = ["vcg", "kg", "z", "vertical", "altura"]
KW_IL = ["i sup", "i_sup", "superficie livre", "free surface", "inercia", "i livre",
         "isl", "i t"]
KW_RHOF = ["rho", "densidade", "massa especifica", "density"]
KW_OBS = ["obs", "observacao", "percentual", "nota", "comentario"]


# ---------------------------------------------------------------------------
# S11 - LEITURA E VALIDACAO DA CONDICAO DE CARGA (Modulo 8)
# ---------------------------------------------------------------------------

def condicao_vazia(n_linhas: int = 6) -> pd.DataFrame:
    """Tabela de condicao de carga em branco, pronta para ser preenchida."""
    return pd.DataFrame({
        "Item": [""] * n_linhas,
        "Peso (t)": [0.0] * n_linhas,
        "LCG (m)": [0.0] * n_linhas,
        "VCG (m)": [0.0] * n_linhas,
        "i_sup_livre (m4)": [0.0] * n_linhas,
        "rho_fluido (t/m3)": [0.0] * n_linhas,
        "Observacao": [""] * n_linhas,
    })


def _acha_coluna(rotulos, palavras, ja_usadas):
    for c, rot in enumerate(rotulos):
        if c in ja_usadas or not rot:
            continue
        if any(p in rot for p in palavras):
            return c
    return None


def ler_condicao(arquivo) -> tuple:
    """
    Le uma condicao de carga de .xlsx ou .csv e devolve (DataFrame, notas).

    Reconhece os cabecalhos por palavra-chave, do mesmo modo que a leitura da
    tabela de cotas: o usuario nao precisa nomear as colunas exatamente como o
    programa espera. As colunas de momento nao sao lidas, e sim recalculadas, para
    que o total sempre corresponda aos pesos e posicoes efetivamente usados.
    """
    abas = ler_arquivo_bruto(arquivo)
    grade = limpar_grade(list(abas.values())[0])
    notas = []

    # linha de cabecalho: a primeira que contenha "peso" e alguma coordenada
    lin_cab = None
    for r in range(min(12, grade.shape[0])):
        rot = [normtxt(v) for v in grade.iloc[r].values]
        if any(any(p in t for p in KW_PESO) for t in rot if t) and \
           any(any(p in t for p in KW_LCG) for t in rot if t):
            lin_cab = r
            break
    if lin_cab is None:
        raise RuntimeError(
            "Nao encontrei o cabecalho da condicao de carga. O arquivo precisa ter uma "
            "linha com os nomes das colunas, incluindo pelo menos uma com 'peso' e uma "
            "com 'LCG'.")

    rotulos = [normtxt(v) for v in grade.iloc[lin_cab].values]
    usadas = set()
    mapa = {}
    for destino, palavras in (("Peso (t)", KW_PESO), ("LCG (m)", KW_LCG),
                              ("VCG (m)", KW_VCG), ("i_sup_livre (m4)", KW_IL),
                              ("rho_fluido (t/m3)", KW_RHOF), ("Item", KW_ITEM),
                              ("Observacao", KW_OBS)):
        # o LCG e procurado antes do VCG porque "vcg" tambem contem "cg"
        c = _acha_coluna(rotulos, palavras, usadas)
        if c is not None:
            mapa[destino] = c
            usadas.add(c)
    if "Peso (t)" not in mapa or "LCG (m)" not in mapa:
        raise RuntimeError("O arquivo precisa ter, no minimo, uma coluna de peso e uma "
                           "coluna de LCG.")
    if "Item" not in mapa:
        livres = [c for c in range(grade.shape[1]) if c not in usadas]
        if livres:
            mapa["Item"] = livres[0]
            notas.append(f"A coluna {livres[0] + 1} foi adotada como nome do item.")

    dados = grade.iloc[lin_cab + 1:]
    saida = condicao_vazia(0)
    for destino in COLUNAS_CARGA:
        if destino in mapa:
            col = dados.iloc[:, mapa[destino]]
            if destino in ("Item", "Observacao"):
                saida[destino] = [("" if v is None or str(v) == "nan" else str(v).strip())
                                  for v in col]
            else:
                saida[destino] = [para_float(v) for v in col]
        else:
            saida[destino] = "" if destino in ("Item", "Observacao") else 0.0
            if destino not in ("Observacao", "i_sup_livre (m4)", "rho_fluido (t/m3)"):
                notas.append(f"Coluna '{destino}' nao encontrada: preenchida com zero.")

    # descarta linhas totalmente vazias
    peso = saida["Peso (t)"].to_numpy(float)
    nome = saida["Item"].astype(str).str.strip()
    manter = ~((nome == "") & (~np.isfinite(peso) | (np.abs(np.nan_to_num(peso)) < 1e-12)))
    saida = saida[manter].reset_index(drop=True)
    notas.append(f"Cabecalho reconhecido na linha {lin_cab + 1}; "
                 f"{len(saida)} item(ns) de peso lidos.")
    return saida, notas


def validar_condicao(df: pd.DataFrame, tab=None, principais=None) -> list:
    """
    Verifica a condicao de carga e devolve a lista de achados (ERRO ou AVISO),
    no mesmo formato do diagnostico da tabela de cotas.
    """
    ach = []
    principais = principais or {}

    def A(cod, nivel, tit, onde, expl, cons, sug=""):
        ach.append(Achado(cod, nivel, tit, onde, expl, cons, sug))

    if df is None or not len(df):
        A("CG-VAZIA", "ERRO", "Condicao de carga sem itens", "tabela de pesos",
          "Nenhum item de peso foi informado.",
          "Sem pesos nao ha deslocamento, e nenhum calado de equilibrio pode ser "
          "determinado.",
          "Acrescente os itens de peso ou importe um arquivo de condicao de carga.")
        return ach

    peso = df["Peso (t)"].to_numpy(float)
    lcg = df["LCG (m)"].to_numpy(float)
    vcg = df["VCG (m)"].to_numpy(float)
    nomes = df["Item"].astype(str).tolist()

    # --- celulas vazias ou nao numericas -----------------------------------
    for coluna, vetor in (("Peso (t)", peso), ("LCG (m)", lcg), ("VCG (m)", vcg)):
        faltando = [i for i in range(len(vetor)) if not np.isfinite(vetor[i])]
        if faltando:
            A("CG-VAZIO", "ERRO", f"Celulas vazias ou nao numericas em {coluna}",
              "itens " + ", ".join(nomes[i] or f"linha {i + 1}" for i in faltando[:8]),
              f"Ha itens sem valor numerico em {coluna}.",
              "O somatorio de pesos e de momentos nao pode ser fechado: Delta, LCG e "
              "KG ficam indefinidos.",
              "Preencha os valores ou remova as linhas que nao sao itens de peso.")

    # --- peso total --------------------------------------------------------
    total = float(np.nansum(peso))
    if abs(total) < 1e-9:
        A("CG-ZERO", "ERRO", "Peso total nulo", f"soma dos pesos = {fmt(total)} t",
          "A soma dos pesos da condicao de carga e zero.",
          "Sem deslocamento nao existe calado de equilibrio.",
          "Informe os pesos dos itens.")

    # --- pesos negativos ---------------------------------------------------
    neg = [i for i in range(len(peso)) if np.isfinite(peso[i]) and peso[i] < -1e-9]
    if neg:
        A("CG-NEG", "AVISO", "Pesos negativos",
          ", ".join(nomes[i] or f"linha {i + 1}" for i in neg[:8]),
          "Ha itens com peso negativo.",
          "Peso negativo so faz sentido como remocao deliberada de um item ja "
          "contabilizado. Se nao for esse o caso, Delta, LCG e KG ficam errados.",
          "Confirme se a remocao e intencional; caso contrario corrija o sinal.")

    # --- coordenadas fora do casco -----------------------------------------
    if tab is not None and len(tab.x):
        x0, x1 = float(np.min(tab.x)), float(np.max(tab.x))
        fora = [i for i in range(len(lcg))
                if np.isfinite(lcg[i]) and not (x0 - 1e-9 <= lcg[i] <= x1 + 1e-9)]
        if fora:
            A("CG-LCG", "AVISO", "LCG fora da extensao do casco",
              ", ".join(f"{nomes[i] or f'linha {i + 1}'} (LCG = {fmt(lcg[i])} m)"
                        for i in fora[:8]),
              f"A tabela de cotas vai de x = {fmt(x0)} m a x = {fmt(x1)} m, e esses "
              "itens estao fora dessa faixa.",
              "Pode ser referencia longitudinal diferente da usada na tabela de cotas. "
              "Nesse caso LCG, o momento de trim e os calados de ponta saem todos "
              "deslocados.",
              "Confirme que o LCG esta medido na mesma referencia da coluna X da "
              "tabela de cotas.")
        zt = float(np.max(tab.z))
        alto = [i for i in range(len(vcg))
                if np.isfinite(vcg[i]) and vcg[i] > 3 * zt and peso[i] > 1e-9]
        if alto:
            A("CG-VCG", "AVISO", "VCG muito acima do pontal coberto pela tabela",
              ", ".join(f"{nomes[i] or f'linha {i + 1}'} (VCG = {fmt(vcg[i])} m)"
                        for i in alto[:8]),
              f"A tabela de cotas cobre ate z = {fmt(zt)} m.",
              "Um VCG muito alto eleva o KG e reduz o GM. Se for erro de unidade ou de "
              "referencia, a estabilidade calculada fica irreal.",
              "Confirme a unidade e a referencia vertical desses itens.")

    # --- superficie livre ---------------------------------------------------
    il = df["i_sup_livre (m4)"].to_numpy(float)
    rhof = df["rho_fluido (t/m3)"].to_numpy(float)
    sem_rho = [i for i in range(len(il))
               if np.isfinite(il[i]) and il[i] > 1e-9
               and (not np.isfinite(rhof[i]) or rhof[i] <= 1e-9)]
    if sem_rho:
        A("CG-SL", "AVISO", "Superficie livre sem densidade do fluido",
          ", ".join(nomes[i] or f"linha {i + 1}" for i in sem_rho[:8]),
          "Esses itens tem momento de inercia de superficie livre informado, mas nao "
          "tem a densidade do fluido.",
          "Sera adotada densidade 1,000 t/m3 para esses tanques, o que subestima a "
          "correcao se o fluido for mais denso que agua doce.",
          "Informe a densidade do fluido de cada tanque com superficie livre.")

    return ach


# ---------------------------------------------------------------------------
# S12 - SOMATORIO DE PESOS (Modulo 9)
# ---------------------------------------------------------------------------

def somatorio(df: pd.DataFrame) -> dict:
    """
    Fecha a condicao de carga.

        Delta = soma dos pesos
        LCG   = soma(w * LCG) / Delta
        KG    = soma(w * VCG) / Delta

    A correcao de superficie livre eleva virtualmente o centro de gravidade:

        GG0 = soma(rho_fluido * i) / Delta        KG_corrigido = KG + GG0

    onde i e o momento de inercia da superficie livre do tanque em relacao ao seu
    proprio eixo longitudinal. O peso do liquido ja entra normalmente na soma: a
    correcao trata apenas do efeito do liquido escorregar para o bordo baixo.
    """
    peso = np.nan_to_num(df["Peso (t)"].to_numpy(float))
    lcg = np.nan_to_num(df["LCG (m)"].to_numpy(float))
    vcg = np.nan_to_num(df["VCG (m)"].to_numpy(float))
    il = np.nan_to_num(df["i_sup_livre (m4)"].to_numpy(float))
    rhof = np.nan_to_num(df["rho_fluido (t/m3)"].to_numpy(float))
    rhof = np.where((il > 1e-9) & (rhof <= 1e-9), 1.0, rhof)

    mom_l = peso * lcg
    mom_v = peso * vcg
    mom_sl = rhof * il

    delta = float(np.sum(peso))
    det = df.copy()
    det["Momento long. (t.m)"] = mom_l
    det["Momento vert. (t.m)"] = mom_v
    det["Momento sup. livre (t.m)"] = mom_sl

    if abs(delta) < 1e-12:
        return {"delta": 0.0, "LCG": np.nan, "KG": np.nan, "KG_corr": np.nan,
                "GG0": np.nan, "soma_mom_l": float(np.sum(mom_l)),
                "soma_mom_v": float(np.sum(mom_v)),
                "soma_mom_sl": float(np.sum(mom_sl)), "detalhe": det}

    LCG = float(np.sum(mom_l) / delta)
    KG = float(np.sum(mom_v) / delta)
    GG0 = float(np.sum(mom_sl) / delta)
    return {"delta": delta, "LCG": LCG, "KG": KG, "KG_corr": KG + GG0, "GG0": GG0,
            "soma_mom_l": float(np.sum(mom_l)), "soma_mom_v": float(np.sum(mom_v)),
            "soma_mom_sl": float(np.sum(mom_sl)), "detalhe": det,
            "n_itens": int(len(df))}


# ---------------------------------------------------------------------------
# S13 - CONSULTA HIDROSTATICA PELO DESLOCAMENTO (Modulo 10)
# ---------------------------------------------------------------------------

def calado_por_deslocamento(df_ht: pd.DataFrame, delta: float) -> dict:
    """
    Localiza na Hydrostatic Table o calado que corresponde ao deslocamento Delta,
    interpolando linearmente entre as duas linhas vizinhas.
    """
    colT = coluna_calado(df_ht)
    colD = None
    for c in df_ht.columns:
        if str(c).startswith("Delta (deslocamento)"):
            colD = c
            break
    if colT is None or colD is None:
        raise ValueError("A Hydrostatic Table precisa ter as colunas de calado e de "
                         "deslocamento. Gere-a na etapa 6 antes de continuar.")
    T = df_ht[colT].to_numpy(float)
    D = df_ht[colD].to_numpy(float)
    bons = np.isfinite(T) & np.isfinite(D)
    T, D = T[bons], D[bons]
    ordem = np.argsort(D)
    T, D = T[ordem], D[ordem]
    if len(D) < 2:
        raise ValueError("A Hydrostatic Table tem poucos calados para interpolar.")

    extrapolou = not (D[0] - 1e-9 <= delta <= D[-1] + 1e-9)
    T0 = float(np.interp(delta, D, T))

    # linhas vizinhas, para a auditoria
    j = int(np.clip(np.searchsorted(D, delta), 1, len(D) - 1))
    return {"T0": T0, "extrapolou": extrapolou,
            "D_min": float(D[0]), "D_max": float(D[-1]),
            "T_inf": float(T[j - 1]), "T_sup": float(T[j]),
            "D_inf": float(D[j - 1]), "D_sup": float(D[j])}


def calado_por_busca(tab, opt: dict, delta: float, tol: float = 1e-6,
                     max_iter: int = 60) -> dict:
    """
    Refina o calado resolvendo rho * Vol(T) = Delta por bisseccao no proprio
    nucleo hidrostatico, sem passar pela tabela. Serve para medir quanto a
    interpolacao da Hydrostatic Table custou em precisao.
    """
    rho = float(opt.get("rho", 1.025))
    lo, hi = 0.0, float(calado_max(tab))
    if rho * hidrostatica(tab, hi, opt)["VOL"] < delta:
        return {"T": hi, "convergiu": False, "iteracoes": 0,
                "delta_obtido": rho * hidrostatica(tab, hi, opt)["VOL"]}
    it = 0
    for it in range(1, max_iter + 1):
        meio = 0.5 * (lo + hi)
        d = rho * hidrostatica(tab, meio, opt)["VOL"]
        if abs(d - delta) <= tol * max(delta, 1.0):
            return {"T": meio, "convergiu": True, "iteracoes": it, "delta_obtido": d}
        if d < delta:
            lo = meio
        else:
            hi = meio
    meio = 0.5 * (lo + hi)
    return {"T": meio, "convergiu": False, "iteracoes": it,
            "delta_obtido": rho * hidrostatica(tab, meio, opt)["VOL"]}


# ---------------------------------------------------------------------------
# S14 - EQUILIBRIO LONGITUDINAL (Modulo 11)
# ---------------------------------------------------------------------------

def mtc(delta: float, L: float, BML: float = None, GML: float = None,
        modo: str = "aproximado") -> float:
    """
    Momento para alterar o trim em um centimetro, em t.m/cm.

        aproximado:  MTC = Delta * BM_l / (100 L)
        exato:       MTC = Delta * GM_l / (100 L),  com GM_l = KM_l - KG

    A forma aproximada dispensa o KG e e a que o enunciado admite por padrao. A
    exata e mais correta, porem so existe quando o KG da condicao e conhecido.
    """
    if not L or L <= 0 or not np.isfinite(delta):
        return np.nan
    if modo == "exato" and GML is not None and np.isfinite(GML):
        return float(delta * GML / (100.0 * L))
    if BML is not None and np.isfinite(BML):
        return float(delta * BML / (100.0 * L))
    return np.nan


def equilibrio(tab, opt: dict, soma: dict, df_ht: pd.DataFrame,
               modo_mtc: str = "aproximado", refinar: bool = True) -> dict:
    """
    Calcula o equilibrio longitudinal da condicao de carga.

    Passos, na ordem em que sao apresentados na auditoria:
      1. T0 pelo deslocamento, interpolado na Hydrostatic Table
      2. propriedades hidrostaticas em T0, calculadas diretamente pelo nucleo
      3. momento de trim = Delta * (LCG - LCB)
      4. compasso t = momento / MTC
      5. calados de popa e de proa, girando em torno do LCF
    """
    delta = float(soma["delta"])
    LCG = float(soma["LCG"])
    KG = float(soma.get("KG_corr", np.nan))

    busca = calado_por_deslocamento(df_ht, delta)
    T0 = busca["T0"]
    refino = None
    if refinar:
        refino = calado_por_busca(tab, opt, delta)
        if refino.get("convergiu"):
            T0 = refino["T"]

    r = hidrostatica(tab, T0, {**opt, "KG": KG if np.isfinite(KG) else 0.0})

    xa = float(np.min(tab.x))                 # perpendicular de re
    xf = float(np.max(tab.x))                 # perpendicular de vante
    L = xf - xa
    LCB, LCF = r["LCB"], r["LCF"]
    BML, KML = r["BML"], r["KML"]
    GML = KML - KG if np.isfinite(KG) else np.nan

    M_trim = delta * (LCG - LCB)              # t.m ; positivo = aproa
    MTC = mtc(delta, L, BML, GML, modo_mtc)
    t_cm = M_trim / MTC if (np.isfinite(MTC) and abs(MTC) > EPS) else np.nan
    t_m = t_cm / 100.0 if np.isfinite(t_cm) else np.nan

    # o navio gira em torno do centro de flutuacao: o calado no LCF continua T0
    braco_re = LCF - xa
    braco_vante = xf - LCF
    Ta = T0 - (braco_re / L) * t_m if (L > 0 and np.isfinite(t_m)) else np.nan
    Tf = T0 + (braco_vante / L) * t_m if (L > 0 and np.isfinite(t_m)) else np.nan
    theta = np.degrees(np.arctan2(t_m, L)) if np.isfinite(t_m) else np.nan

    if not np.isfinite(t_m):
        sentido = "indeterminado"
    elif abs(t_m) < 1e-9:
        sentido = "sem trim (quilha paralela)"
    elif t_m > 0:
        sentido = "aproado (trim pela proa)"
    else:
        sentido = "apopado (trim pela popa)"

    return {"delta": delta, "LCG": LCG, "KG": KG, "T0": T0, "busca": busca,
            "refino": refino, "r": r, "LCB": LCB, "LCF": LCF, "BML": BML,
            "KML": KML, "GML": GML, "KMT": r["KMT"], "GMT": r["KMT"] - KG,
            "MTC": MTC, "modo_mtc": modo_mtc, "M_trim": M_trim,
            "t_cm": t_cm, "t_m": t_m, "Ta": Ta, "Tf": Tf, "theta": theta,
            "sentido": sentido, "xa": xa, "xf": xf, "L": L,
            "braco_re": braco_re, "braco_vante": braco_vante}


def tabela_resultado(eq: dict, soma: dict, nome_condicao: str = "") -> pd.DataFrame:
    """Tabela-resumo da condicao, nos tres grupos pedidos pelo enunciado."""
    linhas = [
        ("Condicao de carga", "Nome da condicao", nome_condicao or "(sem nome)", ""),
        ("Condicao de carga", "Numero de itens", soma.get("n_itens", ""), ""),
        ("Condicao de carga", "Delta (deslocamento)", soma["delta"], "t"),
        ("Condicao de carga", "Soma dos momentos longitudinais", soma["soma_mom_l"], "t.m"),
        ("Condicao de carga", "LCG", soma["LCG"], "m"),
        ("Condicao de carga", "Soma dos momentos verticais", soma["soma_mom_v"], "t.m"),
        ("Condicao de carga", "KG sem correcao", soma["KG"], "m"),
        ("Condicao de carga", "Correcao de superficie livre GG0", soma["GG0"], "m"),
        ("Condicao de carga", "KG corrigido", soma["KG_corr"], "m"),
        ("Hidrostatica em T0", "T0 (calado de equilibrio sem trim)", eq["T0"], "m"),
        ("Hidrostatica em T0", "LCB", eq["LCB"], "m"),
        ("Hidrostatica em T0", "LCF", eq["LCF"], "m"),
        ("Hidrostatica em T0", "BM_l", eq["BML"], "m"),
        ("Hidrostatica em T0", "KM_l", eq["KML"], "m"),
        ("Hidrostatica em T0", "GM_l", eq["GML"], "m"),
        ("Hidrostatica em T0", "KM_t", eq["KMT"], "m"),
        ("Hidrostatica em T0", "GM_t", eq["GMT"], "m"),
        ("Hidrostatica em T0", f"MTC ({eq['modo_mtc']})", eq["MTC"], "t.m/cm"),
        ("Equilibrio longitudinal", "Momento de trim", eq["M_trim"], "t.m"),
        ("Equilibrio longitudinal", "Compasso t", eq["t_cm"], "cm"),
        ("Equilibrio longitudinal", "Compasso t", eq["t_m"], "m"),
        ("Equilibrio longitudinal", "X da perpendicular de re", eq["xa"], "m"),
        ("Equilibrio longitudinal", "X da perpendicular de vante", eq["xf"], "m"),
        ("Equilibrio longitudinal", "Calado na popa Ta", eq["Ta"], "m"),
        ("Equilibrio longitudinal", "Calado na proa Tf", eq["Tf"], "m"),
        ("Equilibrio longitudinal", "Angulo de trim", eq["theta"], "graus"),
        ("Equilibrio longitudinal", "Sentido", eq["sentido"], ""),
    ]
    return pd.DataFrame(linhas, columns=["Grupo", "Grandeza", "Valor", "Unidade"])


def resultado_para_exibir(df: pd.DataFrame) -> pd.DataFrame:
    """
    Versao da tabela-resumo pronta para a tela.

    A coluna de valores mistura numeros e texto (o sentido do trim, o nome da
    condicao). Uma coluna assim nao pode ser exibida diretamente: o Streamlit
    converte a tabela para Arrow e falha ao tentar ler "aproado" como numero.
    Aqui cada valor vira texto ja formatado.
    """
    d = df.copy()

    def _mostra(v):
        if isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, bool):
            return fmt(v, 4)
        return "" if v is None else str(v)

    d["Valor"] = d["Valor"].map(_mostra)
    return d


def excel_condicao(df_carga: pd.DataFrame, soma: dict, eq: dict,
                   nome_condicao: str = "") -> bytes:
    """Exporta a condicao de carga e o resultado do equilibrio para .xlsx."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        tabela_resultado(eq, soma, nome_condicao).to_excel(
            w, sheet_name="Resultado", index=False)
        soma["detalhe"].to_excel(w, sheet_name="Condicao de carga", index=False)
        pd.DataFrame([
            {"Etapa": "1. Deslocamento", "Valor": soma["delta"], "Unidade": "t"},
            {"Etapa": "2. T0 interpolado na Hydrostatic Table",
             "Valor": eq["busca"]["T0"], "Unidade": "m"},
            {"Etapa": "2b. T0 refinado por busca direta",
             "Valor": (eq["refino"] or {}).get("T", np.nan), "Unidade": "m"},
            {"Etapa": "3. Momento de trim", "Valor": eq["M_trim"], "Unidade": "t.m"},
            {"Etapa": "4. MTC", "Valor": eq["MTC"], "Unidade": "t.m/cm"},
            {"Etapa": "5. Compasso", "Valor": eq["t_cm"], "Unidade": "cm"},
            {"Etapa": "6. Calado na popa", "Valor": eq["Ta"], "Unidade": "m"},
            {"Etapa": "7. Calado na proa", "Valor": eq["Tf"], "Unidade": "m"},
        ]).to_excel(w, sheet_name="Auditoria", index=False)
    return buf.getvalue()
