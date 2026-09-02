# -*- coding: utf-8 -*-
"""Modelo canonico da tabela de cotas, diagnostico geometrico e interpolacao."""

import io
import re
import base64
import datetime as _dt
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st

from .base import *  # noqa: F401,F403


# ============================================================================ #
# S3 - MODELO CANONICO DA TABELA DE COTAS E DIAGNOSTICO                        #
# ============================================================================ #

@dataclass
class Tabela:
    """
    Tabela de trabalho. O arquivo original NUNCA e alterado: esta e uma copia.
      x        : (n_est,)          posicoes longitudinais [m]
      z        : (n_wl,)           alturas das linhas d'agua [m]
      Y        : (n_est, n_wl)     meias-bocas [m]
      original : (n_est, n_wl)     mascara True = valor veio do arquivo
      origem   : (n_est, n_wl)     texto explicando a origem de cada celula preenchida
      rotulos  : nomes das balizas conforme o arquivo
    """
    x: np.ndarray
    z: np.ndarray
    Y: np.ndarray
    original: np.ndarray
    origem: np.ndarray
    rotulos: list
    unidade: str = "m (metro)"

    def copia(self):
        return Tabela(self.x.copy(), self.z.copy(), self.Y.copy(),
                      self.original.copy(), self.origem.copy(),
                      list(self.rotulos), self.unidade)

    @property
    def n_est(self):
        return len(self.x)

    @property
    def n_wl(self):
        return len(self.z)

    def como_df(self) -> pd.DataFrame:
        """Visao com WL nas colunas e balizas nas linhas (estrutura do documento)."""
        cols = [f"WL{j} (z={fmt(self.z[j], 3)})" for j in range(self.n_wl)]
        df = pd.DataFrame(self.Y, columns=cols)
        df.insert(0, "X", self.x)
        df.insert(0, "Baliza", self.rotulos)
        return df

    def n_interpolados(self) -> int:
        return int((~self.original & np.isfinite(self.Y)).sum())


def nova_tabela(x, z, Y, rotulos=None, unidade="m (metro)") -> Tabela:
    x = np.asarray(x, float)
    z = np.asarray(z, float)
    Y = np.asarray(Y, float)
    original = np.isfinite(Y)
    origem = np.where(original, "arquivo", "vazio").astype(object)
    if rotulos is None:
        rotulos = [str(i) for i in range(len(x))]
    return Tabela(x, z, Y, original, origem, list(rotulos), unidade)


def converter_unidade(tab: Tabela, de: str, para: str) -> Tabela:
    """Converte x, z e Y de uma unidade para outra. Os calculos internos sao em metros."""
    f = UNIDADES[de] / UNIDADES[para]
    t = tab.copia()
    t.x = t.x * f
    t.z = t.z * f
    t.Y = t.Y * f
    t.unidade = para
    return t


# ---------------------------------------------------------------------------
# S3.1 - DIAGNOSTICO (Modulo 2 / item 6 do enunciado)
# Detecta, localiza, explica e apresenta consequencias. Nao corrige nada.
# ---------------------------------------------------------------------------

def diagnosticar(tab: Tabela, principais: dict) -> list:
    ach = []

    def A(cod, nivel, tit, onde, expl, cons, sug=""):
        ach.append(Achado(cod, nivel, tit, onde, expl, cons, sug))

    x, z, Y = tab.x, tab.z, tab.Y
    B = principais.get("B")
    L = principais.get("LPP")

    # --- estruturais -------------------------------------------------------
    if tab.n_est < 3:
        A("EST-MIN", "ERRO", "Poucas estacoes",
          f"{tab.n_est} estacao(oes)",
          "A integracao longitudinal precisa de pelo menos 3 estacoes.",
          "Volume, LCB, LCF e A_WP nao podem ser calculados de forma confiavel.",
          "Importe uma tabela com mais balizas ou acrescente estacoes por interpolacao.")
    if tab.n_wl < 3:
        A("WL-MIN", "ERRO", "Poucas linhas d'agua",
          f"{tab.n_wl} linha(s) d'agua",
          "A integracao vertical precisa de pelo menos 3 linhas d'agua.",
          "Areas seccionais, volume vertical e KB ficam sem base numerica.",
          "Importe mais linhas d'agua ou gere-as por interpolacao.")

    # --- duplicatas --------------------------------------------------------
    dupx = [i for i in range(1, len(x)) if abs(x[i] - x[i - 1]) < 1e-9]
    if dupx:
        A("EST-DUP", "ERRO", "Estacoes duplicadas",
          "estacoes " + ", ".join(str(i) for i in dupx),
          "Duas ou mais estacoes ocupam a mesma posicao longitudinal X.",
          "O espacamento h fica nulo em um trecho: a integracao longitudinal "
          "perde area e o volume sai subestimado.",
          "Remova a estacao repetida ou corrija a posicao X.")
    dupz = [j for j in range(1, len(z)) if abs(z[j] - z[j - 1]) < 1e-9]
    if dupz:
        A("WL-DUP", "ERRO", "Linhas d'agua duplicadas",
          "linhas d'agua " + ", ".join(str(j) for j in dupz),
          "Duas ou mais linhas d'agua tem a mesma altura z.",
          "A integracao vertical perde altura: areas seccionais e KB ficam errados.",
          "Corrija a altura repetida.")

    # --- ordenacao ---------------------------------------------------------
    if not np.all(np.diff(x) > 0):
        cres = np.all(np.diff(x) < 0)
        A("EST-ORD", "AVISO", "Estacoes fora de ordem crescente",
          "coluna X",
          ("As posicoes X estao em ordem decrescente."
           if cres else "As posicoes X nao estao ordenadas."),
          "Integrais longitudinais podem resultar negativas ou incoerentes; "
          "LCB e LCF podem sair invertidos.",
          "O aplicativo pode reordenar as estacoes por X (com seu aval).")
    if not np.all(np.diff(z) > 0):
        A("WL-ORD", "AVISO", "Linhas d'agua fora de ordem crescente",
          "cabecalho das linhas d'agua",
          "As alturas z nao estao em ordem crescente.",
          "Areas seccionais e volume vertical podem ficar negativos ou truncados.",
          "O aplicativo pode reordenar as linhas d'agua (com seu aval).")

    # --- celulas vazias / nao numericas ------------------------------------
    faltando = np.argwhere(~np.isfinite(Y))
    if len(faltando):
        amostra = ", ".join(f"(baliza {tab.rotulos[i]}, WL{j})" for i, j in faltando[:8])
        extra = "" if len(faltando) <= 8 else f" ... e mais {len(faltando) - 8}."
        A("CEL-VAZIA", "AVISO", "Celulas vazias ou nao numericas",
          f"{len(faltando)} celula(s): {amostra}{extra}",
          "Ha posicoes da tabela sem um valor numerico reconhecido.",
          "Toda integral que passe por esses pontos fica incompleta: area seccional, "
          "A_WP, volume, centros e curvas hidrostaticas podem ficar errados naquela regiao.",
          "Va ao Modulo 3 e escolha como preencher (interpolacao, zero ou valor manual). "
          "Voce tambem pode editar a celula diretamente na tabela de trabalho.")

    # --- valores negativos -------------------------------------------------
    neg = np.argwhere(np.isfinite(Y) & (Y < -1e-9))
    if len(neg):
        A("Y-NEG", "AVISO", "Meias-bocas negativas",
          ", ".join(f"(baliza {tab.rotulos[i]}, WL{j})" for i, j in neg[:8]),
          "Meia-boca e uma distancia a partir do plano de simetria: nao pode ser negativa.",
          "Areas seccionais e A_WP ficam subestimadas; o volume pode ficar menor que o real.",
          "Verifique se houve troca de sinal ou se o valor pertence ao bordo oposto.")

    # --- meia-boca maior que a propria boca do navio -----------------------
    if B:
        limite = B / 2.0 * 1.02
        estouro = np.argwhere(np.isfinite(Y) & (Y > limite))
        if len(estouro):
            colunas = sorted({int(j) for _, j in estouro})
            onde = ", ".join(f"WL{j}" for j in colunas)
            pior = float(np.nanmax(Y[np.isfinite(Y)]))
            A("Y-MAIOR-B", "AVISO", "Meia-boca maior que a metade da boca informada",
              f"{len(estouro)} celula(s), concentradas em {onde}",
              f"A boca informada e {fmt(B)} m, o que limita a meia-boca a {fmt(B/2)} m. "
              f"A tabela chega a {fmt(pior)} m, ou seja, uma boca de {fmt(2*pior)} m.",
              "Uma coluna inteira acima desse limite normalmente NAO e uma linha d'agua: "
              "costuma ser outra grandeza gravada junto da tabela (perimetro, area, linha "
              "de convés). Se ela for integrada como se fosse meia-boca, o volume, o "
              "deslocamento e todos os coeficientes ficam inflados.",
              "Confira a coluna apontada. Se ela nao for uma linha d'agua, reduza a faixa "
              "de colunas de meias-bocas na interpretacao da tabela e reveja as alturas.")

    # --- coerencia geometrica: alargamento nao monotono na vertical --------
    suspeitas = []
    for i in range(tab.n_est):
        yy = Y[i]
        val = np.isfinite(yy)
        if val.sum() < 3:
            continue
        d = np.diff(yy[val])
        if np.any(d < -0.02 * max(np.nanmax(np.abs(yy[val])), 1e-6)):
            suspeitas.append(tab.rotulos[i])
    if suspeitas:
        A("GEO-TUMBLE", "AVISO", "Secao estreitando com o aumento do calado",
          "balizas " + ", ".join(suspeitas[:10]),
          "Nessas balizas a meia-boca diminui ao subir a linha d'agua. Isso e possivel "
          "fisicamente (tumblehome, popa, proa), mas tambem e um sintoma classico de "
          "colunas de WL trocadas de ordem.",
          "Se for erro de ordem, areas seccionais, A_WP e todos os coeficientes "
          "sairao distorcidos.",
          "Confira o plano de linhas no Modulo 2: a forma deve parecer com a do casco real.")

    # --- coerencia com os dados principais ---------------------------------
    if B:
        bmax = 2 * np.nanmax(Y) if np.isfinite(Y).any() else np.nan
        if np.isfinite(bmax) and bmax > 1e-9:
            erro = abs(bmax - B) / B * 100
            if erro > 10:
                A("DIM-B", "AVISO", "Boca da tabela difere da boca informada",
                  "dados principais x tabela de cotas",
                  f"Boca informada B = {fmt(B)} m; boca maxima da tabela = 2*y_max = "
                  f"{fmt(bmax)} m (diferenca de {fmt(erro, 1)} %).",
                  "Sugere unidade errada (por exemplo, tabela em milimetros) ou tabela "
                  "de outra embarcacao. Todos os coeficientes de forma dependem de B.",
                  "Confira a unidade da tabela no Modulo 1 ou corrija a boca informada.")
    if L:
        span = float(np.nanmax(x) - np.nanmin(x))
        if span > 1e-9:
            erro = abs(span - L) / L * 100
            if erro > 10:
                A("DIM-L", "AVISO", "Comprimento da tabela difere do LPP informado",
                  "dados principais x coluna X",
                  f"LPP informado = {fmt(L)} m; extensao das estacoes = {fmt(span)} m "
                  f"(diferenca de {fmt(erro, 1)} %).",
                  "C_B, C_P, C_WP e o LCB usam L. Uma divergencia grande desloca todos eles.",
                  "Verifique a unidade da coluna X e a referencia longitudinal adotada.")

    # --- unidade suspeita --------------------------------------------------
    if np.isfinite(Y).any():
        ymax = float(np.nanmax(Y))
        if ymax > 100:
            A("UNI-SUSP", "AVISO", "Valores muito grandes para metros",
              f"y_max = {fmt(ymax)}",
              "As meias-bocas passam de 100 na unidade declarada.",
              "Se a tabela estiver em milimetros e for lida como metros, o volume sai "
              "10^9 vezes maior e as curvas ficam sem sentido fisico.",
              "Confirme a unidade da tabela de cotas no Modulo 1.")

    # --- espacamento uniforme ---------------------------------------------
    if len(x) > 2 and not espacamento_uniforme(x):
        A("EST-NUNIF", "AVISO", "Espacamento longitudinal nao uniforme",
          "coluna X",
          "As estacoes nao estao igualmente espacadas.",
          "As regras de Simpson exigem passo constante: nos trechos irregulares o "
          "aplicativo usara o Trapezio, com precisao um pouco menor.",
          "Isso e aceitavel e fica registrado na auditoria da integracao.")
    if len(z) > 2 and not espacamento_uniforme(z):
        A("WL-NUNIF", "AVISO", "Espacamento vertical nao uniforme",
          "alturas z",
          "As linhas d'agua nao estao igualmente espacadas.",
          "Mesmo efeito: Simpson so sera aplicado nos trechos de passo constante.",
          "Registrado na auditoria da integracao.")

    # --- base do casco -----------------------------------------------------
    if len(z) and z[0] > 1e-6:
        A("WL-BASE", "AVISO", "Primeira linha d'agua acima da linha de base",
          f"z_min = {fmt(z[0])} m",
          "A tabela nao comeca em z = 0.",
          "O volume abaixo da primeira linha d'agua nao esta descrito pelos dados; "
          "sera necessario assumir uma hipotese para essa faixa, o que afeta "
          "volume, KB e WSA.",
          "Escolha a hipotese no Modulo 3 (manter a menor meia-boca ou assumir zero).")

    return ach


def espacamento_uniforme(v, rtol=1e-6) -> bool:
    if len(v) < 3:
        return True
    d = np.diff(np.asarray(v, float))
    return bool(np.all(np.abs(d - d[0]) <= rtol * max(abs(d[0]), 1e-12) + 1e-9))


# ============================================================================ #
# S4 - INTERPOLACAO (Modulo 3)                                                 #
# ============================================================================ #
#
# Regras adotadas, todas registradas celula a celula:
#   - lacuna INTERNA (ha dado abaixo e acima)  -> interpolacao linear em z
#   - lacuna no TOPO (acima do ultimo dado)    -> escolha do usuario
#   - lacuna na BASE (abaixo do primeiro dado) -> escolha do usuario
#   - baliza inteiramente vazia                -> interpolacao linear em x
# ---------------------------------------------------------------------------

def interpolar_tabela(tab: Tabela, topo="manter", base="zero") -> tuple:
    """
    Preenche as lacunas e devolve (nova_tabela, lista_de_registros).
    Cada registro descreve metodo, pontos usados, posicao e valor obtido.
    """
    t = tab.copia()
    regs = []
    n_est, n_wl = t.n_est, t.n_wl

    # --- 1) dentro de cada baliza, ao longo de z ---------------------------
    for i in range(n_est):
        y = t.Y[i]
        val = np.isfinite(y)
        if val.sum() == 0:
            continue
        idx = np.where(val)[0]
        j0, j1 = idx[0], idx[-1]

        # lacunas internas
        for j in range(j0 + 1, j1):
            if not np.isfinite(y[j]):
                ja = idx[idx < j].max()
                jb = idx[idx > j].min()
                za, zb, zc = t.z[ja], t.z[jb], t.z[j]
                ya, yb = y[ja], y[jb]
                novo = ya + (yb - ya) * (zc - za) / (zb - za)
                t.Y[i, j] = novo
                t.origem[i, j] = (f"interpolacao linear em z entre WL{ja} (z={fmt(za)}, "
                                  f"y={fmt(ya)}) e WL{jb} (z={fmt(zb)}, y={fmt(yb)})")
                regs.append({"Baliza": t.rotulos[i], "X": t.x[i], "WL": j, "z": zc,
                             "Metodo": "Linear em z", "Pontos usados": f"WL{ja} e WL{jb}",
                             "Valor obtido": novo, "Motivo": "lacuna interna"})

        # lacunas no topo
        for j in range(j1 + 1, n_wl):
            if topo == "manter":
                novo, met = y[j1], "extensao do ultimo valor"
            elif topo == "zero":
                novo, met = 0.0, "assumido zero"
            else:  # extrapolar
                if len(idx) >= 2:
                    ja, jb = idx[-2], idx[-1]
                    novo = y[jb] + (y[jb] - y[ja]) * (t.z[j] - t.z[jb]) / (t.z[jb] - t.z[ja])
                    novo = max(novo, 0.0)
                else:
                    novo = y[j1]
                met = "extrapolacao linear"
            t.Y[i, j] = novo
            t.origem[i, j] = f"acima do ultimo dado: {met}"
            regs.append({"Baliza": t.rotulos[i], "X": t.x[i], "WL": j, "z": t.z[j],
                         "Metodo": met, "Pontos usados": f"WL{j1}",
                         "Valor obtido": novo, "Motivo": "acima do ultimo dado (convés/topo)"})

        # lacunas na base
        for j in range(0, j0):
            if base == "zero":
                novo, met = 0.0, "assumido zero (casco nao alcanca esse nivel)"
            else:
                novo, met = y[j0], "extensao do primeiro valor"
            t.Y[i, j] = novo
            t.origem[i, j] = f"abaixo do primeiro dado: {met}"
            regs.append({"Baliza": t.rotulos[i], "X": t.x[i], "WL": j, "z": t.z[j],
                         "Metodo": met, "Pontos usados": f"WL{j0}",
                         "Valor obtido": novo, "Motivo": "abaixo do primeiro dado (fundo)"})

    # --- 2) balizas inteiramente vazias, ao longo de x ---------------------
    vazias = [i for i in range(n_est) if not np.isfinite(t.Y[i]).any()]
    cheias = [i for i in range(n_est) if np.isfinite(t.Y[i]).all()]
    for i in vazias:
        ant = [c for c in cheias if c < i]
        pos = [c for c in cheias if c > i]
        if ant and pos:
            ia, ib = ant[-1], pos[0]
            f = (t.x[i] - t.x[ia]) / (t.x[ib] - t.x[ia])
            t.Y[i] = t.Y[ia] + (t.Y[ib] - t.Y[ia]) * f
            t.origem[i, :] = f"interpolacao linear em x entre balizas {t.rotulos[ia]} e {t.rotulos[ib]}"
            regs.append({"Baliza": t.rotulos[i], "X": t.x[i], "WL": "todas", "z": "-",
                         "Metodo": "Linear em x", "Pontos usados":
                             f"balizas {t.rotulos[ia]} e {t.rotulos[ib]}",
                         "Valor obtido": np.nan, "Motivo": "baliza inteiramente vazia"})
        else:
            t.Y[i] = 0.0
            t.origem[i, :] = "baliza vazia sem vizinhos: assumido zero"
            regs.append({"Baliza": t.rotulos[i], "X": t.x[i], "WL": "todas", "z": "-",
                         "Metodo": "assumido zero", "Pontos usados": "-",
                         "Valor obtido": 0.0, "Motivo": "baliza vazia sem vizinhos validos"})

    return t, regs


def reamostrar_z(tab: Tabela, n_alvo: int) -> tuple:
    """
    Gera uma malha vertical uniforme com n_alvo linhas d'agua entre z_min e z_max
    (interpolacao linear). Util quando o espacamento original impede Simpson.
    """
    z_novo = np.linspace(tab.z[0], tab.z[-1], n_alvo)
    Y = np.zeros((tab.n_est, n_alvo))
    for i in range(tab.n_est):
        Y[i] = np.interp(z_novo, tab.z, tab.Y[i])
    t = nova_tabela(tab.x, z_novo, Y, tab.rotulos, tab.unidade)
    marca = np.isin(np.round(z_novo, 9), np.round(tab.z, 9))
    t.original = np.tile(marca, (tab.n_est, 1))
    t.origem = np.where(t.original, "arquivo",
                        "reamostragem vertical uniforme (linear)").astype(object)
    return t, z_novo


def aplicar_alturas(tab: Tabela, z_novo) -> Tabela:
    """Substitui as alturas das linhas d'agua mantendo as meias-bocas."""
    t = tab.copia()
    t.z = np.asarray(z_novo, float)
    return t


def aplicar_posicoes(tab: Tabela, x_novo) -> Tabela:
    """Substitui as posicoes longitudinais das balizas mantendo as meias-bocas."""
    t = tab.copia()
    t.x = np.asarray(x_novo, float)
    return t


def ordenar_tabela(tab: Tabela) -> Tabela:
    """Reordena estacoes por x crescente e linhas d'agua por z crescente."""
    t = tab.copia()
    ix = np.argsort(t.x, kind="stable")
    jz = np.argsort(t.z, kind="stable")
    t.x = t.x[ix]
    t.z = t.z[jz]
    t.Y = t.Y[np.ix_(ix, jz)]
    t.original = t.original[np.ix_(ix, jz)]
    t.origem = t.origem[np.ix_(ix, jz)]
    t.rotulos = [t.rotulos[i] for i in ix]
    return t


def remover_duplicatas(tab: Tabela) -> tuple:
    """Remove estacoes com x repetido e linhas d'agua com z repetido (mantem a primeira)."""
    t = ordenar_tabela(tab)
    manter_i = [0] + [i for i in range(1, len(t.x)) if abs(t.x[i] - t.x[i - 1]) > 1e-9]
    manter_j = [0] + [j for j in range(1, len(t.z)) if abs(t.z[j] - t.z[j - 1]) > 1e-9]
    removidas = (len(t.x) - len(manter_i), len(t.z) - len(manter_j))
    t.x = t.x[manter_i]
    t.z = t.z[manter_j]
    t.Y = t.Y[np.ix_(manter_i, manter_j)]
    t.original = t.original[np.ix_(manter_i, manter_j)]
    t.origem = t.origem[np.ix_(manter_i, manter_j)]
    t.rotulos = [t.rotulos[i] for i in manter_i]
    return t, removidas


# ---------------------------------------------------------------------------
# S4.1 - REFINAMENTO DA TABELA POR INTERPOLACAO
# ---------------------------------------------------------------------------
#
# Uma tabela de cotas com poucas balizas e poucas linhas d'agua descreve mal um
# casco curvo: entre dois pontos o programa so pode supor uma reta, e areas e
# volumes saem subestimados nas regioes de maior curvatura, tipicamente o bojo.
#
# Refinar acrescenta pontos INTERMEDIARIOS entre os dados originais. Isso nao
# cria informacao nova: apenas troca a suposicao "reta entre dois pontos" por
# uma curva suave que passa exatamente pelos mesmos pontos. Para um casco de
# verdade, que e suave, a curva costuma ser a suposicao mais proxima da realidade.
#
# Duas opcoes de curva:
#   linear    -> mantem a reta entre pontos. Refinar nao muda nada; serve so
#                para deixar a malha uniforme.
#   monotona  -> cubica de Hermite com as inclinacoes de Fritsch-Carlson. Passa
#                pelos pontos originais, e suave, e nunca inventa ondulacoes nem
#                ultrapassa os valores vizinhos, ao contrario de uma spline comum.
#                E a escolha adequada para meias-bocas, que nao devem oscilar.
# ---------------------------------------------------------------------------

def interp_monotona(x, y, xq):
    """
    Interpolacao cubica de Hermite com inclinacoes de Fritsch-Carlson.

    Preserva a monotonicidade dos dados: onde as meias-bocas so crescem, a curva
    so cresce, sem os sobressinais que uma spline cubica comum produziria perto
    do bojo ou do convés.
    """
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    xq = np.atleast_1d(np.asarray(xq, float))
    n = len(x)
    if n < 3:
        return np.interp(xq, x, y)

    h = np.diff(x)
    delta = np.diff(y) / h

    # inclinacao em cada no
    m = np.zeros(n)
    m[0] = delta[0]
    m[-1] = delta[-1]
    for i in range(1, n - 1):
        if delta[i - 1] * delta[i] <= 0:
            m[i] = 0.0                      # extremo local: tangente horizontal
        else:
            w1 = 2 * h[i] + h[i - 1]
            w2 = h[i] + 2 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / delta[i - 1] + w2 / delta[i])

    # limitador de Fritsch-Carlson: impede sobressinal em cada trecho
    for i in range(n - 1):
        if abs(delta[i]) < 1e-15:
            m[i] = m[i + 1] = 0.0
        else:
            a, b = m[i] / delta[i], m[i + 1] / delta[i]
            s = a * a + b * b
            if s > 9.0:
                t = 3.0 / np.sqrt(s)
                m[i] = t * a * delta[i]
                m[i + 1] = t * b * delta[i]

    idx = np.clip(np.searchsorted(x, xq) - 1, 0, n - 2)
    dx = xq - x[idx]
    hh = h[idx]
    t = dx / hh
    t2, t3 = t * t, t * t * t
    h00 = 2 * t3 - 3 * t2 + 1
    h10 = t3 - 2 * t2 + t
    h01 = -2 * t3 + 3 * t2
    h11 = t3 - t2
    return h00 * y[idx] + h10 * hh * m[idx] + h01 * y[idx + 1] + h11 * hh * m[idx + 1]


def _interpolar(x, y, xq, metodo="monotona"):
    bons = np.isfinite(y)
    if bons.sum() < 2:
        return np.zeros_like(np.atleast_1d(xq), dtype=float)
    if metodo == "monotona" and bons.sum() >= 3:
        return interp_monotona(np.asarray(x)[bons], np.asarray(y)[bons], xq)
    return np.interp(xq, np.asarray(x)[bons], np.asarray(y)[bons])


def refinar_tabela(tab: Tabela, fator_x: int = 1, fator_z: int = 1,
                   metodo: str = "monotona") -> tuple:
    """
    Devolve (nova_tabela, resumo) com pontos intermediarios entre os originais.

    fator_x = 2 coloca uma baliza entre cada par de balizas; fator_z = 2 faz o
    mesmo com as linhas d'agua. Os pontos originais permanecem na tabela e
    continuam marcados como vindos do arquivo.
    """
    fator_x = max(int(fator_x), 1)
    fator_z = max(int(fator_z), 1)
    if fator_x == 1 and fator_z == 1:
        return tab.copia(), {"balizas": tab.n_est, "linhas_agua": tab.n_wl, "gerados": 0}

    def malha(v, f):
        if f <= 1:
            return np.asarray(v, float)
        saida = [float(v[0])]
        for a, b in zip(v[:-1], v[1:]):
            saida.extend(np.linspace(a, b, f + 1)[1:])
        return np.array(saida, float)

    x_novo = malha(tab.x, fator_x)
    z_novo = malha(tab.z, fator_z)

    # primeiro ao longo de z, em cada baliza original
    Y1 = np.zeros((tab.n_est, len(z_novo)))
    for i in range(tab.n_est):
        Y1[i] = np.clip(_interpolar(tab.z, tab.Y[i], z_novo, metodo), 0.0, None)
    # depois ao longo de x, em cada linha d'agua da malha nova
    Y2 = np.zeros((len(x_novo), len(z_novo)))
    for j in range(len(z_novo)):
        Y2[:, j] = np.clip(_interpolar(tab.x, Y1[:, j], x_novo, metodo), 0.0, None)

    rot = []
    for xi in x_novo:
        k = int(np.argmin(np.abs(np.asarray(tab.x) - xi)))
        rot.append(tab.rotulos[k] if abs(tab.x[k] - xi) < 1e-9
                   else f"{tab.rotulos[k]}+")

    novo = nova_tabela(x_novo, z_novo, Y2, rot, tab.unidade)
    orig_x = np.isclose(x_novo[:, None], np.asarray(tab.x)[None, :], atol=1e-9).any(axis=1)
    orig_z = np.isclose(z_novo[:, None], np.asarray(tab.z)[None, :], atol=1e-9).any(axis=1)
    marca = orig_x[:, None] & orig_z[None, :]
    novo.original = marca & np.isfinite(Y2)
    nome = {"monotona": "cubica monotona (Fritsch-Carlson)", "linear": "linear"}[metodo]
    novo.origem = np.where(novo.original, "arquivo",
                           f"refinamento por interpolacao {nome}").astype(object)
    resumo = {"balizas": len(x_novo), "linhas_agua": len(z_novo),
              "gerados": int((~novo.original).sum()), "metodo": nome}
    return novo, resumo
