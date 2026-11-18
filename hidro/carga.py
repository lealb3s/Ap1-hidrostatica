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
from .leitura import *       # noqa: F401,F403
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

# Colunas de momento sao recalculadas pelo programa, nunca lidas. Sem excluir
# essas palavras, um cabecalho "Momento longitudinal" seria tomado como a coluna
# do LCG, e o LCG sairia multiplicado pelo peso.
KW_MOMENTO = ["momento", "moment", "m.long", "m.vert", "w x", "w*"]

# Grandezas que so existem DEPOIS do calculo. Uma condicao de carga nunca as traz:
# se aparecem no cabecalho, o arquivo e uma tabela de resultados, e nao uma entrada.
# Sem essa checagem, a planilha-resumo das condicoes seria lida como se cada
# condicao fosse um item de peso, e o deslocamento sairia sendo a soma de todas.
KW_RESULTADO = ["t0", "lcb", "lcf", "mtc", "bml", "bm_l", "kml", "km_l", "kmt",
                "km_t", "gmt", "gm_t", "gml", "gm_l", "trim", "compasso", "theta",
                "calado", "awp", "a_wp", "tpc", "wsa", "deslocamento", "ta_m",
                "tf_m", "sentido"]

# Uma planilha de condicao de carga quase sempre termina com uma linha de total,
# e muitas trazem depois o LCG e o KG ja calculados. Somar essas linhas como se
# fossem itens dobra o deslocamento.
KW_TOTAL = ["total", "soma", "somatorio", "subtotal", "resultado", "deslocamento",
            "lcg calculado", "kg calculado", "vcg calculado", "delta", "sum"]


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


def _acha_coluna(rotulos, palavras, ja_usadas, proibidas=None):
    """
    Localiza a coluna cujo cabecalho casa com alguma palavra-chave.

    Termos de ate duas letras ("t", "w", "x", "z", "kg") so valem como palavra
    inteira: por substring, o "t" de "Momento (t.m)" casaria com a coluna de peso.
    `proibidas` descarta cabecalhos que contenham certos termos, o que mantem as
    colunas de momento fora da busca por coordenadas.
    """
    for c, rot in enumerate(rotulos):
        if c in ja_usadas or not rot:
            continue
        if proibidas and tem_kw(rot, proibidas):
            continue
        if tem_kw(rot, palavras):
            return c
    return None


def _linha_de_total(nome: str, peso, lcg, vcg) -> bool:
    """
    True quando a linha e um total ou um resultado ja calculado, e nao um item.

    Duas assinaturas: o nome diz "total", "soma" ou "LCG calculado"; ou ha peso
    sem nenhuma coordenada, que e como uma linha de total costuma aparecer.
    """
    if tem_kw(nome, KW_TOTAL):
        return True
    tem_peso = np.isfinite(peso) and abs(peso) > 1e-12
    sem_coord = not (np.isfinite(lcg) and abs(lcg) > 1e-12) and \
                not (np.isfinite(vcg) and abs(vcg) > 1e-12)
    return bool(tem_peso and sem_coord and not str(nome).strip())


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

    # Linha de cabecalho: a primeira em que "peso" e "LCG" aparecam em CELULAS
    # DIFERENTES. As duas exigencias importam. O casamento e por palavra inteira
    # para os termos curtos, senao o "t" de KW_PESO casa com qualquer frase; e as
    # celulas tem de ser distintas, senao uma nota de rodape que mencione peso e
    # LCG na mesma frase seria tomada por cabecalho.
    lin_cab = None
    for r in range(min(15, grade.shape[0])):
        rot = [normtxt(v) for v in grade.iloc[r].values]
        c_peso = next((c for c, t in enumerate(rot)
                       if t and tem_kw(t, KW_PESO) and not tem_kw(t, KW_MOMENTO)), None)
        c_lcg = next((c for c, t in enumerate(rot)
                      if t and tem_kw(t, KW_LCG) and not tem_kw(t, KW_MOMENTO)), None)
        if c_peso is not None and c_lcg is not None and c_peso != c_lcg:
            lin_cab = r
            break
    if lin_cab is None:
        raise RuntimeError(
            "Nao encontrei o cabecalho da condicao de carga. O arquivo precisa ter uma "
            "linha com os nomes das colunas, incluindo pelo menos uma com 'peso' e uma "
            "com 'LCG'.")

    rotulos = [normtxt(v) for v in grade.iloc[lin_cab].values]

    # O arquivo e mesmo uma condicao de carga, ou uma tabela de resultados?
    achadas = sorted({p for t in rotulos if t for p in KW_RESULTADO if tem_kw(t, [p])})
    if len(achadas) >= 3:
        raise RuntimeError(
            "Este arquivo parece uma TABELA DE RESULTADOS, e nao uma condicao de "
            "carga: o cabecalho traz " + ", ".join(achadas[:6]) +
            ". Essas grandezas sao calculadas pelo aplicativo, nunca informadas. "
            "Uma condicao de carga tem uma linha por item de peso, com as colunas "
            "de peso, LCG e VCG. Envie um dos arquivos 'condicao_...', ou baixe o "
            "modelo em branco logo abaixo.")

    usadas = set()
    mapa = {}
    for destino, palavras in (("Peso (t)", KW_PESO), ("LCG (m)", KW_LCG),
                              ("VCG (m)", KW_VCG), ("i_sup_livre (m4)", KW_IL),
                              ("rho_fluido (t/m3)", KW_RHOF), ("Item", KW_ITEM),
                              ("Observacao", KW_OBS)):
        # o LCG e procurado antes do VCG porque "vcg" tambem contem "cg"
        proibidas = None if destino in ("Item", "Observacao") else KW_MOMENTO
        c = _acha_coluna(rotulos, palavras, usadas, proibidas)
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

    # descarta linhas vazias e linhas de total
    peso = saida["Peso (t)"].to_numpy(float)
    lcg = saida["LCG (m)"].to_numpy(float)
    vcg = saida["VCG (m)"].to_numpy(float)
    nome = saida["Item"].astype(str).fillna("").tolist()

    manter, descartadas, notas_rodape = [], [], []
    for i in range(len(saida)):
        vazia = (not str(nome[i]).strip()) and (
            not np.isfinite(peso[i]) or abs(peso[i]) < 1e-12)
        if vazia:
            continue
        # linha de legenda ou nota de rodape: tem texto, mas nenhum numero em
        # peso nem em coordenada. Um item de peso zero, que o enunciado admite,
        # tem o zero escrito na celula e portanto passa por aqui.
        sem_numero = (not np.isfinite(peso[i]) and not np.isfinite(lcg[i])
                      and not np.isfinite(vcg[i]))
        if sem_numero:
            notas_rodape.append(str(nome[i]).strip()[:70])
            continue
        if _linha_de_total(nome[i], peso[i], lcg[i], vcg[i]):
            descartadas.append(f"{str(nome[i]).strip() or f'linha {i + 1}'}"
                               f" ({fmt(peso[i], 3)} t)")
            continue
        manter.append(i)
    saida = saida.iloc[manter].reset_index(drop=True)

    notas.append(f"Cabecalho reconhecido na linha {lin_cab + 1}; "
                 f"{len(saida)} item(ns) de peso lidos.")
    if descartadas:
        notas.append("Linha(s) de total ou de resultado ja calculado foram "
                     "IGNORADAS, para o deslocamento nao sair dobrado: "
                     + "; ".join(descartadas[:6]))
    if notas_rodape:
        notas.append("Linha(s) de texto sem nenhum numero foram tratadas como nota de "
                     "rodape e ignoradas: " + "; ".join(notas_rodape[:4]))
    cols_mom = [rotulos[c] for c in range(len(rotulos))
                if rotulos[c] and tem_kw(rotulos[c], KW_MOMENTO)]
    if cols_mom:
        notas.append("As colunas de momento do arquivo nao foram lidas: elas sao "
                     "recalculadas a partir dos pesos e das coordenadas, para que o "
                     "total sempre corresponda aos valores efetivamente usados.")
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


def reinterpolar_tabela_hidrostatica(df_ht: pd.DataFrame, pontos_extra=None) -> pd.DataFrame:
    """
    Cria uma nova Hydrostatic Table a partir da tabela imediatamente anterior.

    Esta funcao NAO recalcula o casco. Todos os valores da nova tabela sao obtidos
    por interpolacao linear da tabela recebida. Os calados da condicao atual
    (T0, Ta e Tf) sao incluidos como pontos adicionais para que a tabela da
    proxima condicao contenha explicitamente a condicao que acabou de ser
    calculada.

    A tabela original nunca e modificada.
    """
    if df_ht is None or not len(df_ht):
        raise ValueError("Nao ha Hydrostatic Table anterior para interpolar.")

    colT = coluna_calado(df_ht)
    if colT is None:
        raise ValueError("A tabela hidrostatica anterior nao possui coluna de calado.")

    base = df_ht.copy().reset_index(drop=True)
    Tbase = pd.to_numeric(base[colT], errors="coerce")
    bons = np.isfinite(Tbase.to_numpy(float))
    base = base.loc[bons].copy()
    Tbase = pd.to_numeric(base[colT], errors="coerce")
    if len(base) < 2:
        raise ValueError("A tabela hidrostatica anterior tem poucos pontos para interpolar.")

    ordem = np.argsort(Tbase.to_numpy(float))
    base = base.iloc[ordem].reset_index(drop=True)
    Tbase = pd.to_numeric(base[colT], errors="coerce").to_numpy(float)

    pontos = list(Tbase)
    for p in (pontos_extra or []):
        try:
            p = float(p)
        except (TypeError, ValueError):
            continue
        if not np.isfinite(p):
            continue
        if not (Tbase[0] - 1e-9 <= p <= Tbase[-1] + 1e-9):
            raise ValueError(
                f"O calado {p:.4f} m da condicao esta fora da faixa "
                f"da Hydrostatic Table-base ({Tbase[0]:.4f} a {Tbase[-1]:.4f} m). "
                "A tabela anterior precisa cobrir toda a condicao antes de seguir."
            )
        pontos.append(p)

    pontos = np.unique(np.round(np.asarray(pontos, dtype=float), 12))
    linhas = []
    for Tq in pontos:
        linha = {}
        for c in base.columns:
            if c == colT:
                linha[c] = float(Tq)
                continue
            vals = pd.to_numeric(base[c], errors="coerce").to_numpy(float)
            ok = np.isfinite(vals) & np.isfinite(Tbase)
            if ok.sum() >= 2:
                linha[c] = float(np.interp(Tq, Tbase[ok], vals[ok]))
            elif ok.sum() == 1:
                linha[c] = float(vals[ok][0])
            else:
                linha[c] = np.nan
        linhas.append(linha)

    return pd.DataFrame(linhas, columns=base.columns)


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


def lcg_para_referencia_tabela(tab: Tabela, lcg_informado: float, referencia: str = "ap") -> float:
    """Converte o LCG informado na referencia longitudinal usada pela tabela de cotas.

    ``tab.x`` e a referencia interna de TODOS os calculos hidrostaticos. A carga,
    porem, e normalmente informada a partir da AP (x=0). Se a tabela estiver
    centrada na meia-nau, comparar diretamente os dois numeros desloca o centro de
    gravidade e impede que o equilibrio longitudinal feche.

    referencias aceitas:
      - ``ap``: LCG informado a partir da AP (x = min(tab.x));
      - ``tabela``: LCG ja esta na referencia da coluna X da tabela;
      - ``meia_nau``: LCG informado a partir da meia-nau, positivo para vante.
    """
    x0 = float(np.min(tab.x))
    x1 = float(np.max(tab.x))
    lcg = float(lcg_informado)
    ref = str(referencia or "ap").lower()
    if ref in ("ap", "pp_re", "re"):
        return lcg + x0
    if ref in ("meia_nau", "meianau", "midship"):
        return lcg + 0.5 * (x0 + x1)
    if ref in ("tabela", "arquivo", "x_tabela"):
        return lcg
    raise ValueError(f"Referencia de LCG desconhecida: {referencia}")


def _equilibrio_inclinado_por_casco(tab: Tabela, opt: dict, delta: float, LCG: float,
                                    Ta0: float, Tf0: float) -> dict:
    """
    Resolve a condicao final de equilibrio para uma linha d'agua inclinada.

    O calculo procura dois desconhecidos: Ta e Tf. Para cada compasso t = Tf-Ta,
    primeiro e encontrada por bisseccao a elevacao da linha d'agua que produz o
    deslocamento Delta. Em seguida e avaliado o LCB da carena realmente submersa.
    O compasso final e aquele para o qual LCB = LCG.

    Diferentemente da versao anterior, uma tentativa que nao converge NAO e aceita
    como resultado final. Isso evita apresentar como equilibrio uma linha d'agua
    que ainda possui momento residual.
    """
    rho = float(opt.get("rho", 1.025))
    mz = opt.get("metodo_z", "auto")
    zb = z_base(tab)
    Tmax = calado_max(tab)
    xa = float(np.min(tab.x))
    xf = float(np.max(tab.x))
    L = xf - xa
    if L <= EPS or Tmax <= EPS:
        raise ValueError("Casco sem comprimento/calado suficientes para resolver o equilibrio.")

    ax, _, _ = pesos_integracao(tab.x, opt.get("metodo_x", "auto"))
    alvoV = delta / rho

    def propriedades(Ta, Tf):
        Ta = float(Ta)
        Tf = float(Tf)
        if not (np.isfinite(Ta) and np.isfinite(Tf)):
            return None
        drafts = Ta + (Tf - Ta) * (tab.x - xa) / L
        if np.min(drafts) < -1e-9 or np.max(drafts) > Tmax + 1e-9:
            return None
        drafts = np.clip(drafts, 0.0, Tmax)
        areas = np.zeros(tab.n_est)
        awp_y = np.zeros(tab.n_est)
        for i, Ti in enumerate(drafts):
            zs, ys = perfil_secao(tab, i, float(Ti), opt.get("sub_vertical"))
            az, _, _ = pesos_integracao(zs, mz)
            areas[i] = 2.0 * float(np.dot(az, ys)) if len(zs) >= 2 else 0.0
            awp_y[i] = max(0.0, y_interp_z(tab, i, zb + float(Ti)))
        V = float(np.dot(ax, areas))
        Mx = float(np.dot(ax, areas * tab.x))
        LCB = Mx / V if V > EPS else np.nan
        awp = 2.0 * float(np.dot(ax, awp_y))
        LCF = float(np.dot(ax, awp_y * tab.x) / awp) if awp > EPS else np.nan
        return {"V": V, "LCB": LCB, "LCF": LCF, "drafts": drafts}

    def resolver_ta_para_trim(t):
        """Para um compasso t, encontra Ta tal que V = Delta/rho."""
        # Para todos os calados ao longo do casco permanecerem entre 0 e Tmax:
        # Ta >= max(0,-t) e Ta <= min(Tmax,Tmax-t).
        lo = max(0.0, -float(t))
        hi = min(Tmax, Tmax - float(t))
        if hi < lo - 1e-12:
            return None

        qlo = propriedades(lo, lo + t)
        qhi = propriedades(hi, hi + t)
        if qlo is None or qhi is None:
            return None
        vlo, vhi = qlo["V"], qhi["V"]
        if alvoV < vlo - max(1e-9, 1e-8 * max(abs(alvoV), 1.0)):
            return None
        if alvoV > vhi + max(1e-9, 1e-8 * max(abs(alvoV), 1.0)):
            return None

        for _ in range(70):
            mid = 0.5 * (lo + hi)
            qm = propriedades(mid, mid + t)
            if qm is None:
                return None
            if abs(qm["V"] - alvoV) <= max(1e-9, 1e-9 * max(abs(alvoV), 1.0)):
                return mid, qm
            if qm["V"] < alvoV:
                lo = mid
            else:
                hi = mid
        mid = 0.5 * (lo + hi)
        qm = propriedades(mid, mid + t)
        return (mid, qm) if qm is not None else None

    def avaliacao_trim(t):
        r = resolver_ta_para_trim(float(t))
        if r is None:
            return None
        Ta, q = r
        return {"Ta": Ta, "Tf": Ta + float(t), "q": q,
                "erro": float(q["LCB"] - LCG)}

    # Usa a estimativa por MTC como ponto de partida, mas procura tambem em toda
    # a faixa admissivel para garantir que uma falha local de Newton nao esconda
    # a raiz fisica.
    t0 = float(Tf0 - Ta0) if np.isfinite(Ta0) and np.isfinite(Tf0) else 0.0
    tmax = float(Tmax)
    candidatos = np.unique(np.clip(np.r_[np.linspace(-tmax, tmax, 401), t0], -tmax, tmax))
    vals = []
    convergiu = False
    for t in candidatos:
        a = avaliacao_trim(float(t))
        if a is not None and np.isfinite(a["erro"]):
            vals.append((float(t), a))

    if not vals:
        raise ValueError("Nao foi possivel encontrar uma linha d'agua com o deslocamento informado dentro da faixa do casco.")

    # Primeiro, se houver um ponto praticamente equilibrado, usa-o.
    tol_lcb = max(1e-6, 1e-6 * max(L, 1.0))
    for t, a in vals:
        if abs(a["erro"]) <= tol_lcb:
            raiz = a
            t_raiz = t
            n_it = 0
            convergiu = True
            break
    else:
        # Procura uma mudança de sinal entre pontos consecutivos.
        vals.sort(key=lambda z: z[0])
        bracket = None
        for (ta_, a_), (tb_, b_) in zip(vals[:-1], vals[1:]):
            if a_["erro"] == 0.0 or a_["erro"] * b_["erro"] < 0.0:
                bracket = (ta_, a_, tb_, b_)
                break
        if bracket is None:
            melhor = min(vals, key=lambda z: abs(z[1]["erro"]))
            raise ValueError(
                "Nao foi encontrada uma condicao de equilibrio em que LCB = LCG. "
                f"Menor diferenca encontrada: {melhor[1]['erro']:.6g} m. "
                "Isso indica que a faixa de calados/geometria ou a referencia longitudinal "
                "da condicao de carga precisa ser conferida."
            )

        lo_t, lo_a, hi_t, hi_a = bracket
        raiz = None
        t_raiz = None
        n_it = 0
        for n_it in range(1, 70):
            mid_t = 0.5 * (lo_t + hi_t)
            mid_a = avaliacao_trim(mid_t)
            if mid_a is None:
                break
            if abs(mid_a["erro"]) <= tol_lcb:
                raiz = mid_a
                t_raiz = mid_t
                convergiu = True
                break
            if lo_a["erro"] * mid_a["erro"] <= 0.0:
                hi_t, hi_a = mid_t, mid_a
            else:
                lo_t, lo_a = mid_t, mid_a
        if raiz is None:
            # Ultima media do intervalo; somente aceita se realmente satisfizer
            # a tolerancia. Caso contrario, nao mascara a falta de convergencia.
            mid_t = 0.5 * (lo_t + hi_t)
            mid_a = avaliacao_trim(mid_t)
            if mid_a is None or abs(mid_a["erro"]) > tol_lcb:
                raise ValueError("O equilibrio longitudinal nao convergiu para LCB = LCG.")
            raiz = mid_a
            t_raiz = mid_t
            convergiu = True

    q = raiz["q"]
    Ta = float(raiz["Ta"])
    Tf = float(raiz["Tf"])
    t = Tf - Ta
    theta = np.degrees(np.arctan2(t, L))
    return {
        "Ta": Ta, "Tf": Tf, "t_m": float(t), "t_cm": float(t * 100.0),
        "theta": float(theta), "LCB_final": float(q["LCB"]),
        "LCF_final": float(q["LCF"]), "volume_final": float(q["V"]),
        "delta_final": float(rho * q["V"]), "convergiu": bool(convergiu),
        "iteracoes": int(n_it),
        "erro_lcb_lcg": float(q["LCB"] - LCG),
    }


def equilibrio(tab, opt: dict, soma: dict, df_ht: pd.DataFrame,
               modo_mtc: str = "aproximado", refinar: bool = False,
               referencia_lcg: str = "ap") -> dict:
    """
    Calcula o equilibrio longitudinal usando SOMENTE a Hydrostatic Table
    fornecida como base da condicao atual.

    A sequencia do AP1.2 e deliberadamente encadeada:
        tabela original -> condicao 1 -> nova tabela interpolada -> condicao 2
        -> nova tabela interpolada -> condicao 3 -> ...

    A Hydrostatic Table continua sendo a base da condicao e fornece T0, LCB(T0),
    LCF e MTC por interpolacao. Como uma tabela convencional nao contem o LCB de
    uma linha d'agua inclinada, a estimativa MTC e usada como ponto inicial de um
    refinamento final pela geometria do casco, fechando volume e momento.
    """
    delta = float(soma["delta"])
    LCG_informado = float(soma["LCG"])
    LCG = lcg_para_referencia_tabela(tab, LCG_informado, referencia_lcg)
    KG = float(soma.get("KG_corr", np.nan))

    busca = calado_por_deslocamento(df_ht, delta)
    T0 = busca["T0"]

    # As propriedades de LCB/LCF/BM_l/KM_l tambem sao obtidas por interpolacao
    # da mesma tabela-base da condicao, e nao por um novo calculo geometrico.
    consulta = consultar_curva(df_ht, T0)

    def _num(prefixo, padrao=np.nan):
        for c, v in consulta.items():
            if str(c).startswith(prefixo):
                try:
                    return float(v)
                except (TypeError, ValueError):
                    return padrao
        return padrao

    LCB = _num("LCB")
    LCF = _num("LCF")
    BML = _num("BM_l")
    KML = _num("KM_l")
    KMT = _num("KM_t")
    GML = KML - KG if np.isfinite(KG) and np.isfinite(KML) else np.nan
    GMT = KMT - KG if np.isfinite(KG) and np.isfinite(KMT) else np.nan

    xa = float(np.min(tab.x))
    xf = float(np.max(tab.x))
    L = xf - xa

    # LCB(T0) e a referencia da aproximacao classica M_trim/MTC. Ela nao e o
    # LCB da condicao final, porque a lamina d'agua deixa de ser horizontal
    # quando existe trim. Primeiro calculamos a estimativa classica.
    LCB_T0 = LCB
    M_trim = delta * (LCG - LCB_T0)
    MTC = mtc(delta, L, BML, GML, modo_mtc)
    t_cm_mtc = M_trim / MTC if (np.isfinite(MTC) and abs(MTC) > EPS) else np.nan
    t_m_mtc = t_cm_mtc / 100.0 if np.isfinite(t_cm_mtc) else np.nan

    braco_re = LCF - xa
    braco_vante = xf - LCF
    Ta_mtc = T0 - (braco_re / L) * t_m_mtc if (L > 0 and np.isfinite(t_m_mtc)) else np.nan
    Tf_mtc = T0 + (braco_vante / L) * t_m_mtc if (L > 0 and np.isfinite(t_m_mtc)) else np.nan

    # A Hydrostatic Table comum so conhece curvas para linhas d'agua horizontais.
    # Para a condicao final, em que Ta != Tf, o LCB correto precisa ser obtido
    # da carena efetivamente submersa pela lamina inclinada. Usamos a estimativa
    # MTC acima apenas como ponto inicial e fechamos simultaneamente volume e
    # momento longitudinal. Assim LCB_final nao e imposto artificialmente: ele
    # resulta do equilibrio e deve coincidir numericamente com o LCG.
    final = _equilibrio_inclinado_por_casco(
        tab, opt, delta, LCG, Ta_mtc, Tf_mtc
    )
    Ta = final["Ta"]
    Tf = final["Tf"]
    t_m = final["t_m"]
    t_cm = final["t_cm"]
    theta = final["theta"]
    LCB_final = final["LCB_final"]
    LCF_final = final["LCF_final"]

    if not np.isfinite(t_m):
        sentido = "indeterminado"
    elif abs(t_m) < 1e-9:
        sentido = "sem trim (quilha paralela)"
    elif t_m > 0:
        sentido = "aproado (trim pela proa)"
    else:
        sentido = "apopado (trim pela popa)"

    r = {"LCB": LCB_T0, "LCB_T0": LCB_T0, "LCB_final": LCB_final,
         "LCF": LCF, "LCF_final": LCF_final, "BML": BML, "KML": KML,
         "GML": GML, "KMT": KMT, "GMT": GMT, "KG": KG, "T": T0}
    return {"delta": delta, "LCG": LCG, "LCG_informado": LCG_informado,
            "referencia_lcg": referencia_lcg, "KG": KG, "T0": T0, "busca": busca,
            "refino": None, "r": r, "LCB": LCB_T0, "LCB_T0": LCB_T0,
            "LCB_final": LCB_final, "LCF": LCF, "LCF_final": LCF_final, "BML": BML,
            "KML": KML, "GML": GML, "KMT": KMT, "GMT": GMT,
            "MTC": MTC, "modo_mtc": modo_mtc, "M_trim": M_trim,
            "t_cm_mtc": t_cm_mtc, "t_m_mtc": t_m_mtc,
            "Ta_mtc": Ta_mtc, "Tf_mtc": Tf_mtc,
            "t_cm": t_cm, "t_m": t_m, "Ta": Ta, "Tf": Tf, "theta": theta,
            "equilibrio_final_exato": bool(final["convergiu"]),
            "iteracoes_equilibrio": final["iteracoes"],
            "volume_final": final["volume_final"],
            "delta_final": final["delta_final"],
            "M_residual_final": delta * (LCG - LCB_final),
            "sentido": sentido, "xa": xa, "xf": xf, "L": L,
            "braco_re": braco_re, "braco_vante": braco_vante,
            "tabela_base": df_ht.copy()}


def tabela_resultado(eq: dict, soma: dict, nome_condicao: str = "") -> pd.DataFrame:
    """Tabela-resumo da condicao, nos tres grupos pedidos pelo enunciado."""
    linhas = [
        ("Condicao de carga", "Nome da condicao", nome_condicao or "(sem nome)", ""),
        ("Condicao de carga", "Numero de itens", soma.get("n_itens", ""), ""),
        ("Condicao de carga", "Delta (deslocamento)", soma["delta"], "t"),
        ("Condicao de carga", "Soma dos momentos longitudinais", soma["soma_mom_l"], "t.m"),
        ("Condicao de carga", "LCG informado", eq.get("LCG_informado", soma["LCG"]), "m"),
        ("Condicao de carga", "Referencia do LCG", eq.get("referencia_lcg", "ap"), ""),
        ("Condicao de carga", "LCG na referencia da tabela", eq["LCG"], "m"),
        ("Condicao de carga", "Soma dos momentos verticais", soma["soma_mom_v"], "t.m"),
        ("Condicao de carga", "KG sem correcao", soma["KG"], "m"),
        ("Condicao de carga", "Correcao de superficie livre GG0", soma["GG0"], "m"),
        ("Condicao de carga", "KG corrigido", soma["KG_corr"], "m"),
        ("Hidrostatica em T0", "T0 (calado de equilibrio sem trim)", eq["T0"], "m"),
        ("Hidrostatica em T0", "LCB em T0 (referencia do trim)", eq["LCB_T0"], "m"),
        ("Equilibrio longitudinal", "LCB final", eq["LCB_final"], "m"),
        ("Equilibrio longitudinal", "LCG", eq["LCG"], "m"),
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
            {"Etapa": "2. LCG informado", "Valor": eq.get("LCG_informado", soma["LCG"]), "Unidade": "m"},
            {"Etapa": "2b. LCG convertido para a referencia da tabela", "Valor": eq["LCG"], "Unidade": "m"},
            {"Etapa": "3. T0 interpolado na Hydrostatic Table",
             "Valor": eq["busca"]["T0"], "Unidade": "m"},
            {"Etapa": "3. Momento de trim", "Valor": eq["M_trim"], "Unidade": "t.m"},
            {"Etapa": "4. MTC", "Valor": eq["MTC"], "Unidade": "t.m/cm"},
            {"Etapa": "5. Compasso", "Valor": eq["t_cm"], "Unidade": "cm"},
            {"Etapa": "6. Calado na popa", "Valor": eq["Ta"], "Unidade": "m"},
            {"Etapa": "7. Calado na proa", "Valor": eq["Tf"], "Unidade": "m"},
        ]).to_excel(w, sheet_name="Auditoria", index=False)
    return buf.getvalue()
