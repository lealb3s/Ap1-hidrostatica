# -*- coding: utf-8 -*-
"""Leitura de arquivos e deteccao automatica do layout da tabela de cotas."""

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
# S2 - LEITURA DE ARQUIVOS E DETECCAO AUTOMATICA DE LAYOUT                     #
# ============================================================================ #
#
# O aplicativo NAO assume um formato unico de tabela de cotas. Ele aceita:
#
#   FORMATO A (matriz classica)  -> WL nas colunas, balizas nas linhas
#        Baliza | X | WL0 | WL1 | WL2 ...
#               |   | z0  | z1  | z2       <- linha opcional com as alturas
#           0   |x0 | y00 | y01 | y02
#
#   FORMATO B (matriz transposta) -> balizas nas colunas, WL nas linhas
#        WL / z | Est.0 | Est.1 | Est.2 ...
#               |  x0   |  x1   |  x2      <- linha opcional com as posicoes
#          0.0  | y00   | y10   | y20
#
#   FORMATO C (tabela longa / tidy) -> tres colunas: x, z, y
#
# A deteccao e automatica, mas TUDO pode ser corrigido pelo usuario na interface
# (orientacao, coluna de X, linha de z, unidade). E assim que a generalizacao
# para um casco desconhecido e garantida sem alterar o codigo-fonte.
# ---------------------------------------------------------------------------


def ler_arquivo_bruto(arquivo) -> dict:
    """
    Le o arquivo enviado SEM interpretar nada (header=None): preserva tudo.
    Retorna {nome_da_aba: DataFrame de celulas cruas}.
    O arquivo original nunca e modificado pelo aplicativo.
    """
    nome = arquivo.name
    ext = nome.lower().rsplit(".", 1)[-1]
    dados = arquivo.getvalue()
    abas = {}

    if ext in ("xlsx", "xlsm", "xltx"):
        xl = pd.ExcelFile(io.BytesIO(dados), engine="openpyxl")
        for aba in xl.sheet_names:
            abas[aba] = xl.parse(aba, header=None, dtype=object)

    elif ext == "xls":
        try:
            xl = pd.ExcelFile(io.BytesIO(dados), engine="xlrd")
            for aba in xl.sheet_names:
                abas[aba] = xl.parse(aba, header=None, dtype=object)
        except Exception as e:
            raise RuntimeError(
                "Arquivo .xls (Excel 97-2003) exige a biblioteca 'xlrd'. "
                f"Detalhe: {e}. Solucao: salve novamente como .xlsx ou .csv."
            )

    elif ext in ("csv", "txt", "tsv"):
        texto = None
        for cod in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
            try:
                texto = dados.decode(cod)
                break
            except UnicodeDecodeError:
                continue
        if texto is None:
            raise RuntimeError("Nao foi possivel decodificar o arquivo de texto.")
        # descobre o separador contando ocorrencias nas primeiras linhas
        amostra = "\n".join(texto.splitlines()[:30])
        candidatos = {";": amostra.count(";"), ",": amostra.count(","),
                      "\t": amostra.count("\t"), "|": amostra.count("|")}
        sep = max(candidatos, key=candidatos.get)
        if candidatos[sep] == 0:
            sep = r"\s+"
        df = pd.read_csv(io.StringIO(texto), sep=sep, header=None,
                         dtype=object, engine="python", skip_blank_lines=False)
        abas["(csv)"] = df
    else:
        raise RuntimeError(f"Extensao nao suportada: .{ext}. Use .xlsx, .xls ou .csv.")

    return abas


def limpar_grade(df: pd.DataFrame) -> pd.DataFrame:
    """Remove linhas/colunas totalmente vazias das bordas, preservando o miolo."""
    g = df.copy()
    g = g.replace({None: np.nan})
    g = g.map(lambda v: np.nan if (isinstance(v, str) and v.strip() == "") else v)
    g = g.dropna(how="all", axis=0).dropna(how="all", axis=1)
    g = g.reset_index(drop=True)
    g.columns = range(g.shape[1])
    return g


def matriz_numerica(g: pd.DataFrame) -> np.ndarray:
    return np.array([[para_float(v) for v in linha] for linha in g.values], dtype=float)


# ---------------------------------------------------------------------------
# S2.1 - Deteccao do layout
# ---------------------------------------------------------------------------

@dataclass
class Deteccao:
    ok: bool = False
    orientacao: str = "wl_colunas"   # wl_colunas | wl_linhas | longa
    lin_ini: int = 0                 # primeira linha de dados
    lin_fim: int = 0                 # ultima linha de dados (inclusive)
    col_y_ini: int = 0               # primeira coluna de meias-bocas
    col_y_fim: int = 0               # ultima coluna de meias-bocas
    col_x: int | None = None         # coluna com as posicoes X
    col_id: int | None = None        # coluna com o rotulo da baliza
    lin_z: int | None = None         # linha que contem as alturas z
    lin_rotulo: int | None = None    # linha com rotulos WL0, WL1...
    z_valores: list = field(default_factory=list)
    confianca: int = 0
    notas: list = field(default_factory=list)


def _linhas_de_dados(num: np.ndarray, min_num=3):
    """Maior bloco consecutivo de linhas com pelo menos `min_num` celulas numericas."""
    contagem = np.isfinite(num).sum(axis=1)
    melhor = (0, -1, 0)
    i = 0
    while i < len(contagem):
        if contagem[i] >= min_num:
            j = i
            while j + 1 < len(contagem) and contagem[j + 1] >= min_num:
                j += 1
            if (j - i) > (melhor[1] - melhor[0]):
                melhor = (i, j, j - i)
            i = j + 1
        else:
            i += 1
    return melhor[0], melhor[1]


def _acha_linha_rotulos_wl(g: pd.DataFrame):
    """
    Procura uma linha com varios rotulos do tipo 'WL 0', 'LA 1', 'Waterline 2'.
    Retorna (indice_da_linha, colunas_com_rotulo).
    """
    for r in range(g.shape[0]):
        rotulos = [normtxt(v) for v in g.iloc[r].values]
        cols = [c for c, t in enumerate(rotulos)
                if t and re.match(r"^(wl|w\.?l\.?|la|l\.?a\.?|lwl|dwl|linha d'?agua|"
                                  r"linha dagua|waterline|water line)\s*[-_ ]?[\d.,]*$", t)]
        if len(cols) >= 3:
            return r, cols
    return None, []


def _linha_de_alturas(g: pd.DataFrame, num: np.ndarray, ate_linha: int):
    """
    Procura a linha que contem as ALTURAS z das linhas d'agua.

    Assinatura que a distingue de uma linha de dados: a parte da direita e uma
    sequencia numerica CRESCENTE (as alturas) e a parte da esquerda esta VAZIA
    ou contem apenas texto (os cabecalhos 'Baliza' e 'X' nao tem numero ali).
    Uma linha de dados, ao contrario, sempre traz um numero na coluna X.

    Retorna (indice_da_linha, colunas_das_alturas) ou (None, []).
    """
    achado = (None, [])
    limite = min(max(ate_linha + 1, 1), g.shape[0])
    for r in range(limite):
        # so aceita celulas que sejam numero de verdade. Um cabecalho como
        # "L.A 00 ... L.A 11" tambem produz numeros, mas e uma NUMERACAO das
        # linhas d'agua, nao a altura de cada uma.
        fin = np.array([numero_puro(v) for v in g.iloc[r].values])
        if fin.sum() < 3:
            continue
        cols = np.where(fin)[0]
        # exige um bloco final consecutivo de numeros
        k = len(cols) - 1
        while k > 0 and cols[k] - cols[k - 1] == 1:
            k -= 1
        bloco = list(cols[k:])
        if len(bloco) < 3:
            continue
        # a esquerda do bloco nao pode haver numero algum
        if np.isfinite(num[r, :bloco[0]]).any():
            continue
        vals = [num[r, c] for c in bloco]
        if not all(vals[i] < vals[i + 1] - 1e-12 for i in range(len(vals) - 1)):
            continue
        achado = (r, bloco)
    return achado


def _z_dos_rotulos(g: pd.DataFrame, linha: int, cols):
    """
    Extrai as alturas z a partir dos rotulos das colunas, como em 'WL 1,50' ou '2.5 m'.

    Devolve [] quando os rotulos sao apenas NUMERACAO, do tipo 'L.A 00' ate 'L.A 11'
    ou 'WL 0' ate 'WL 9'. Nesse caso o arquivo numera as linhas d'agua mas nao diz a
    que altura cada uma esta, e usar a numeracao como altura seria inventar geometria:
    o casco ficaria com o pontal errado e a faixa de calados toda comprimida.
    """
    vals = [para_float(g.iat[linha, c]) for c in cols]
    if not all(np.isfinite(v) for v in vals):
        return []
    if not (all(vals[k] < vals[k + 1] + 1e-12 for k in range(len(vals) - 1))
            and vals[-1] > vals[0]):
        return []
    if sao_indices(vals):
        return []
    return vals


def _score_geometrico(Y: np.ndarray) -> float:
    """
    Fracao das linhas em que a meia-boca NAO diminui ao subir.
    Serve para decidir a orientacao quando o arquivo nao tem cabecalho de texto:
    na leitura correta o casco alarga (ou se mantem) com o aumento de z; na leitura
    transposta por engano essa regularidade se perde.
    """
    bons = total = 0
    for linha in Y:
        v = linha[np.isfinite(linha)]
        if len(v) < 2:
            continue
        total += 1
        tol = 0.02 * max(float(np.max(np.abs(v))), 1e-9)
        if np.all(np.diff(v) >= -tol):
            bons += 1
    return bons / total if total else 0.0


def _maior_run(cols):
    """Maior sequencia de colunas consecutivas dentro de uma lista ordenada."""
    seq, melhor = [], []
    for c in cols:
        seq = seq + [c] if (seq and c == seq[-1] + 1) else [c]
        if len(seq) > len(melhor):
            melhor = list(seq)
    return melhor


def detectar_layout(g: pd.DataFrame) -> Deteccao:
    """
    Detecta o layout de UMA orientacao (linhas d'agua nas colunas).
    Para o formato transposto, chame com a grade transposta (ver `detectar_melhor`).

    Ordem da deteccao:
      1. linha de rotulos WL (texto)
      2. bloco bruto de linhas com dados numericos
      3. linha das alturas z  ->  define tambem as colunas de meias-bocas
      4. colunas X e de rotulo da baliza, a esquerda das meias-bocas
      5. delimitacao final das linhas de dados
    """
    d = Deteccao()
    if g.shape[0] < 2 or g.shape[1] < 2:
        d.notas.append("Grade pequena demais para conter uma tabela de cotas.")
        return d

    num = matriz_numerica(g)
    nlin, ncol = g.shape

    # --- 1) rotulos de linha d'agua ---------------------------------------
    lin_rot, cols_rot = _acha_linha_rotulos_wl(g)
    if lin_rot is not None:
        d.lin_rotulo = lin_rot
        d.confianca += 25
        d.notas.append(f"Rotulos de linha d'agua reconhecidos na linha {lin_rot + 1} "
                       "da planilha.")

    # --- 2) bloco bruto de dados ------------------------------------------
    inicio = (lin_rot + 1) if lin_rot is not None else 0
    r0, r1 = _linhas_de_dados(num[inicio:], min_num=3)
    if r1 <= r0:
        r0, r1 = _linhas_de_dados(num[inicio:], min_num=2)
    r0, r1 = r0 + inicio, r1 + inicio
    if r1 <= r0:
        d.notas.append("Nao foi encontrado um bloco de linhas com dados numericos.")
        return d

    # --- 3) linha das alturas z -------------------------------------------
    lin_z, cols_z = _linha_de_alturas(g, num, r0)
    if lin_z is not None:
        d.lin_z = lin_z
        d.confianca += 35
        d.notas.append(f"Alturas das linhas d'agua (z) lidas na linha {lin_z + 1} "
                       "da planilha.")
        cols_y = cols_z
        if lin_z >= r0:
            r0 = lin_z + 1
    elif cols_rot:
        cols_y = [c for c in cols_rot]
    else:
        frac = np.isfinite(num[r0:r1 + 1, :]).mean(axis=0)
        cols_y = _maior_run([c for c in range(ncol) if frac[c] >= 0.5])

    if len(cols_y) < 2:
        d.notas.append("Nao foi possivel delimitar as colunas de meias-bocas.")
        return d

    # --- 4) colunas X e rotulo da baliza ----------------------------------
    col_x, col_id = None, None
    esquerda = [c for c in range(min(cols_y))]

    # 4a) pelo cabecalho, examinando as linhas de baixo para cima (a mais proxima
    #     dos dados costuma ser a linha de rotulos, e nao o titulo da planilha)
    for r in range(max(r0, 1) - 1, -1, -1):
        for c in esquerda:
            cab = normtxt(g.iat[r, c])
            if not cab:
                continue
            if col_x is None and tem_kw(cab, KW_X) and not tem_kw(cab, KW_ESTACAO):
                col_x = c
            if col_id is None and tem_kw(cab, KW_ESTACAO):
                col_id = c
        if col_x is not None or col_id is not None:
            break
    if col_x is not None:
        d.confianca += 15

    if col_x is None and esquerda:                       # 4b) pelo comportamento
        cands = []
        for c in esquerda:
            v = num[r0:r1 + 1, c]
            if np.isfinite(v).mean() < 0.9:
                continue
            vv = v[np.isfinite(v)]
            if len(vv) < 3:
                continue
            monot = bool(np.all(np.diff(vv) > 0) or np.all(np.diff(vv) < 0))
            indice = bool(np.allclose(vv, np.arange(vv[0], vv[0] + len(vv)), atol=1e-9))
            cands.append((c, monot, indice))
        for c, monot, indice in cands:
            if monot and not indice:
                col_x = c
                d.notas.append(f"Coluna {c + 1} adotada como X "
                               "(valores monotonos e nao sequenciais).")
                d.confianca += 10
                break
        if col_x is None and cands:
            col_x = cands[-1][0]
            d.notas.append(f"Coluna {col_x + 1} adotada como X por eliminacao.")
        for c, monot, indice in cands:
            if indice and c != col_x and col_id is None:
                col_id = c

    d.col_x, d.col_id = col_x, col_id
    d.col_y_ini, d.col_y_fim = min(cols_y), max(cols_y)
    if col_x is not None and d.col_y_ini <= col_x <= d.col_y_fim:
        d.col_y_ini = col_x + 1

    # --- 5) delimitacao final das linhas de dados -------------------------
    faixa = list(range(d.col_y_ini, d.col_y_fim + 1))
    validas = [r for r in range(r0, min(r1 + 1, nlin))
               if np.isfinite(num[r, faixa]).sum() >= max(1, int(0.4 * len(faixa)))]
    if validas:
        r0, r1 = validas[0], validas[-1]
    d.lin_ini, d.lin_fim = r0, r1

    # --- 6) valores de z ---------------------------------------------------
    z = []
    if d.lin_z is not None:
        z = [num[d.lin_z, c] for c in faixa]
    elif d.lin_rotulo is not None:
        z = _z_dos_rotulos(g, d.lin_rotulo, faixa)
    if z and all(np.isfinite(z)):
        d.z_valores = [float(v) for v in z]
        if d.lin_z is None:
            d.confianca += 15
            d.notas.append("Alturas z extraidas dos proprios rotulos das colunas.")
    else:
        d.z_valores = []
        if d.lin_rotulo is not None:
            brutos = [para_float(g.iat[d.lin_rotulo, c]) for c in faixa]
            if all(np.isfinite(brutos)) and sao_indices(brutos):
                d.notas.append(
                    "Os rotulos das linhas d'agua sao apenas NUMERACAO "
                    f"({fmt(brutos[0], 0)} a {fmt(brutos[-1], 0)}), e nao alturas. "
                    "O arquivo numera as linhas d'agua mas nao informa a altura de cada "
                    "uma nesse cabecalho: e preciso dizer qual e o espacamento vertical.")
        d.notas.append("Alturas z das linhas d'agua NAO foram encontradas no arquivo. "
                       "Sera necessario informa-las (espacamento uniforme ou lista).")

    # --- 7) pontuacao semantica: os rotulos concordam com esta orientacao? ------
    #
    # Aqui so vale a LINHA DE ROTULOS, imediatamente acima dos dados. Ler todo o
    # cabecalho da planilha ja causou erro: um arquivo que trazia
    # "Espacamento Secoes L/20" no topo era classificado como transposto por causa
    # da palavra "Secoes", que nada tinha a ver com os rotulos das colunas.
    if d.lin_rotulo is not None:
        linhas_rotulo = [d.lin_rotulo]
    elif d.lin_ini > 0:
        linhas_rotulo = [d.lin_ini - 1]
    else:
        linhas_rotulo = []
    cab_y = " ".join(normtxt(g.iat[r, c]) for r in linhas_rotulo for c in faixa)

    # rotulos de linha d'agua reconhecidos exatamente sobre as colunas de dados
    # sao a evidencia mais forte de que a orientacao esta correta
    if cols_rot and len(set(cols_rot) & set(faixa)) >= max(3, int(0.6 * len(faixa))):
        d.confianca += 30

    if tem_kw(cab_y, KW_ESTACAO):
        d.confianca -= 30
        d.notas.append("Os cabecalhos das colunas de dados parecem nomes de BALIZAS, "
                       "e nao de linhas d'agua: a tabela provavelmente esta transposta.")
    elif tem_kw(cab_y, KW_WL):
        d.confianca += 30

    if esquerda:
        rot_lin = " ".join(normtxt(g.iat[r, esquerda[0]])
                           for r in range(d.lin_ini, d.lin_fim + 1))
        if tem_kw(rot_lin, KW_ESTACAO):
            d.confianca += 30
        elif tem_kw(rot_lin, KW_WL):
            d.confianca -= 30
            d.notas.append("Os rotulos das linhas parecem nomes de LINHAS D'AGUA: "
                           "a tabela provavelmente esta transposta.")

    # --- 8) pontuacao geometrica: o casco alarga com o calado? -----------------
    Yprev = num[np.ix_(range(d.lin_ini, d.lin_fim + 1), faixa)]
    sc = _score_geometrico(Yprev)
    d.confianca += int(round(30 * sc))
    if sc < 0.4:
        d.notas.append(f"Apenas {sc*100:.0f} % das linhas alargam com o aumento de z. "
                       "Confira a orientacao da tabela e a ordem das linhas d'agua.")

    if len(faixa) >= 2 and (d.lin_fim - d.lin_ini) >= 1:
        d.ok = True
        d.confianca += 20
    return d


def detectar_formato_longo(g: pd.DataFrame):
    """
    Formato C: tres colunas (x, z, y). Retorna (x, z, Y) canonico ou None.
    """
    if g.shape[1] < 3 or g.shape[0] < 6:
        return None
    for r in range(0, min(6, g.shape[0])):
        rot = [normtxt(v) for v in g.iloc[r].values]
        ix = iz = iy = None
        for c, t in enumerate(rot):
            if ix is None and (t == "x" or tem_kw(t, KW_X) or tem_kw(t, KW_ESTACAO)):
                ix = c
            elif iz is None and (t == "z" or tem_kw(t, KW_WL)):
                iz = c
            elif iy is None and (t == "y" or tem_kw(t, KW_Y)):
                iy = c
        if ix is not None and iz is not None and iy is not None:
            dados = g.iloc[r + 1:, [ix, iz, iy]].map(para_float).dropna()
            if len(dados) < 6:
                continue
            dados.columns = ["x", "z", "y"]
            piv = dados.pivot_table(index="x", columns="z", values="y", aggfunc="mean")
            piv = piv.sort_index().sort_index(axis=1)
            return (np.array(piv.index, float),
                    np.array(piv.columns, float),
                    piv.to_numpy(float))
    return None


def detectar_melhor(g: pd.DataFrame):
    """
    Testa as duas orientacoes e devolve a de maior confianca.
    Retorna (deteccao, grade_usada, transposta_bool).
    """
    d1 = detectar_layout(g)
    gt = limpar_grade(g.T.reset_index(drop=True))
    gt.columns = range(gt.shape[1])
    d2 = detectar_layout(gt)

    c1 = d1.confianca + (40 if d1.ok else 0)
    c2 = d2.confianca + (40 if d2.ok else 0)
    if c2 > c1:
        d2.orientacao = "wl_linhas"
        d2.notas.insert(0, "A tabela parece TRANSPOSTA (balizas nas colunas, "
                           "linhas d'agua nas linhas). O aplicativo transpos os dados.")
        return d2, gt, True
    d1.orientacao = "wl_colunas"
    return d1, g, False


def montar_canonico(g: pd.DataFrame, d: Deteccao, z_manual=None, x_manual=None):
    """
    Constroi o modelo canonico a partir da grade e da deteccao:
        x  -> vetor (n_estacoes,)   posicoes longitudinais
        z  -> vetor (n_wl,)         alturas das linhas d'agua
        Y  -> matriz (n_estacoes, n_wl) de meias-bocas
        rotulos -> nomes das balizas como estavam no arquivo
    """
    num = matriz_numerica(g)
    linhas = list(range(d.lin_ini, d.lin_fim + 1))
    cols_y = list(range(d.col_y_ini, d.col_y_fim + 1))

    Y = num[np.ix_(linhas, cols_y)].astype(float)

    if x_manual is not None and len(x_manual) == len(linhas):
        x = np.asarray(x_manual, float)
    elif d.col_x is not None:
        x = num[linhas, d.col_x].astype(float)
    else:
        x = np.arange(len(linhas), dtype=float)

    if z_manual is not None and len(z_manual) == len(cols_y):
        z = np.asarray(z_manual, float)
    elif d.z_valores and len(d.z_valores) == len(cols_y):
        z = np.asarray(d.z_valores, float)
    else:
        z = np.arange(len(cols_y), dtype=float)

    if d.col_id is not None:
        rot = [str(g.iat[r, d.col_id]) for r in linhas]
    else:
        rot = [str(i) for i in range(len(linhas))]

    return x, z, Y, rot


# ---------------------------------------------------------------------------
# S2.2 - Pistas escritas no cabecalho da planilha
# ---------------------------------------------------------------------------
#
# Muitas tabelas de cotas trazem, antes dos dados, linhas como:
#
#     Comprimento total ............ 216      m.
#     Boca = B ..................... 32,25    m.
#     Calado Tm .................... 9,1      m.
#     Espacamento Secoes L/20 ...... 10,8     m.
#     Espacamento linha de agua T/10 0,91     m.
#
# Esses valores respondem justamente o que o cabecalho das colunas nao diz: a
# altura de cada linha d'agua. Vale a pena procura-los antes de pedir ao usuario.
# ---------------------------------------------------------------------------

PISTAS = {
    "espacamento_wl": [["espacamento", "linha"], ["espacamento", "agua"],
                       ["espacamento", "la"], ["espacamento", "wl"],
                       ["intervalo", "linha"]],
    "espacamento_estacoes": [["espacamento", "secao"], ["espacamento", "secoes"],
                             ["espacamento", "baliza"], ["espacamento", "estacao"],
                             ["intervalo", "baliza"]],
    "comprimento": [["comprimento", "total"], ["comprimento"], ["loa"], ["lpp"], ["lbp"]],
    "boca": [["boca"], ["breadth"], ["beam"]],
    "pontal": [["pontal"], ["depth"]],
    "calado": [["calado"], ["draft"], ["draught"]],
    "deslocamento": [["deslocamento"], ["displacement"]],
}


def pistas_cabecalho(g: pd.DataFrame) -> dict:
    """
    Varre a planilha atras das grandezas escritas em texto no cabecalho.

    Para cada celula de texto que contenha os termos de uma pista, procura o
    primeiro numero puro a direita (mesma linha) e, se nao houver, abaixo (mesma
    coluna). Assim funciona tanto em planilhas em pe quanto deitadas.

    Retorna {chave: (valor, "texto do rotulo encontrado")}.
    """
    achados = {}
    nlin, ncol = g.shape
    for r in range(nlin):
        for c in range(ncol):
            rotulo = normtxt(g.iat[r, c])
            if not rotulo or len(rotulo) < 3:
                continue
            for chave, conjuntos in PISTAS.items():
                if chave in achados:
                    continue
                if not any(all(t in rotulo for t in termos) for termos in conjuntos):
                    continue
                valor = None
                for cc in range(c + 1, ncol):                 # a direita
                    if numero_puro(g.iat[r, cc]):
                        valor = para_float(g.iat[r, cc])
                        break
                if valor is None:
                    for rr in range(r + 1, min(r + 4, nlin)):  # ou logo abaixo
                        if numero_puro(g.iat[rr, c]):
                            valor = para_float(g.iat[rr, c])
                            break
                if valor is not None and np.isfinite(valor):
                    achados[chave] = (float(valor), str(g.iat[r, c]).strip()[:60])
    return achados


def alturas_sugeridas(g: pd.DataFrame, n_wl: int, calado=None):
    """
    Monta uma proposta de alturas para as linhas d'agua a partir do cabecalho.
    Ordem de preferencia:
      1. espacamento das linhas d'agua declarado no proprio arquivo
      2. calado declarado dividido pelo numero de intervalos
    Retorna (lista_de_alturas, explicacao) ou (None, "").
    """
    p = pistas_cabecalho(g)
    if "espacamento_wl" in p:
        dz, onde = p["espacamento_wl"]
        if dz > 0:
            return ([k * dz for k in range(n_wl)],
                    f"espacamento de {fmt(dz)} m lido no cabecalho da planilha "
                    f"(\"{onde}\")")
    T = calado if calado else (p["calado"][0] if "calado" in p else None)
    if T and n_wl > 1:
        dz = float(T) / (n_wl - 1)
        return ([k * dz for k in range(n_wl)],
                f"calado de {fmt(T)} m dividido em {n_wl - 1} intervalos iguais")
    return None, ""
