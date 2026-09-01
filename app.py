# -*- coding: utf-8 -*-
"""
================================================================================
 APLICATIVO DE CALCULO HIDROSTATICO  -  AP1.1 Projeto Integrador
 Arquitetura Naval  -  Aplicativo generalizavel, auditavel e validado
================================================================================

 FILOSOFIA:  DETECTAR -> EXPLICAR -> AVISAR -> MOSTRAR CONSEQUENCIAS -> O USUARIO DECIDE

 O programa nunca corrige silenciosamente. Todo problema encontrado e mostrado,
 explicado, tem suas consequencias apresentadas, e a decisao final e do usuario.
 Toda decisao fica registrada no historico e no relatorio.

 NAVEGACAO DO CODIGO (procure pelos marcadores):
   S0  ...... Imports, configuracao e constantes
   S1  ...... Utilitarios: numeros, unidades, historico, formatacao
   S2  ...... Leitura de arquivos e DETECCAO AUTOMATICA DE LAYOUT
   S3  ...... Modelo canonico da tabela de cotas + diagnostico geometrico
   S4  ...... Interpolacao (preenchimento auditavel de lacunas)
   S5  ...... Integracao numerica (Trapezio, Simpson 1/3, Simpson 3/8) + auditoria
   S6  ...... Nucleo hidrostatico (areas, volumes, centros, metacentro, coefs, WSA)
   S7  ...... Hydrostatic Table e Hydrostatic Curves
   S8  ...... Graficos: plano de linhas, secoes, linhas d'agua, 3D
   S9  ...... Relatorio (HTML autocontido) e exportacoes
   S10 ...... Interface Streamlit (Modulos 1 a 7)

 Execucao:  streamlit run app.py
================================================================================
"""

# ============================================================================ #
# S0 - IMPORTS, CONFIGURACAO E CONSTANTES                                      #
# ============================================================================ #

import io
import re
import base64
import textwrap
import datetime as _dt
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401  (registra a projecao 3d)

APP_NOME = "Aplicativo de Calculo Hidrostatico"
APP_VERSAO = "1.0"
EPS = 1e-12

# Fatores de conversao para o SI (metro). Os calculos internos sao SEMPRE em metros.
UNIDADES = {
    "m (metro)": 1.0,
    "cm (centimetro)": 0.01,
    "mm (milimetro)": 0.001,
    "ft (pe)": 0.3048,
    "in (polegada)": 0.0254,
}

# Palavras-chave reconhecidas em portugues e ingles (Modulo 2 - interpretacao bilingue)
KW_ESTACAO = ["baliza", "balizas", "bal", "estacao", "estacoes", "est", "station",
              "stations", "st", "sec", "secao", "secoes", "section", "sections",
              "frame", "caverna", "ord", "ordenada"]
KW_X = ["x", "posicao", "posicoes", "long", "longitudinal", "abscissa", "lpp", "dist"]
KW_WL = ["wl", "w.l", "wl.", "linha", "linhas", "agua", "dagua", "d'agua", "la",
         "waterline", "waterlines", "wline", "lwl", "dwl", "z", "altura", "height"]
KW_Y = ["y", "meia", "meias", "boca", "bocas", "semiboca", "semi", "half", "halfbreadth",
        "breadth", "offset", "offsets", "cota", "cotas", "b/2"]

NULOS = {"", "-", "--", "---", "n/a", "na", "nan", "none", "null", "#n/d", "#n/a",
         "#valor!", "s/d", "x", "?", ".", "vazio", "empty"}

# Propriedades hidrostaticas: chave -> (rotulo, unidade, casas decimais)
PROPRIEDADES = {
    "T":      ("T (calado)",                 "m",    3),
    "VOL_L":  ("Vol L (long.)",              "m3",   3),
    "VOL_V":  ("Vol V (vert.)",              "m3",   3),
    "VOL":    ("Vol (adotado)",              "m3",   3),
    "E_VOL":  ("E_vol",                      "%",    3),
    "DESL":   ("Delta (deslocamento)",       "t",    3),
    "LCB":    ("LCB",                        "m",    3),
    "LCF":    ("LCF",                        "m",    3),
    "KB":     ("KB = VCB",                   "m",    4),
    "BMT":    ("BM_t",                       "m",    4),
    "KMT":    ("KM_t",                       "m",    4),
    "BML":    ("BM_l",                       "m",    4),
    "KML":    ("KM_l",                       "m",    4),
    "AWP":    ("A_WP",                       "m2",   3),
    "IT":     ("I_t",                        "m4",   3),
    "IL":     ("I_l",                        "m4",   3),
    "TPC":    ("TPC",                        "t/cm", 4),
    "WSA":    ("WSA (sup. molhada)",         "m2",   3),
    "AM":     ("A_M (secao mestra)",         "m2",   3),
    "BWL":    ("B_WL (boca na linha)",       "m",    3),
    "LWL":    ("L_WL",                       "m",    3),
    "CB":     ("C_B",                        "-",    4),
    "CWP":    ("C_WP",                       "-",    4),
    "CM":     ("C_M",                        "-",    4),
    "CP":     ("C_P",                        "-",    4),
}

CURVAS_OBRIGATORIAS = ["VOL", "DESL", "LCB", "LCF", "KB", "BMT", "KMT",
                       "BML", "KML", "AWP", "TPC", "CB", "CWP", "CM", "CP"]


# ============================================================================ #
# S1 - UTILITARIOS                                                             #
# ============================================================================ #

def agora() -> str:
    return _dt.datetime.now().strftime("%d/%m/%Y %H:%M:%S")


def para_float(v: Any) -> float:
    """
    Converte qualquer celula para float, aceitando:
      - virgula decimal brasileira  (1,25  ->  1.25)
      - separador de milhar         (1.234,56 -> 1234.56  /  1,234.56 -> 1234.56)
      - texto com unidade colada    ("1,50 m" -> 1.50 ; "WL 2.5" -> 2.5)
      - marcadores de vazio         ("-", "n/a", "" -> NaN)
    Retorna NaN quando nao ha numero reconhecivel.
    """
    if v is None:
        return np.nan
    if isinstance(v, bool):
        return np.nan
    if isinstance(v, (int, float, np.integer, np.floating)):
        f = float(v)
        return f if np.isfinite(f) else np.nan

    s = str(v).strip().replace("\u00a0", " ")
    if s.lower() in NULOS:
        return np.nan

    # remove tudo que nao compoe um numero (mantem sinal, digitos, . , e/E)
    s = re.sub(r"[^\d,.\-+eE]", "", s)
    s = s.strip()
    if s in ("", "-", "+", ".", ","):
        return np.nan

    tem_v, tem_p = ("," in s), ("." in s)
    if tem_v and tem_p:
        # o separador que aparece por ULTIMO e o decimal
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif tem_v:
        # virgula sozinha: decimal (padrao brasileiro). "1,234" -> 1.234
        s = s.replace(",", ".")

    # multiplos pontos sobrando => eram milhares
    if s.count(".") > 1:
        cabeca, _, cauda = s.rpartition(".")
        s = cabeca.replace(".", "") + "." + cauda

    try:
        f = float(s)
        return f if np.isfinite(f) else np.nan
    except ValueError:
        return np.nan


def normtxt(v: Any) -> str:
    """Normaliza texto para comparacao: minusculo, sem acento, sem pontuacao extra."""
    if v is None:
        return ""
    s = str(v).strip().lower()
    if s in ("nan", "none"):
        return ""
    tabela = str.maketrans("aaaaaeeeeiiiiooooouuuuc", "aaaaaeeeeiiiiooooouuuuc")
    s = (s.replace("á", "a").replace("à", "a").replace("ã", "a").replace("â", "a")
           .replace("é", "e").replace("ê", "e").replace("í", "i")
           .replace("ó", "o").replace("ô", "o").replace("õ", "o")
           .replace("ú", "u").replace("ç", "c").translate(tabela))
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def tem_kw(texto: str, palavras) -> bool:
    """
    Verifica se um cabecalho contem alguma palavra-chave.
    Palavras curtas (ate 2 letras, como "x" e "st") so valem como palavra inteira;
    caso contrario um titulo como "navio exemplo" seria confundido com a coluna X.
    """
    t = normtxt(texto)
    if not t:
        return False
    fichas = set(re.split(r"[^a-z0-9']+", t))
    for p in palavras:
        if p in fichas:
            return True
        if len(p) >= 3 and p in t:
            return True
    return False


def fmt(v, casas=3) -> str:
    """Formata numero para exibicao (com fallback para valores invalidos)."""
    if v is None:
        return "-"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if not np.isfinite(f):
        return "-"
    return f"{f:,.{casas}f}".replace(",", "@").replace(".", ",").replace("@", ".")


def rerodar():
    """st.rerun com compatibilidade entre versoes do Streamlit."""
    try:
        st.rerun()
    except AttributeError:  # pragma: no cover
        st.experimental_rerun()


# ---------------------------------------------------------------------------
# S1.1 - HISTORICO / AUDITORIA
# Todo evento relevante passa por aqui. Nada e alterado sem registro.
# ---------------------------------------------------------------------------

NIVEIS = {"INFO": "info", "AVISO": "aviso", "ERRO": "erro",
          "DECISAO": "decisao", "ALTERACAO": "alteracao"}


def registrar(etapa: str, acao: str, *, nivel: str = "INFO", antes=None, novo=None,
              autor: str = "programa", consequencia: str = ""):
    """Adiciona um evento ao historico (S2 do documento de especificacao)."""
    if "hist" not in st.session_state:
        st.session_state.hist = []
    st.session_state.hist.append({
        "n": len(st.session_state.hist) + 1,
        "data_hora": agora(),
        "etapa": etapa,
        "nivel": nivel,
        "acao": acao,
        "valor_anterior": "" if antes is None else str(antes),
        "valor_novo": "" if novo is None else str(novo),
        "autor": autor,
        "consequencia": consequencia,
    })


def historico_df() -> pd.DataFrame:
    h = st.session_state.get("hist", [])
    if not h:
        return pd.DataFrame(columns=["n", "data_hora", "etapa", "nivel", "acao",
                                     "valor_anterior", "valor_novo", "autor", "consequencia"])
    return pd.DataFrame(h)


@dataclass
class Achado:
    """Um problema/ambiguidade detectado: o que e, onde esta, o que causa."""
    codigo: str
    nivel: str            # "ERRO" (impede calculo) | "AVISO" (pode continuar)
    titulo: str
    onde: str
    explicacao: str
    consequencia: str
    sugestao: str = ""

    def como_dict(self):
        return {"Codigo": self.codigo, "Nivel": self.nivel, "Problema": self.titulo,
                "Onde": self.onde, "O que foi encontrado": self.explicacao,
                "Possiveis consequencias": self.consequencia, "Sugestao": self.sugestao}


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
        fin = np.isfinite(num[r])
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
    """Extrai z de rotulos como 'WL 1,50' ou '2.5 m'. Retorna [] se nao houver numero util."""
    vals = [para_float(g.iat[linha, c]) for c in cols]
    if all(np.isfinite(v) for v in vals):
        if all(vals[k] < vals[k + 1] + 1e-12 for k in range(len(vals) - 1)) and vals[-1] > vals[0]:
            return vals
    return []


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
        d.notas.append("Alturas z das linhas d'agua NAO foram encontradas no arquivo. "
                       "Sera necessario informa-las (espacamento uniforme ou lista).")

    # --- 7) pontuacao semantica: os rotulos concordam com esta orientacao? ------
    cab_y = " ".join(normtxt(g.iat[r, c]) for r in range(0, max(d.lin_ini, 0))
                     for c in faixa)
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
    d.confianca += int(round(25 * sc))
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
    B = principais.get("B")
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
    L = principais.get("LPP")
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


# ============================================================================ #
# S5 - INTEGRACAO NUMERICA (Modulo 3, item 9 do enunciado)                     #
# ============================================================================ #
#
# Implementacao direta, sem biblioteca pronta:
#   Trapezio      :  I = h/2 * (f0 + f1)
#   Simpson 1/3   :  I = h/3 * (f0 + 4f1 + 2f2 + 4f3 + ... + fn)      n par
#   Simpson 3/8   :  I = 3h/8 * (f0 + 3f1 + 3f2 + f3)                 n multiplo de 3
#
# O planejador escolhe a regra trecho a trecho e devolve a AUDITORIA no formato
# pedido pelo enunciado:  "Estacoes 0-2: Simpson 1/3 | 2-5: Simpson 3/8 | 5-6: Trapezio".
# ---------------------------------------------------------------------------

def trechos_uniformes(v, rtol=1e-6):
    """Divide o eixo em trechos maximos de passo constante. Retorna [(i_ini, i_fim)]."""
    v = np.asarray(v, float)
    n = len(v)
    if n < 2:
        return []
    d = np.diff(v)
    trechos, ini = [], 0
    for k in range(1, len(d)):
        if abs(d[k] - d[ini]) > rtol * max(abs(d[ini]), 1e-12) + 1e-9:
            trechos.append((ini, k))
            ini = k
        # continua
    trechos.append((ini, len(d)))
    return [(a, b) for a, b in trechos if b > a]


def _plano_trecho(i0, n_int, metodo="auto"):
    """Sequencia de regras para n_int intervalos uniformes iniciando no no i0."""
    p = []
    if n_int <= 0:
        return p
    if metodo == "trapezio":
        return [(i0, i0 + n_int, "Trapezio")]
    if metodo == "simpson13":
        if n_int % 2 == 0:
            return [(i0, i0 + n_int, "Simpson 1/3")]
        if n_int > 1:
            return [(i0, i0 + n_int - 1, "Simpson 1/3"),
                    (i0 + n_int - 1, i0 + n_int, "Trapezio (sobra impar)")]
        return [(i0, i0 + 1, "Trapezio (sobra impar)")]
    if metodo == "simpson38":
        k = (n_int // 3) * 3
        if k:
            p.append((i0, i0 + k, "Simpson 3/8"))
        r = n_int - k
        if r == 2:
            p.append((i0 + k, i0 + n_int, "Simpson 1/3"))
        elif r == 1:
            p.append((i0 + k, i0 + n_int, "Trapezio (sobra)"))
        return p
    # automatico
    if n_int == 1:
        return [(i0, i0 + 1, "Trapezio")]
    if n_int == 2:
        return [(i0, i0 + 2, "Simpson 1/3")]
    if n_int == 3:
        return [(i0, i0 + 3, "Simpson 3/8")]
    if n_int % 2 == 0:
        return [(i0, i0 + n_int, "Simpson 1/3")]
    # impar e >= 5: 3/8 nos tres primeiros, 1/3 no restante (par)
    return [(i0, i0 + 3, "Simpson 3/8"), (i0 + 3, i0 + n_int, "Simpson 1/3")]


def planejar_integracao(v, metodo="auto"):
    """Plano completo (respeitando trechos de passo constante)."""
    plano = []
    for a, b in trechos_uniformes(v):
        plano += _plano_trecho(a, b - a, metodo)
    return plano


def _aplica(v, f, a, b, regra):
    h = (v[b] - v[a]) / (b - a)
    seg = f[a:b + 1]
    if regra.startswith("Simpson 1/3"):
        n = b - a
        s = seg[0] + seg[-1] + 4 * seg[1:-1:2].sum() + 2 * seg[2:-1:2].sum()
        return h / 3.0 * s
    if regra.startswith("Simpson 3/8"):
        total = 0.0
        for k in range(a, b, 3):
            total += 3 * h / 8.0 * (f[k] + 3 * f[k + 1] + 3 * f[k + 2] + f[k + 3])
        return total
    # trapezio composto
    return np.trapezoid(seg, v[a:b + 1]) if hasattr(np, "trapezoid") else np.trapz(seg, v[a:b + 1])


def integrar(v, f, metodo="auto", nome_eixo="estacoes"):
    """
    Integra f em relacao a v e devolve (valor, auditoria).
    auditoria: lista de dicionarios com trecho, regra, passo h e contribuicao.
    """
    v = np.asarray(v, float)
    f = np.asarray(f, float)
    if len(v) < 2:
        return 0.0, []
    if len(v) != len(f):
        raise ValueError("Vetores de tamanhos diferentes na integracao.")
    if not np.all(np.isfinite(f)):
        f = np.nan_to_num(f, nan=0.0)

    plano = planejar_integracao(v, metodo)
    total, aud = 0.0, []
    for a, b, regra in plano:
        val = _aplica(v, f, a, b, regra)
        total += val
        aud.append({"Trecho": f"{nome_eixo} {a}-{b}",
                    "de": float(v[a]), "ate": float(v[b]),
                    "Regra": regra, "h": float((v[b] - v[a]) / (b - a)),
                    "Contribuicao": float(val)})
    return float(total), aud


def auditoria_texto(aud) -> str:
    """Formato do enunciado: 'Estacoes 0-2: Simpson 1/3 ; 2-5: Simpson 3/8 ...'"""
    return " ; ".join(f"{a['Trecho']}: {a['Regra']}" for a in aud) if aud else "-"


# ---------------------------------------------------------------------------
# S5.1 - PESOS DE INTEGRACAO (a_i)
# A integracao e escrita como  I = SUM( a_i * f_i ).
# Os coeficientes a_i sao exatamente os mesmos exibidos nas tabelas de calculo,
# de modo que a tabela mostrada ao usuario REPRODUZ o numero apresentado.
# ---------------------------------------------------------------------------

def pesos_integracao(v, metodo="auto"):
    """Retorna (a, mult, plano): a = pesos com h embutido; mult = multiplicador classico."""
    v = np.asarray(v, float)
    n = len(v)
    a = np.zeros(n)
    mult = np.zeros(n)
    plano = planejar_integracao(v, metodo)
    for i0, i1, regra in plano:
        h = (v[i1] - v[i0]) / (i1 - i0)
        m = np.zeros(i1 - i0 + 1)
        if regra.startswith("Simpson 1/3"):
            m[0] += 1
            m[-1] += 1
            m[1:-1:2] += 4
            m[2:-1:2] += 2
            a[i0:i1 + 1] += m * h / 3.0
        elif regra.startswith("Simpson 3/8"):
            for k in range(0, i1 - i0, 3):
                m[k] += 1
                m[k + 1] += 3
                m[k + 2] += 3
                m[k + 3] += 1
            a[i0:i1 + 1] += m * 3.0 * h / 8.0
        else:  # trapezio composto
            m[:] = 1
            m[0] = 0.5
            m[-1] = 0.5
            a[i0:i1 + 1] += m * h
        mult[i0:i1 + 1] += m
    return a, mult, plano


def integrar(v, f, metodo="auto", nome_eixo="estacoes"):
    """Integra f dv. Retorna (valor, auditoria). Usa exatamente os pesos a_i."""
    v = np.asarray(v, float)
    f = np.nan_to_num(np.asarray(f, float), nan=0.0)
    if len(v) < 2:
        return 0.0, []
    a, mult, plano = pesos_integracao(v, metodo)
    total = float(np.dot(a, f))
    aud = []
    for i0, i1, regra in plano:
        h = (v[i1] - v[i0]) / (i1 - i0)
        parcial = float(np.dot(a[i0:i1 + 1] if len(plano) == 1 else _pesos_local(v, i0, i1, regra),
                               f[i0:i1 + 1]))
        aud.append({"Trecho": f"{nome_eixo} {i0}-{i1}", "de": float(v[i0]), "ate": float(v[i1]),
                    "Regra": regra, "h": float(h), "Contribuicao": parcial})
    return total, aud


def _pesos_local(v, i0, i1, regra):
    h = (v[i1] - v[i0]) / (i1 - i0)
    m = np.zeros(i1 - i0 + 1)
    if regra.startswith("Simpson 1/3"):
        m[0] += 1
        m[-1] += 1
        m[1:-1:2] += 4
        m[2:-1:2] += 2
        return m * h / 3.0
    if regra.startswith("Simpson 3/8"):
        for k in range(0, i1 - i0, 3):
            m[k] += 1
            m[k + 1] += 3
            m[k + 2] += 3
            m[k + 3] += 1
        return m * 3.0 * h / 8.0
    m[:] = 1
    m[0] = 0.5
    m[-1] = 0.5
    return m * h


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


# ============================================================================ #
# S8 - GRAFICOS: PLANO DE LINHAS, SECOES, LINHAS D'AGUA E 3D                   #
# ============================================================================ #
#
# O plano de linhas classico tem tres vistas, todas obtidas da mesma tabela:
#   - Body Plan       (secoes transversais: y x z, meia-nau ao centro)
#   - Half-Breadth    (linhas d'agua vistas de cima: x x y)
#   - Buttock/Sheer   (linhas de alto vistas de lado: x x z)
# ---------------------------------------------------------------------------

COR_RE = "#1f77b4"      # metade de re
COR_VANTE = "#d62728"   # metade de vante
COR_AGUA = "#2a9df4"


def _acabamento(ax, titulo, xl, yl, igual=True, ajuste="datalim"):
    """
    ajuste='datalim' expande os limites dos dados para manter a escala igual
    (adequado ao plano de balizas); ajuste='box' encolhe a moldura em vez dos
    limites, o que mantem as vistas longas (perfil e meia-boca) legiveis sem
    perder a escala 1:1.
    """
    ax.set_title(titulo, fontsize=10, fontweight="bold")
    ax.set_xlabel(xl, fontsize=8)
    ax.set_ylabel(yl, fontsize=8)
    ax.grid(True, ls=":", lw=0.5, alpha=0.6)
    ax.tick_params(labelsize=7)
    if igual:
        ax.set_aspect("equal", adjustable=ajuste)


def plot_body_plan(tab: Tabela, T=None, ax=None):
    """
    Secoes transversais. Convencao classica: balizas de VANTE a direita do eixo
    de simetria e balizas de RE a esquerda.
    """
    criado = ax is None
    if criado:
        fig, ax = plt.subplots(figsize=(5.2, 5.0))
    meio = 0.5 * (tab.x[0] + tab.x[-1])
    for i in range(tab.n_est):
        y = np.nan_to_num(tab.Y[i], nan=np.nan)
        bons = np.isfinite(y)
        if bons.sum() < 2:
            continue
        vante = tab.x[i] >= meio
        sinal = 1.0 if vante else -1.0
        cor = COR_VANTE if vante else COR_RE
        ax.plot(sinal * y[bons], tab.z[bons], color=cor, lw=1.0, alpha=0.85)
        ax.plot([sinal * y[bons][0]], [tab.z[bons][0]], ".", color=cor, ms=2)
    ax.axvline(0, color="k", lw=0.8)
    ax.axhline(z_base(tab), color="k", lw=0.8)
    if T is not None:
        nivel = z_base(tab) + T
        ax.axhline(nivel, color=COR_AGUA, lw=1.4, ls="--")
        ax.text(0.02, nivel, f" calado T = {fmt(T)} m", color=COR_AGUA,
                fontsize=7, va="bottom", transform=ax.get_yaxis_transform())
    _acabamento(ax, "Plano de balizas (Body Plan)\nre a esquerda | vante a direita",
                "meia-boca y (m)", "z (m)")
    if criado:
        fig.tight_layout()
        return fig
    return None


def plot_meia_boca(tab: Tabela, T=None, ax=None):
    """Linhas d'agua vistas de cima (Half-Breadth Plan)."""
    criado = ax is None
    if criado:
        fig, ax = plt.subplots(figsize=(7.2, 3.0))
    cmap = plt.get_cmap("viridis")
    for j in range(tab.n_wl):
        y = tab.Y[:, j]
        bons = np.isfinite(y)
        if bons.sum() < 2:
            continue
        cor = cmap(j / max(tab.n_wl - 1, 1))
        ax.plot(tab.x[bons], y[bons], color=cor, lw=1.0,
                label=f"z={fmt(tab.z[j], 2)}" if tab.n_wl <= 12 else None)
        ax.plot(tab.x[bons], -y[bons], color=cor, lw=1.0, alpha=0.35)
    if T is not None:
        nivel = z_base(tab) + T
        yT = np.array([y_interp_z(tab, i, nivel) for i in range(tab.n_est)])
        ax.plot(tab.x, yT, color=COR_AGUA, lw=2.0, label=f"linha d'agua T={fmt(T)} m")
        ax.plot(tab.x, -yT, color=COR_AGUA, lw=2.0)
    ax.axhline(0, color="k", lw=0.8)
    _acabamento(ax, "Plano de linhas d'agua (Half-Breadth Plan)", "x (m)", "y (m)",
                ajuste="box")
    if tab.n_wl <= 12:
        ax.legend(fontsize=6, ncol=3, loc="upper right")
    if criado:
        fig.tight_layout()
        return fig
    return None


def plot_alto(tab: Tabela, T=None, n_buttock=5, ax=None):
    """Linhas de alto / perfil (Buttock Lines): cortes em y constante."""
    criado = ax is None
    if criado:
        fig, ax = plt.subplots(figsize=(7.2, 3.0))
    ymax = np.nanmax(tab.Y) if np.isfinite(tab.Y).any() else 1.0
    cortes = np.linspace(0, ymax * 0.95, n_buttock + 1)[1:]
    cmap = plt.get_cmap("plasma")
    for k, yc in enumerate(cortes):
        xs, zs = [], []
        for i in range(tab.n_est):
            y = np.nan_to_num(tab.Y[i], nan=0.0)
            # menor z em que a meia-boca atinge yc
            achou = None
            for j in range(1, tab.n_wl):
                if (y[j - 1] - yc) * (y[j] - yc) <= 0 and abs(y[j] - y[j - 1]) > 1e-12:
                    t = (yc - y[j - 1]) / (y[j] - y[j - 1])
                    achou = tab.z[j - 1] + t * (tab.z[j] - tab.z[j - 1])
                    break
            if achou is not None:
                xs.append(tab.x[i])
                zs.append(achou)
        if len(xs) >= 2:
            ax.plot(xs, zs, color=cmap(k / max(len(cortes) - 1, 1)), lw=1.0,
                    label=f"y={fmt(yc, 2)}")
    # contorno do perfil: maior z com dado e a linha de base
    ax.plot(tab.x, np.full(tab.n_est, tab.z[-1]), color="0.4", lw=1.0, ls="-")
    ax.plot(tab.x, np.full(tab.n_est, z_base(tab)), color="k", lw=1.0)
    if T is not None:
        ax.axhline(z_base(tab) + T, color=COR_AGUA, lw=1.6, ls="--")
    _acabamento(ax, "Linhas de alto / perfil (Buttock Lines)", "x (m)", "z (m)",
                ajuste="box")
    if ax.get_legend_handles_labels()[0]:
        ax.legend(fontsize=6, ncol=3, loc="lower right")
    if criado:
        fig.tight_layout()
        return fig
    return None


def plot_plano_de_linhas(tab: Tabela, T=None):
    """Prancha completa com as tres vistas do plano de linhas."""
    fig = plt.figure(figsize=(11.5, 7.6))
    gs = fig.add_gridspec(2, 2, height_ratios=[1.15, 1.0], width_ratios=[1.0, 1.35],
                          hspace=0.35, wspace=0.22)
    ax1 = fig.add_subplot(gs[0, 0])
    ax2 = fig.add_subplot(gs[0, 1])
    ax3 = fig.add_subplot(gs[1, :])
    plot_body_plan(tab, T, ax1)
    plot_alto(tab, T, 5, ax2)
    plot_meia_boca(tab, T, ax3)
    fig.suptitle("PLANO DE LINHAS reconstruido a partir da tabela de cotas",
                 fontsize=12, fontweight="bold")
    return fig


def plot_3d(tab: Tabela, T=None, superficie=True, exagero=1.0, elev=22, azim=-125):
    """
    Casco 3D simplificado (wireframe + superficie espelhada).
    NAO e uma representacao fiel: e apenas a superficie que passa pelos pontos da
    tabela de cotas, sem alisamento.
    `exagero` amplia visualmente as escalas transversal e vertical (1,0 = escala real).
    """
    fig = plt.figure(figsize=(10.5, 5.4))
    ax = fig.add_subplot(111, projection="3d")
    X, Z = np.meshgrid(tab.x, tab.z, indexing="ij")
    Y = np.nan_to_num(tab.Y, nan=0.0)

    if superficie:
        for lado in (1.0, -1.0):
            ax.plot_surface(X, lado * Y, Z, color="#8fbcd4", alpha=0.60, linewidth=0,
                            rstride=1, cstride=1, shade=True)
    for i in range(tab.n_est):
        for lado in (1.0, -1.0):
            ax.plot(np.full(tab.n_wl, tab.x[i]), lado * Y[i], tab.z,
                    color="#20465e", lw=0.7)
    for j in range(tab.n_wl):
        for lado in (1.0, -1.0):
            ax.plot(tab.x, lado * Y[:, j], np.full(tab.n_est, tab.z[j]),
                    color="#20465e", lw=0.5, alpha=0.7)

    if T is not None:
        nivel = z_base(tab) + T
        ymax = float(np.nanmax(Y)) * 1.15 + 1e-6
        xx, yy = np.meshgrid([tab.x[0], tab.x[-1]], [-ymax, ymax])
        ax.plot_surface(xx, yy, np.full_like(xx, nivel, dtype=float),
                        color=COR_AGUA, alpha=0.20, linewidth=0)

    ax.set_xlabel("x (m)", fontsize=8, labelpad=10)
    ax.set_ylabel("y (m)", fontsize=8, labelpad=6)
    ax.set_zlabel("z (m)", fontsize=8, labelpad=2)
    titulo = "Casco 3D simplificado (wireframe + superficie)"
    if abs(exagero - 1.0) > 1e-9:
        titulo += f"  -  escalas y e z ampliadas {fmt(exagero,1)}x apenas para visualizacao"
    ax.set_title(titulo + "\nRepresentacao aproximada: nao substitui software de modelagem",
                 fontsize=10, fontweight="bold")
    Lx = float(tab.x[-1] - tab.x[0]) or 1.0
    Ly = 2 * float(np.nanmax(Y)) or 1.0
    Lz = float(tab.z[-1] - tab.z[0]) or 1.0
    try:
        ax.set_box_aspect((Lx, Ly * exagero, Lz * exagero))
    except Exception:
        pass
    ax.view_init(elev=elev, azim=azim)
    ax.tick_params(labelsize=6, pad=1)
    fig.tight_layout()
    return fig


def plot_areas_seccionais(tab: Tabela, A, T, origem="tabela"):
    """Curva de areas seccionais A = A(x) para o calado selecionado."""
    fig, ax = plt.subplots(figsize=(7.6, 3.4))
    xs = np.array([converter_origem(v, tab, origem) for v in tab.x])
    ax.plot(xs, A, "-o", color="#0b6e4f", ms=4, lw=1.6)
    ax.fill_between(xs, 0, A, color="#0b6e4f", alpha=0.15)
    imax = int(np.argmax(A))
    ax.plot([xs[imax]], [A[imax]], "o", color="#d62728", ms=7)
    ax.annotate(f"A_M = {fmt(A[imax])} m2\n(baliza {tab.rotulos[imax]})",
                (xs[imax], A[imax]), textcoords="offset points", xytext=(8, -18),
                fontsize=7, color="#d62728")
    ax.set_title(f"Curva de areas seccionais A = A(x)  |  calado T = {fmt(T)} m",
                 fontsize=10, fontweight="bold")
    ax.set_xlabel("x (m)", fontsize=8)
    ax.set_ylabel("A (m2)", fontsize=8)
    ax.grid(True, ls=":", lw=0.5)
    ax.tick_params(labelsize=7)
    fig.tight_layout()
    return fig


def plot_secao(tab: Tabela, i: int, T: float):
    """Uma baliza isolada com a area submersa hachurada."""
    fig, ax = plt.subplots(figsize=(4.2, 4.4))
    y = np.nan_to_num(tab.Y[i], nan=0.0)
    ax.plot(y, tab.z, "-o", color="#20465e", ms=3, lw=1.2)
    ax.plot(-y, tab.z, "-o", color="#20465e", ms=3, lw=1.2)
    zs, ys = perfil_secao(tab, i, T)
    ax.fill_betweenx(zs, -ys, ys, color=COR_AGUA, alpha=0.30)
    ax.axhline(z_base(tab) + T, color=COR_AGUA, lw=1.4, ls="--")
    ax.axvline(0, color="k", lw=0.8)
    _acabamento(ax, f"Baliza {tab.rotulos[i]}  (x = {fmt(tab.x[i])} m)", "y (m)", "z (m)")
    fig.tight_layout()
    return fig


def plot_curvas(df: pd.DataFrame, chaves=None):
    """Painel com as curvas hidrostaticas obrigatorias (item 21)."""
    chaves = chaves or CURVAS_OBRIGATORIAS
    colT = [c for c in df.columns if c.startswith("T (calado)")][0]
    T = df[colT].to_numpy(float)
    disponiveis = []
    for k in chaves:
        rot, uni, _ = PROPRIEDADES[k]
        col = f"{rot} [{uni}]"
        if col in df.columns and np.isfinite(df[col].to_numpy(float)).any():
            disponiveis.append((k, col, rot, uni))
    n = len(disponiveis)
    ncol = 3
    nlin = int(np.ceil(n / ncol))
    fig, axs = plt.subplots(nlin, ncol, figsize=(11.5, 2.5 * nlin))
    axs = np.atleast_1d(axs).ravel()
    for ax, (k, col, rot, uni) in zip(axs, disponiveis):
        v = df[col].to_numpy(float)
        ax.plot(v, T, "-o", ms=3, lw=1.5, color="#20465e")
        ax.set_title(f"T x {rot}", fontsize=9, fontweight="bold")
        ax.set_xlabel(f"{rot} [{uni}]", fontsize=7)
        ax.set_ylabel("T (m)", fontsize=7)
        ax.grid(True, ls=":", lw=0.5)
        ax.tick_params(labelsize=6)
    for ax in axs[n:]:
        ax.axis("off")
    fig.suptitle("HYDROSTATIC CURVES  -  calado no eixo vertical (convencao naval)",
                 fontsize=12, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    return fig


def plot_diagrama_combinado(df: pd.DataFrame, chaves=None):
    """
    Diagrama hidrostatico combinado: varias curvas no mesmo par de eixos,
    normalizadas pelo proprio maximo, com o fator de escala na legenda.
    """
    chaves = chaves or ["VOL", "DESL", "AWP", "KB", "KMT", "LCB", "LCF", "TPC", "CB"]
    colT = [c for c in df.columns if c.startswith("T (calado)")][0]
    T = df[colT].to_numpy(float)
    fig, ax = plt.subplots(figsize=(9.0, 6.0))
    cmap = plt.get_cmap("tab10")
    k = 0
    for chave in chaves:
        rot, uni, _ = PROPRIEDADES[chave]
        col = f"{rot} [{uni}]"
        if col not in df.columns:
            continue
        v = df[col].to_numpy(float)
        if not np.isfinite(v).any():
            continue
        esc = np.nanmax(np.abs(v))
        if esc <= EPS:
            continue
        ax.plot(v / esc, T, lw=1.6, color=cmap(k % 10),
                label=f"{rot} [{uni}]  (x {fmt(esc, 3)})")
        k += 1
    ax.set_xlabel("valor normalizado pelo maximo de cada curva", fontsize=9)
    ax.set_ylabel("Calado T (m)", fontsize=9)
    ax.set_title("Diagrama hidrostatico combinado", fontsize=11, fontweight="bold")
    ax.grid(True, ls=":", lw=0.6)
    ax.legend(fontsize=7, loc="best")
    fig.tight_layout()
    return fig


def fig_para_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=115, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def fig_para_png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    return buf.getvalue()


# ============================================================================ #
# S9 - RELATORIO E EXPORTACOES                                                 #
# ============================================================================ #

CSS_RELATORIO = """
body{font-family:Segoe UI,Helvetica,Arial,sans-serif;margin:34px;color:#1a1a1a;
     line-height:1.5;max-width:1150px}
h1{border-bottom:3px solid #20465e;padding-bottom:8px;color:#20465e}
h2{margin-top:34px;color:#20465e;border-bottom:1px solid #c8d6e0;padding-bottom:4px}
h3{margin-top:22px;color:#2c6382}
table{border-collapse:collapse;font-size:12px;margin:10px 0;width:100%}
th{background:#20465e;color:#fff;padding:6px 8px;text-align:left;font-weight:600}
td{border:1px solid #d5dee5;padding:5px 8px}
tr:nth-child(even) td{background:#f4f8fa}
.box{border-left:5px solid #20465e;background:#f2f7fa;padding:12px 16px;margin:14px 0}
.aviso{border-left:5px solid #e8a33d;background:#fdf6e9;padding:12px 16px;margin:14px 0}
.erro{border-left:5px solid #c0392b;background:#fbeeec;padding:12px 16px;margin:14px 0}
.ok{border-left:5px solid #2e8b57;background:#eef7f1;padding:12px 16px;margin:14px 0}
img{max-width:100%;border:1px solid #d5dee5;border-radius:4px;margin:10px 0}
code{background:#eef2f5;padding:2px 5px;border-radius:3px;font-size:12px}
.rodape{margin-top:40px;border-top:1px solid #ccc;padding-top:12px;font-size:11px;color:#666}
"""


def _tab_html(df: pd.DataFrame, casas=4, max_linhas=400) -> str:
    if df is None or len(df) == 0:
        return "<p><i>(sem registros)</i></p>"
    d = df.head(max_linhas).copy()
    for c in d.columns:
        if pd.api.types.is_numeric_dtype(d[c]):
            d[c] = d[c].map(lambda v: fmt(v, casas))
    extra = "" if len(df) <= max_linhas else \
        f"<p><i>(exibindo as primeiras {max_linhas} de {len(df)} linhas)</i></p>"
    return d.to_html(index=False, escape=False) + extra


def gerar_relatorio(ctx: dict) -> str:
    """Monta o relatorio HTML autocontido (imagens embutidas em base64)."""
    p = []
    A = p.append
    principais = ctx["principais"]
    tab = ctx["tab"]
    opt = ctx["opt"]

    A(f"<html><head><meta charset='utf-8'><title>Relatorio hidrostatico - "
      f"{principais.get('nome','embarcacao')}</title><style>{CSS_RELATORIO}</style></head><body>")
    A(f"<h1>Relatorio de Calculo Hidrostatico</h1>")
    A(f"<p><b>Embarcacao:</b> {principais.get('nome','(sem nome)')} &nbsp;|&nbsp; "
      f"<b>Emitido em:</b> {agora()} &nbsp;|&nbsp; <b>Aplicativo:</b> {APP_NOME} v{APP_VERSAO}</p>")

    A("<div class='aviso'><b>Aviso de responsabilidade.</b> Este aplicativo trabalha com uma "
      "representacao geometrica simplificada, obtida por interpolacao de uma tabela de cotas "
      "discreta. Ele pode cometer erros e nao substitui software de modelagem naval avancada. "
      "Todos os resultados devem ser conferidos. As alteracoes feitas dentro do aplicativo nao "
      "modificam o arquivo original importado.</div>")

    # ---- 1. dados principais
    A("<h2>1. Dados principais da embarcacao</h2>")
    dfp = pd.DataFrame([{"Grandeza": k, "Valor": v} for k, v in principais.items()])
    A(_tab_html(dfp, 4))
    A(f"<p><b>Unidade da tabela de cotas informada:</b> {ctx.get('unidade_origem','-')} "
      f"&nbsp;|&nbsp; <b>Calculos internos:</b> SI (metros) "
      f"&nbsp;|&nbsp; <b>Densidade:</b> {fmt(opt.get('rho'), 4)} t/m3</p>")
    A(f"<p><b>Referencia longitudinal de apresentacao:</b> {ctx.get('origem_txt','-')}<br>"
      f"<b>Linha de base adotada:</b> z = {fmt(z_base(tab))} m "
      f"(o calado T e medido a partir dela)</p>")

    # ---- 2. arquivo e interpretacao
    A("<h2>2. Arquivo de origem e interpretacao da tabela</h2>")
    A(f"<p><b>Arquivo:</b> {ctx.get('arquivo','(entrada manual)')} &nbsp;|&nbsp; "
      f"<b>Aba:</b> {ctx.get('aba','-')}</p>")
    for n in ctx.get("notas_deteccao", []):
        A(f"<div class='box'>{n}</div>")
    A(f"<p><b>Estacoes:</b> {tab.n_est} &nbsp;|&nbsp; <b>Linhas d'agua:</b> {tab.n_wl} "
      f"&nbsp;|&nbsp; <b>Extensao longitudinal:</b> {fmt(tab.x[-1]-tab.x[0])} m "
      f"&nbsp;|&nbsp; <b>Pontal coberto pela tabela:</b> {fmt(tab.z[-1]-tab.z[0])} m</p>")

    A("<h3>2.1 Tabela de cotas ORIGINAL (como foi lida do arquivo)</h3>")
    A(_tab_html(ctx["tab_original_df"], 4))
    A("<h3>2.2 Tabela de trabalho utilizada nos calculos</h3>")
    A(_tab_html(tab.como_df(), 4))
    A(f"<p><b>Celulas provenientes do arquivo:</b> {int(tab.original.sum())} &nbsp;|&nbsp; "
      f"<b>Celulas geradas por interpolacao/hipotese:</b> {tab.n_interpolados()}</p>")

    # ---- 3. diagnostico
    A("<h2>3. Diagnostico da geometria (deteccao de problemas)</h2>")
    ach = ctx.get("achados", [])
    if not ach:
        A("<div class='ok'>Nenhum problema detectado nas verificacoes automaticas.</div>")
    else:
        A(_tab_html(pd.DataFrame([a.como_dict() for a in ach])))
    ign = ctx.get("avisos_ignorados", [])
    if ign:
        A("<div class='aviso'><b>Avisos que o usuario decidiu ignorar e prosseguir:</b><ul>"
          + "".join(f"<li>{i}</li>" for i in ign) + "</ul></div>")

    # ---- 4. interpolacao
    A("<h2>4. Interpolacao</h2>")
    regs = ctx.get("interpolacoes", [])
    if not regs:
        A("<p>Nenhuma interpolacao foi necessaria: todos os valores vieram do arquivo.</p>")
    else:
        A(f"<p>Foram gerados <b>{len(regs)}</b> valores. Metodo padrao: interpolacao linear. "
          "Dados originais e interpolados sao mantidos separados.</p>")
        A(_tab_html(pd.DataFrame(regs), 4))

    # ---- 5. metodos de integracao
    A("<h2>5. Metodos de integracao</h2>")
    A("<p>Regras implementadas diretamente no codigo: <code>Trapezio</code>, "
      "<code>Simpson 1/3</code> e <code>Simpson 3/8</code>. A escolha automatica aplica "
      "Simpson 1/3 em numero par de intervalos, Simpson 3/8 nos tres primeiros intervalos "
      "quando o numero e impar, e Trapezio nos trechos de passo variavel.</p>")
    A(f"<div class='box'><b>Auditoria longitudinal (eixo x):</b><br>"
      f"{ctx.get('aud_x','-')}</div>")
    A(f"<div class='box'><b>Auditoria vertical (eixo z):</b><br>"
      f"{ctx.get('aud_z','-')}</div>")

    # ---- 6. calculo detalhado no calado selecionado
    r = ctx.get("resultado")
    if r:
        A(f"<h2>6. Calculo detalhado para o calado T = {fmt(r['T'])} m</h2>")
        A("<h3>6.1 Areas seccionais  A_i(T) = 2 &int; y dz</h3>")
        A(_tab_html(ctx["df_areas"], 4))
        if ctx.get("img_areas"):
            A(f"<img src='data:image/png;base64,{ctx['img_areas']}'>")
        A("<h3>6.2 Plano d'agua, LCF e momentos de inercia</h3>")
        A(_tab_html(r["_pw"]["df"], 5))
        A(f"<div class='box'>A_WP = 2 &sum; a<sub>i</sub> y<sub>i</sub> = "
          f"<b>{fmt(r['AWP'])} m2</b><br>"
          f"LCF = (2 &sum; a<sub>i</sub> y<sub>i</sub> x<sub>i</sub>) / A_WP = "
          f"<b>{fmt(ctx.get('LCF_apr', r['LCF']))} m</b> ({ctx.get('origem_txt','')})<br>"
          f"I<sub>t</sub> = (2/3) &sum; a<sub>i</sub> y<sub>i</sub>&sup3; = "
          f"<b>{fmt(r['IT'])} m4</b><br>"
          f"I<sub>l</sub> = <b>{fmt(r['IL'])} m4</b> &nbsp;({r['_pw']['eixo_IL']})</div>")
        A("<h3>6.3 Volume longitudinal</h3>")
        A(_tab_html(r["_vol"]["df_L"], 5))
        A("<h3>6.4 Volume vertical (caminho independente)</h3>")
        A(_tab_html(r["_vol"]["df_V"], 5))
        A(f"<div class='box'>&nabla;<sub>L</sub> = <b>{fmt(r['VOL_L'])} m3</b> &nbsp;|&nbsp; "
          f"&nabla;<sub>V</sub> = <b>{fmt(r['VOL_V'])} m3</b><br>"
          f"E<sub>&nabla;</sub> = |&nabla;<sub>L</sub> - &nabla;<sub>V</sub>| / "
          f"|&nabla;<sub>L</sub>| x 100 = <b>{fmt(r['E_VOL'], 4)} %</b><br>"
          f"Volume adotado nos demais calculos: <b>{opt.get('volume_adotado')}</b> = "
          f"{fmt(r['VOL'])} m3</div>")
        A(f"<p>{ctx.get('interpretacao_evol','')}</p>")
        A("<h3>6.5 Superficie molhada (WSA)</h3>")
        A("<p>Metodo do semi-perimetro molhado: em cada baliza soma-se a meia-largura do "
          "fundo com o comprimento do contorno submerso; o resultado e integrado ao longo "
          "de x e multiplicado por 2. Nao inclui popa espelhada nem apendices.</p>")
        A(_tab_html(r["_wsa_df"], 4))
        A(f"<div class='box'>WSA = 2 &sum; a<sub>i</sub> s<sub>i</sub> = "
          f"<b>{fmt(r['WSA'])} m2</b></div>")
        A("<h3>6.6 Resumo das propriedades no calado selecionado</h3>")
        A(_tab_html(ctx["df_resumo"], 5))
        A("<h3>6.7 Memoria de calculo das propriedades derivadas</h3>")
        A(f"<div class='box'>"
          f"BM<sub>t</sub> = I<sub>t</sub> / &nabla; = {fmt(r['IT'])} / {fmt(r['VOL'])} = "
          f"<b>{fmt(r['BMT'], 4)} m</b><br>"
          f"KM<sub>t</sub> = KB + BM<sub>t</sub> = {fmt(r['KB'], 4)} + {fmt(r['BMT'], 4)} = "
          f"<b>{fmt(r['KMT'], 4)} m</b><br>"
          f"BM<sub>l</sub> = I<sub>l</sub> / &nabla; = {fmt(r['IL'])} / {fmt(r['VOL'])} = "
          f"<b>{fmt(r['BML'], 4)} m</b><br>"
          f"KM<sub>l</sub> = KB + BM<sub>l</sub> = <b>{fmt(r['KML'], 4)} m</b><br>"
          f"&Delta; = &rho; &nabla; = {fmt(r['rho'], 4)} x {fmt(r['VOL'])} = "
          f"<b>{fmt(r['DESL'])} t</b><br>"
          f"TPC = &rho; A<sub>WP</sub> / 100 = {fmt(r['rho'], 4)} x {fmt(r['AWP'])} / 100 = "
          f"<b>{fmt(r['TPC'], 4)} t/cm</b><br>"
          f"C<sub>B</sub> = &nabla; / (L B T) = {fmt(r['VOL'])} / ({fmt(r['L_usado'])} x "
          f"{fmt(r['B_usado'])} x {fmt(r['T'])}) = <b>{fmt(r['CB'], 4)}</b><br>"
          f"C<sub>WP</sub> = A<sub>WP</sub> / (L B) = <b>{fmt(r['CWP'], 4)}</b><br>"
          f"C<sub>M</sub> = A<sub>M</sub> / (B T) = {fmt(r['AM'])} / ({fmt(r['B_usado'])} x "
          f"{fmt(r['T'])}) = <b>{fmt(r['CM'], 4)}</b><br>"
          f"C<sub>P</sub> = &nabla; / (A<sub>M</sub> L) = <b>{fmt(r['CP'], 4)}</b></div>")

    # ---- 7. geometria
    A("<h2>7. Representacao geometrica</h2>")
    for chave, legenda in [("img_linhas", "Plano de linhas reconstruido"),
                           ("img_3d", "Casco 3D simplificado")]:
        if ctx.get(chave):
            A(f"<h3>{legenda}</h3><img src='data:image/png;base64,{ctx[chave]}'>")
    A("<div class='aviso'>O modelo 3D e uma superficie aproximada construida apenas com os "
      "pontos da tabela de cotas. Nao representa fielmente o casco e nao deve ser usado como "
      "modelo de projeto.</div>")

    # ---- 8. hydrostatic table e curves
    if ctx.get("df_ht") is not None and len(ctx["df_ht"]):
        A("<h2>8. Hydrostatic Table</h2>")
        A(f"<p>Calados de {fmt(ctx.get('Tmin'))} m a {fmt(ctx.get('Tmax'))} m, "
          f"incremento &Delta;T = {fmt(ctx.get('dT'))} m.</p>")
        A(_tab_html(ctx["df_ht"], 4, 200))
    if ctx.get("img_curvas"):
        A("<h2>9. Hydrostatic Curves</h2>")
        A(f"<img src='data:image/png;base64,{ctx['img_curvas']}'>")
    if ctx.get("img_combinado"):
        A(f"<h3>Diagrama combinado</h3>"
          f"<img src='data:image/png;base64,{ctx['img_combinado']}'>")

    # ---- 10. validacao
    A("<h2>10. Validacao</h2>")
    if ctx.get("df_val_int") is not None:
        A("<h3>10.1 Consistencia interna</h3>")
        A(_tab_html(ctx["df_val_int"], 6))
    if ctx.get("df_val_ana") is not None:
        A("<h3>10.2 Validacao analitica (barcaca paralelepipedica)</h3>")
        A(_tab_html(ctx["df_val_ana"], 6))
    if ctx.get("df_val_max") is not None:
        A("<h3>10.3 Comparacao com software de referencia (Maxsurf)</h3>")
        A(_tab_html(ctx["df_val_max"], 4))

    # ---- 11. historico
    A("<h2>11. Historico completo (auditoria)</h2>")
    A("<p>Registro cronologico de tudo o que foi detectado, alterado e decidido, "
      "identificando o autor de cada acao.</p>")
    A(_tab_html(ctx["historico"], 4, 600))

    # ---- 12. limitacoes
    A("<h2>12. Limitacoes conhecidas</h2>")
    A("<ul>"
      "<li>A geometria e reconstruida por interpolacao linear entre pontos discretos: "
      "quanto menos estacoes e linhas d'agua, maior o erro de discretizacao.</li>"
      "<li>As regras de Simpson exigem passo constante; em trechos irregulares o "
      "aplicativo recorre ao Trapezio, de ordem menor.</li>"
      "<li>A superficie molhada nao inclui popa espelhada, apendices, leme nem helice.</li>"
      "<li>Volume abaixo da primeira linha d'agua e acima da ultima nao esta descrito "
      "pelos dados e depende da hipotese escolhida pelo usuario.</li>"
      "<li>O modelo 3D e ilustrativo e nao substitui software de modelagem naval.</li>"
      "</ul>")
    A(f"<div class='rodape'>{APP_NOME} v{APP_VERSAO} - relatorio gerado automaticamente em "
      f"{agora()}. Os resultados sao de responsabilidade tecnica de quem os utiliza.</div>")
    A("</body></html>")
    return "\n".join(p)


def excel_hydrostatic_table(df_ht: pd.DataFrame, tab: Tabela, principais: dict,
                            hist: pd.DataFrame, df_interp: pd.DataFrame) -> bytes:
    """Exporta a Hydrostatic Table e os dados processados para .xlsx."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df_ht.to_excel(w, sheet_name="Hydrostatic Table", index=False)
        tab.como_df().to_excel(w, sheet_name="Tabela de trabalho", index=False)
        pd.DataFrame([{"Grandeza": k, "Valor": v} for k, v in principais.items()]) \
            .to_excel(w, sheet_name="Dados principais", index=False)
        if df_interp is not None and len(df_interp):
            df_interp.to_excel(w, sheet_name="Interpolacoes", index=False)
        origem = pd.DataFrame(tab.origem,
                              columns=[f"WL{j}" for j in range(tab.n_wl)])
        origem.insert(0, "Baliza", tab.rotulos)
        origem.to_excel(w, sheet_name="Origem das celulas", index=False)
        hist.to_excel(w, sheet_name="Historico", index=False)
    return buf.getvalue()


# ============================================================================ #
# S10 - INTERFACE STREAMLIT                                                    #
# ============================================================================ #

def W(esticar: bool = True) -> dict:
    """
    Compatibilidade entre versoes do Streamlit: as versoes recentes usam
    width="stretch" e as antigas use_container_width=True. Esta funcao devolve
    o argumento correto para a versao instalada, evitando avisos e quebras.
    """
    try:
        partes = st.__version__.split(".")
        versao = (int(partes[0]), int(partes[1]))
    except Exception:
        versao = (99, 99)
    if versao >= (1, 49):
        return {"width": "stretch" if esticar else "content"}
    return {"use_container_width": bool(esticar)}


st.set_page_config(page_title=APP_NOME, page_icon="⚓", layout="wide",
                   initial_sidebar_state="expanded")

CSS_APP = """
<style>
.block-container{padding-top:2.0rem;padding-bottom:3rem;max-width:1400px}
h1,h2,h3{color:#20465e}
div[data-testid="stMetricValue"]{font-size:1.35rem}
.legenda{font-size:0.82rem;color:#5a6b78}
</style>
"""
st.markdown(CSS_APP, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# S10.1 - Estado inicial e reinicializacao
# ---------------------------------------------------------------------------

PADRAO = {
    "hist": [],
    "uploader_id": 0,
    "abas": None,
    "aba_sel": None,
    "grade": None,
    "deteccao": None,
    "transposta": False,
    "arquivo_nome": None,
    "tab_original": None,      # tabela como lida (antes de interpolar)
    "tab": None,               # tabela de trabalho (usada nos calculos)
    "tab_arquivo_df": None,    # copia visual do arquivo original
    "interp_regs": [],
    "avisos_ignorados": [],
    "df_ht": None,
    "brutos_ht": None,
    "df_val_max": None,
    "principais": {"nome": "", "LPP": 0.0, "B": 0.0, "D": 0.0, "Td": 0.0},
    "opt": {"rho": 1.025, "metodo_x": "auto", "metodo_z": "auto",
            "volume_adotado": "longitudinal", "eixo_IL": "LCF",
            "origem_x": "tabela", "L_ref": "LPP", "B_ref": "BWL",
            "unidade": "m (metro)", "calculos": None},
    "T_sel": 1.0,
}


def iniciar_estado():
    for k, v in PADRAO.items():
        if k not in st.session_state:
            st.session_state[k] = (v.copy() if isinstance(v, (dict, list)) else v)


def reiniciar_tudo():
    uid = st.session_state.get("uploader_id", 0) + 1
    for k in list(st.session_state.keys()):
        if k != "uploader_id":
            del st.session_state[k]
    st.session_state.uploader_id = uid
    iniciar_estado()
    registrar("Sistema", "Aplicativo reiniciado pelo usuario. Todos os dados, tabelas, "
                         "decisoes e resultados anteriores foram descartados.",
              nivel="DECISAO", autor="usuario",
              consequencia="Uma nova tabela de cotas pode ser carregada do zero.")


iniciar_estado()


# ---------------------------------------------------------------------------
# S10.2 - Barra lateral
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("## ⚓ Calculo Hidrostatico")
    st.caption(f"AP1.1 - Projeto Integrador | v{APP_VERSAO}")

    pagina = st.radio(
        "Navegacao",
        ["Inicio",
         "Modulo 1 - Projeto e dados",
         "Modulo 2 - Geometria e validacao",
         "Modulo 3 - Interpolacao e integracao",
         "Modulo 4 - Calculo hidrostatico",
         "Modulo 5 - Hydrostatic Table",
         "Modulo 6 - Hydrostatic Curves",
         "Modulo 7 - Validacao e auditoria",
         "Relatorio final"],
        label_visibility="collapsed")

    st.divider()
    tabv = st.session_state.tab
    if tabv is not None:
        st.success(f"Tabela carregada\n\n{tabv.n_est} estacoes x {tabv.n_wl} linhas d'agua")
        falt = int((~np.isfinite(tabv.Y)).sum())
        if falt:
            st.warning(f"{falt} celula(s) ainda sem valor (ver Modulo 3)")
    else:
        st.info("Nenhuma tabela de cotas carregada")

    st.divider()
    st.markdown("**Reiniciar**")
    st.caption("Apaga tudo e permite carregar outra tabela de cotas.")
    if st.button("🔄 Reiniciar tudo", **W(), type="secondary"):
        st.session_state["_confirma_reset"] = True
    if st.session_state.get("_confirma_reset"):
        st.warning("Isso apaga dados, decisoes e resultados. Confirmar?")
        c1, c2 = st.columns(2)
        if c1.button("Sim, apagar", **W(), type="primary"):
            reiniciar_tudo()
            rerodar()
        if c2.button("Cancelar", **W()):
            st.session_state["_confirma_reset"] = False
            rerodar()


# ---------------------------------------------------------------------------
# S10.3 - Auxiliares da interface
# ---------------------------------------------------------------------------

def exige_tabela() -> bool:
    if st.session_state.tab is None:
        st.warning("Carregue ou monte a tabela de cotas no **Modulo 1** antes de continuar.")
        return False
    return True


def exige_pronta() -> bool:
    if not exige_tabela():
        return False
    t = st.session_state.tab
    if not np.isfinite(t.Y).all():
        n = int((~np.isfinite(t.Y)).sum())
        st.error(f"A tabela ainda tem **{n} celula(s) sem valor**. O aplicativo nao "
                 "calcula silenciosamente a partir de dados incompletos.\n\n"
                 "Va ao **Modulo 3** e decida como preencher, ou edite a tabela no Modulo 2.")
        return False
    if t.n_est < 3 or t.n_wl < 2:
        st.error("Sao necessarias pelo menos 3 estacoes e 2 linhas d'agua.")
        return False
    return True


def origem_texto(opt) -> str:
    return {"tabela": "x conforme a tabela de cotas (origem do arquivo)",
            "pp_re": "x = 0 na perpendicular de re, positivo para vante",
            "meia_nau": "x = 0 na meia-nau, positivo para vante"}[opt.get("origem_x", "tabela")]


def caixa_achados(achados):
    """Apresenta cada problema: onde, o que e, consequencia, opcoes."""
    erros = [a for a in achados if a.nivel == "ERRO"]
    avisos = [a for a in achados if a.nivel == "AVISO"]
    if not achados:
        st.success("Nenhum problema detectado nas verificacoes automaticas. "
                   "Ainda assim, confira o plano de linhas antes de calcular.")
        return
    if erros:
        st.error(f"{len(erros)} ERRO(S): impedem o calculo confiavel.")
    if avisos:
        st.warning(f"{len(avisos)} AVISO(S): o calculo pode continuar, mas voce precisa "
                   "conhecer as consequencias.")
    for a in achados:
        icone = "⛔" if a.nivel == "ERRO" else "⚠️"
        with st.expander(f"{icone} [{a.codigo}] {a.titulo}", expanded=(a.nivel == "ERRO")):
            st.markdown(f"**Onde:** {a.onde}")
            st.markdown(f"**O que foi encontrado:** {a.explicacao}")
            st.markdown(f"**Possiveis consequencias:** {a.consequencia}")
            if a.sugestao:
                st.markdown(f"**Como resolver:** {a.sugestao}")
            if a.nivel == "AVISO":
                chave = f"ign_{a.codigo}"
                marcado = st.checkbox(
                    "Estou ciente das consequencias e desejo prosseguir mesmo assim.",
                    key=chave, value=(a.codigo in [i.split("]")[0].strip("[")
                                                   for i in st.session_state.avisos_ignorados]))
                texto = f"[{a.codigo}] {a.titulo} - {a.consequencia}"
                if marcado and texto not in st.session_state.avisos_ignorados:
                    st.session_state.avisos_ignorados.append(texto)
                    registrar("Modulo 2 - Diagnostico",
                              f"Aviso {a.codigo} ignorado pelo usuario: {a.titulo}",
                              nivel="DECISAO", autor="usuario", consequencia=a.consequencia)
                elif (not marcado) and texto in st.session_state.avisos_ignorados:
                    st.session_state.avisos_ignorados.remove(texto)


def df_resumo_propriedades(r, tab, opt) -> pd.DataFrame:
    linhas = []
    for chave, (rot, uni, casas) in PROPRIEDADES.items():
        if chave not in r:
            continue
        v = r[chave]
        if chave in ("LCB", "LCF"):
            v = converter_origem(v, tab, opt.get("origem_x", "tabela"))
        linhas.append({"Propriedade": rot, "Valor": v, "Unidade": uni})
    return pd.DataFrame(linhas)


# =========================== PAGINA: INICIO ================================ #

if pagina == "Inicio":
    st.title("Aplicativo de Calculo Hidrostatico")
    st.markdown("**AP1.1 - Projeto Integrador de Arquitetura Naval** | "
                "da tabela de cotas as Hydrostatic Curves")

    c1, c2 = st.columns([1.35, 1])
    with c1:
        st.markdown("""
### Como o aplicativo trabalha

**DETECTAR → EXPLICAR → AVISAR → MOSTRAR CONSEQUENCIAS → VOCE DECIDE**

Nada e corrigido em silencio. Sempre que algo estiver estranho na tabela de cotas, o
aplicativo diz **onde** esta, **o que** encontrou e **o que isso causa** nos calculos.
A decisao de aceitar, corrigir ou ignorar e sempre sua, e fica registrada no historico
e no relatorio final.

O arquivo importado **nunca e alterado**: os dados sao copiados para uma tabela de
trabalho editavel.

### Roteiro
1. **Modulo 1** - dados principais, unidades e importacao da tabela de cotas
2. **Modulo 2** - interpretacao, diagnostico, edicao, plano de linhas e 3D
3. **Modulo 3** - interpolacao e escolha dos metodos de integracao
4. **Modulo 4** - propriedades hidrostaticas para um calado, com memoria de calculo
5. **Modulo 5** - Hydrostatic Table (varredura de calados, exporta Excel)
6. **Modulo 6** - Hydrostatic Curves e diagrama combinado
7. **Modulo 7** - validacao analitica, consistencia interna e comparacao com Maxsurf
8. **Relatorio final** - documento unico com tudo o que foi feito
        """)
    with c2:
        st.info("""**Formatos de tabela aceitos**

- `.xlsx`, `.xlsm`, `.xls` e `.csv`
- Linhas d'agua nas **colunas** ou nas **linhas** (transposta)
- Formato longo com colunas `x`, `z`, `y`
- Virgula ou ponto decimal
- Separador `;` `,` tab ou `|`
- Com ou sem cabecalho de alturas z

Qualquer interpretacao automatica pode ser corrigida na interface,
sem mexer no codigo-fonte.""")
        st.warning("""**Limitacoes**

A geometria e uma aproximacao construida por interpolacao de pontos discretos.
O aplicativo pode errar e **nao substitui** software de modelagem naval.
Confira sempre os resultados.""")

    st.divider()
    st.subheader("Comecar rapidamente")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**Importar arquivo**")
        st.caption("Va ao Modulo 1 e envie o .xlsx ou .csv da tabela de cotas.")
    with c2:
        st.markdown("**Digitar manualmente**")
        st.caption("Tambem no Modulo 1: escolha o numero de balizas e de linhas d'agua.")
    with c3:
        st.markdown("**Carregar barcaca de teste**")
        st.caption("Casco de solucao analitica conhecida, util para conferir o aplicativo.")
        if st.button("Carregar barcaca 40 x 10 x 5 m", **W()):
            t = barcaca_teste()
            st.session_state.tab = t
            st.session_state.tab_original = t.copia()
            st.session_state.tab_arquivo_df = t.como_df()
            st.session_state.principais = {"nome": "Barcaca de validacao",
                                           "LPP": 40.0, "B": 10.0, "D": 5.0, "Td": 2.5}
            st.session_state.arquivo_nome = "(barcaca gerada internamente)"
            registrar("Modulo 1", "Barcaca paralelepipedica 40 x 10 x 5 m carregada para teste.",
                      autor="usuario",
                      consequencia="Permite comparar o aplicativo com a solucao analitica.")
            st.success("Barcaca carregada. Va ao Modulo 1 para conferir os dados principais.")


# ==================== PAGINA: MODULO 1 - PROJETO =========================== #

elif pagina == "Modulo 1 - Projeto e dados":
    st.title("Modulo 1 - Projeto: dados principais e tabela de cotas")

    p = st.session_state.principais
    opt = st.session_state.opt

    st.subheader("1.1 Dados principais da embarcacao")
    c1, c2, c3 = st.columns(3)
    with c1:
        p["nome"] = st.text_input("Nome da embarcacao", value=p.get("nome", ""))
        p["LPP"] = st.number_input("LPP - comprimento entre perpendiculares (m)",
                                   value=float(p.get("LPP", 0.0)), min_value=0.0,
                                   step=0.1, format="%.4f")
    with c2:
        p["B"] = st.number_input("B - boca (m)", value=float(p.get("B", 0.0)),
                                 min_value=0.0, step=0.1, format="%.4f")
        p["D"] = st.number_input("D - pontal (m)", value=float(p.get("D", 0.0)),
                                 min_value=0.0, step=0.1, format="%.4f")
    with c3:
        p["Td"] = st.number_input("Td - calado de projeto (m)", value=float(p.get("Td", 0.0)),
                                  min_value=0.0, step=0.1, format="%.4f")
        opt["rho"] = st.number_input("rho - densidade da agua (t/m3)",
                                     value=float(opt.get("rho", 1.025)),
                                     min_value=0.100, max_value=2.000,
                                     step=0.001, format="%.4f",
                                     help="Dado de entrada: pode ser alterado sem mexer no codigo. "
                                          "Agua salgada ~ 1,025 | agua doce ~ 1,000")

    st.subheader("1.2 Referencias e convencoes")
    c1, c2, c3 = st.columns(3)
    with c1:
        opt["origem_x"] = st.selectbox(
            "Referencia longitudinal de apresentacao",
            ["tabela", "pp_re", "meia_nau"],
            index=["tabela", "pp_re", "meia_nau"].index(opt.get("origem_x", "tabela")),
            format_func=lambda k: {"tabela": "Como no arquivo",
                                   "pp_re": "x = 0 na perpendicular de re",
                                   "meia_nau": "x = 0 na meia-nau"}[k],
            help="Internamente o calculo usa o x da tabela; esta escolha afeta apenas "
                 "como LCB e LCF sao apresentados.")
        st.caption(origem_texto(opt))
    with c2:
        opt["L_ref"] = st.selectbox("Comprimento L usado nos coeficientes",
                                    ["LPP", "LWL"], index=0 if opt.get("L_ref") == "LPP" else 1,
                                    format_func=lambda k: {"LPP": "LPP informado",
                                                           "LWL": "L da linha d'agua"}[k])
        opt["B_ref"] = st.selectbox("Boca B usada nos coeficientes",
                                    ["BWL", "B"], index=0 if opt.get("B_ref") == "BWL" else 1,
                                    format_func=lambda k: {"BWL": "Boca na linha d'agua (calculada)",
                                                           "B": "B informada"}[k])
    with c3:
        opt["eixo_IL"] = st.selectbox(
            "Eixo de referencia para I_l (usado em BM_l)",
            ["LCF", "meia_nau"],
            index=0 if opt.get("eixo_IL") == "LCF" else 1,
            format_func=lambda k: {"LCF": "Eixo transversal pelo LCF (padrao)",
                                   "meia_nau": "Eixo transversal pela meia-nau"}[k],
            help="BM_l e definido em relacao ao eixo que passa pelo centro de flutuacao. "
                 "A opcao pela meia-nau serve apenas para comparacao.")
        opt["volume_adotado"] = st.selectbox(
            "Volume adotado nas propriedades derivadas",
            ["longitudinal", "vertical", "media"],
            index=["longitudinal", "vertical", "media"].index(
                opt.get("volume_adotado", "longitudinal")))

    st.divider()
    st.subheader("1.3 Tabela de cotas")
    st.caption("O arquivo original nunca e modificado: os dados sao copiados para uma "
               "tabela de trabalho editavel.")

    modo = st.radio("Como deseja fornecer a tabela?",
                    ["Importar arquivo (.xlsx / .xls / .csv)", "Digitar manualmente"],
                    horizontal=True)

    # ---------------- importacao ----------------
    if modo.startswith("Importar"):
        up = st.file_uploader("Arquivo da tabela de cotas",
                              type=["xlsx", "xlsm", "xls", "csv", "txt", "tsv"],
                              key=f"upl_{st.session_state.uploader_id}")
        if up is not None:
            if st.session_state.arquivo_nome != up.name or st.session_state.abas is None:
                try:
                    abas = ler_arquivo_bruto(up)
                    st.session_state.abas = abas
                    st.session_state.arquivo_nome = up.name
                    st.session_state.aba_sel = list(abas.keys())[0]
                    registrar("Modulo 1", f"Arquivo '{up.name}' importado "
                                          f"({len(abas)} aba(s)). Copia criada para trabalho.",
                              autor="usuario",
                              consequencia="O arquivo original permanece intacto.")
                except Exception as e:
                    st.error(f"Nao foi possivel ler o arquivo: {e}")
                    st.session_state.abas = None

        if st.session_state.abas:
            abas = st.session_state.abas
            if len(abas) > 1:
                st.session_state.aba_sel = st.selectbox("Aba da planilha", list(abas.keys()),
                                                        index=list(abas.keys()).index(
                                                            st.session_state.aba_sel))
            aba = st.session_state.aba_sel
            g0 = limpar_grade(abas[aba])
            st.markdown(f"**Conteudo bruto da aba `{aba}`** ({g0.shape[0]} linhas x "
                        f"{g0.shape[1]} colunas)")
            st.dataframe(g0.head(25), **W(), height=240)

            # tentativa de formato longo
            longo = detectar_formato_longo(g0)
            det, gu, transp = detectar_melhor(g0)
            st.session_state.grade = gu
            st.session_state.deteccao = det
            st.session_state.transposta = transp

            st.markdown("#### Interpretacao automatica")
            if longo is not None:
                st.info("O arquivo parece estar no **formato longo** (colunas x, z, y). "
                        "Esse formato tambem e aceito.")
                if st.button("Usar interpretacao em formato longo"):
                    x, z, Y = longo
                    t = nova_tabela(x, z, Y)
                    st.session_state.tab_original = t.copia()
                    st.session_state.tab = t
                    st.session_state.tab_arquivo_df = t.como_df()
                    registrar("Modulo 1", "Tabela lida no formato longo (x, z, y).",
                              autor="programa")
                    rerodar()

            if not det.ok:
                st.error("Nao foi possivel identificar automaticamente a estrutura da tabela. "
                         "Use os controles abaixo para indicar manualmente onde estao os dados.")
            for n in det.notas:
                st.caption(f"• {n}")

            with st.expander("Ajustar manualmente a interpretacao (orientacao, X, alturas z)",
                             expanded=not det.ok or not det.z_valores):
                st.caption("Tudo o que o aplicativo detectou pode ser corrigido aqui. "
                           "E assim que uma tabela de cotas desconhecida e processada sem "
                           "alterar o codigo-fonte.")
                nova_or = st.radio("Orientacao da tabela",
                                   ["Linhas d'agua nas COLUNAS (balizas nas linhas)",
                                    "Linhas d'agua nas LINHAS (balizas nas colunas)"],
                                   index=1 if transp else 0)
                quer_transp = nova_or.startswith("Linhas d'agua nas LINHAS")
                if quer_transp != transp:
                    base = limpar_grade(abas[aba])
                    gu = limpar_grade(base.T.reset_index(drop=True)) if quer_transp \
                        else limpar_grade(base)
                    gu.columns = range(gu.shape[1])
                    det = detectar_layout(gu)
                    st.session_state.grade, st.session_state.deteccao = gu, det
                    st.session_state.transposta = quer_transp

                nlin, ncol = gu.shape
                c1, c2 = st.columns(2)
                with c1:
                    li = st.number_input("Primeira linha de dados (1 = primeira da planilha)",
                                         1, nlin, det.lin_ini + 1)
                    lf = st.number_input("Ultima linha de dados", 1, nlin, det.lin_fim + 1)
                    cx = st.number_input("Coluna com as posicoes X (0 = nao existe)",
                                         0, ncol, (det.col_x + 1) if det.col_x is not None else 0)
                with c2:
                    ci = st.number_input("Primeira coluna de meias-bocas", 1, ncol,
                                         det.col_y_ini + 1)
                    cf = st.number_input("Ultima coluna de meias-bocas", 1, ncol,
                                         det.col_y_fim + 1)
                    lz = st.number_input("Linha com as alturas z (0 = nao existe)", 0, nlin,
                                         (det.lin_z + 1) if det.lin_z is not None else 0)

                n_wl_prev = int(cf - ci + 1)
                z_manual = None
                if lz == 0:
                    st.warning("As alturas z das linhas d'agua nao foram encontradas no "
                               "arquivo. Sem elas a integracao vertical fica sem escala e "
                               "areas, volumes e KB ficam errados. Informe-as abaixo.")
                    mz = st.radio("Como informar as alturas z?",
                                  ["Espacamento uniforme", "Lista de valores"], horizontal=True)
                    if mz == "Espacamento uniforme":
                        cc1, cc2 = st.columns(2)
                        z0 = cc1.number_input("z da primeira linha d'agua (m)", value=0.0,
                                              step=0.1, format="%.4f")
                        dz = cc2.number_input("Espacamento vertical dz (m)", value=0.5,
                                              min_value=0.0001, step=0.1, format="%.4f")
                        z_manual = [z0 + k * dz for k in range(n_wl_prev)]
                        st.caption("z = " + ", ".join(fmt(v, 3) for v in z_manual))
                    else:
                        txt = st.text_input(f"{n_wl_prev} valores separados por ; ou espaco",
                                            value="")
                        vals = [para_float(s) for s in re.split(r"[;,\s]+", txt) if s.strip()]
                        if len(vals) == n_wl_prev and all(np.isfinite(vals)):
                            z_manual = vals
                        elif txt.strip():
                            st.error(f"Foram lidos {len(vals)} valores; sao necessarios "
                                     f"{n_wl_prev}.")

                x_manual = None
                if cx == 0:
                    n_est_prev = int(lf - li + 1)
                    st.warning("Sem coluna X o aplicativo nao conhece as posicoes "
                               "longitudinais das balizas. Elas serao geradas a partir do LPP.")
                    lpp = p.get("LPP") or 0.0
                    if lpp > 0:
                        x_manual = list(np.linspace(0.0, lpp, n_est_prev))
                        st.caption(f"h = LPP / (n_estacoes - 1) = {fmt(lpp/(max(n_est_prev-1,1)))} m")
                    else:
                        st.error("Informe o LPP em 1.1 para gerar as posicoes X.")

                if st.button("✔ Aplicar esta interpretacao", type="primary"):
                    d = Deteccao(ok=True, lin_ini=int(li - 1), lin_fim=int(lf - 1),
                                 col_y_ini=int(ci - 1), col_y_fim=int(cf - 1),
                                 col_x=(int(cx - 1) if cx > 0 else None),
                                 col_id=det.col_id,
                                 lin_z=(int(lz - 1) if lz > 0 else None),
                                 z_valores=det.z_valores)
                    if d.lin_z is not None:
                        num = matriz_numerica(gu)
                        d.z_valores = [num[d.lin_z, c] for c in
                                       range(d.col_y_ini, d.col_y_fim + 1)]
                    x, z, Y, rot = montar_canonico(gu, d, z_manual, x_manual)
                    t = nova_tabela(x, z, Y, rot, opt.get("unidade", "m (metro)"))
                    st.session_state.tab_original = t.copia()
                    st.session_state.tab = t
                    st.session_state.tab_arquivo_df = t.como_df()
                    st.session_state.interp_regs = []
                    registrar("Modulo 1", "Interpretacao da tabela definida manualmente "
                                          "pelo usuario.", nivel="DECISAO", autor="usuario")
                    st.success("Interpretacao aplicada.")
                    rerodar()

            if det.ok and st.session_state.tab is None:
                if st.button("✔ Aceitar a interpretacao automatica", type="primary"):
                    x, z, Y, rot = montar_canonico(gu, det)
                    t = nova_tabela(x, z, Y, rot, opt.get("unidade", "m (metro)"))
                    st.session_state.tab_original = t.copia()
                    st.session_state.tab = t
                    st.session_state.tab_arquivo_df = t.como_df()
                    registrar("Modulo 1", "Interpretacao automatica aceita pelo usuario.",
                              nivel="DECISAO", autor="usuario")
                    rerodar()

    # ---------------- entrada manual ----------------
    else:
        st.caption("A estrutura reproduz a tabela do enunciado: linhas d'agua nas colunas, "
                   "balizas nas linhas, X em coluna propria e meias-bocas nas celulas.")
        c1, c2, c3, c4 = st.columns(4)
        n_est = c1.number_input("Numero de balizas", 3, 200, 11)
        n_wl = c2.number_input("Numero de linhas d'agua", 2, 100, 6)
        lpp_m = c3.number_input("LPP para gerar X (m)", value=float(p.get("LPP") or 40.0),
                                min_value=0.0001, step=0.1, format="%.4f")
        dz_m = c4.number_input("Espacamento vertical dz (m)", value=0.5,
                               min_value=0.0001, step=0.1, format="%.4f")
        if st.button("Criar tabela vazia para preenchimento"):
            x = np.linspace(0.0, lpp_m, int(n_est))
            z = np.array([k * dz_m for k in range(int(n_wl))], float)
            Y = np.full((int(n_est), int(n_wl)), np.nan)
            t = nova_tabela(x, z, Y)
            st.session_state.tab_original = t.copia()
            st.session_state.tab = t
            st.session_state.tab_arquivo_df = t.como_df()
            registrar("Modulo 1", f"Tabela em branco criada manualmente: {n_est} balizas x "
                                  f"{n_wl} linhas d'agua; h = LPP/(n-1) = "
                                  f"{fmt(lpp_m/max(int(n_est)-1,1))} m.", autor="usuario")
            rerodar()

    # ---------------- unidades ----------------
    if st.session_state.tab is not None:
        st.divider()
        st.subheader("1.4 Unidade da tabela de cotas")
        st.caption("Os calculos internos sao sempre feitos no SI (metros). Se a tabela "
                   "estiver em outra unidade, converta aqui.")
        c1, c2 = st.columns([1, 2])
        with c1:
            uni = st.selectbox("Unidade dos valores da tabela", list(UNIDADES.keys()),
                               index=list(UNIDADES.keys()).index(
                                   st.session_state.tab.unidade))
        with c2:
            t = st.session_state.tab
            if np.isfinite(t.Y).any() and np.nanmax(t.Y) > 100:
                st.warning("Valores acima de 100 nas meias-bocas: verifique se a tabela nao "
                           "esta em milimetros. Ler mm como m multiplica o volume por 10^9.")
            if uni != t.unidade:
                st.info(f"Converter de **{t.unidade}** para **{uni}** multiplica x, z e y por "
                        f"{fmt(UNIDADES[t.unidade]/UNIDADES[uni], 6)}. Isso altera todos os "
                        "resultados. Confirme abaixo.")
                if st.button("Confirmar conversao de unidade", type="primary"):
                    antes = t.unidade
                    st.session_state.tab = converter_unidade(t, antes, uni)
                    st.session_state.tab_original = converter_unidade(
                        st.session_state.tab_original, antes, uni)
                    registrar("Modulo 1", "Conversao de unidade da tabela de cotas",
                              nivel="ALTERACAO", antes=antes, novo=uni, autor="usuario",
                              consequencia="Todos os comprimentos, areas, volumes e "
                                           "coeficientes foram reescalados.")
                    rerodar()

        st.subheader("1.5 Selecao dos calculos")
        todas = list(PROPRIEDADES.keys())
        marcar_tudo = st.checkbox("Executar todos os calculos pedidos", value=True)
        if marcar_tudo:
            opt["calculos"] = None
            st.caption("Serao calculadas todas as propriedades: " +
                       ", ".join(PROPRIEDADES[k][0] for k in todas))
        else:
            sel = st.multiselect("Propriedades a calcular",
                                 todas, default=opt.get("calculos") or todas,
                                 format_func=lambda k: PROPRIEDADES[k][0])
            opt["calculos"] = sel
            st.caption(f"{len(sel)} propriedade(s) selecionada(s).")


# ================= PAGINA: MODULO 2 - GEOMETRIA ============================ #

elif pagina == "Modulo 2 - Geometria e validacao":
    st.title("Modulo 2 - Geometria: interpretacao, diagnostico e visualizacao")
    if exige_tabela():
        tab = st.session_state.tab
        p = st.session_state.principais

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Estacoes", tab.n_est)
        c2.metric("Linhas d'agua", tab.n_wl)
        c3.metric("Extensao em x", f"{fmt(tab.x[-1]-tab.x[0], 2)} m")
        c4.metric("Altura coberta", f"{fmt(tab.z[-1]-tab.z[0], 2)} m")

        aba1, aba2, aba3, aba4 = st.tabs(
            ["Tabela de trabalho", "Diagnostico", "Plano de linhas", "Casco 3D"])

        # --- tabela editavel ---
        with aba1:
            st.markdown("#### Tabela de trabalho (editavel)")
            st.caption("Toda celula pode ser alterada. As alteracoes NAO modificam o arquivo "
                       "original e ficam registradas no historico.")
            df = tab.como_df()
            edit = st.data_editor(df, **W(), num_rows="fixed",
                                  key="editor_tabela", height=420)
            if st.button("Aplicar edicoes", type="primary"):
                mudou = 0
                novo_x = np.array([para_float(v) for v in edit["X"]], float)
                for i in range(tab.n_est):
                    if np.isfinite(novo_x[i]) and abs(novo_x[i] - tab.x[i]) > 1e-12:
                        registrar("Modulo 2", f"Posicao X da baliza {tab.rotulos[i]} alterada",
                                  nivel="ALTERACAO", antes=fmt(tab.x[i], 4),
                                  novo=fmt(novo_x[i], 4), autor="usuario",
                                  consequencia="Muda o passo h e todas as integrais "
                                               "longitudinais.")
                        tab.x[i] = novo_x[i]
                        mudou += 1
                cols = [c for c in edit.columns if c.startswith("WL")]
                for j, c in enumerate(cols):
                    vals = np.array([para_float(v) for v in edit[c]], float)
                    for i in range(tab.n_est):
                        a, b = tab.Y[i, j], vals[i]
                        dif = (np.isfinite(a) != np.isfinite(b)) or \
                              (np.isfinite(a) and np.isfinite(b) and abs(a - b) > 1e-12)
                        if dif:
                            registrar("Modulo 2",
                                      f"Meia-boca alterada na baliza {tab.rotulos[i]}, WL{j}",
                                      nivel="ALTERACAO", antes=fmt(a, 4), novo=fmt(b, 4),
                                      autor="usuario",
                                      consequencia="Afeta area seccional, A_WP, volume e "
                                                   "todas as propriedades derivadas.")
                            tab.Y[i, j] = b
                            tab.original[i, j] = False
                            tab.origem[i, j] = "valor informado manualmente pelo usuario"
                            mudou += 1
                st.session_state.tab = tab
                st.success(f"{mudou} alteracao(oes) aplicada(s) e registrada(s).")
                rerodar()

            with st.expander("Comparar com a tabela como foi lida do arquivo"):
                st.dataframe(st.session_state.tab_arquivo_df, **W())

            with st.expander("Origem de cada celula (auditoria)"):
                org = pd.DataFrame(tab.origem, columns=[f"WL{j}" for j in range(tab.n_wl)])
                org.insert(0, "Baliza", tab.rotulos)
                st.dataframe(org, **W())

        # --- diagnostico ---
        with aba2:
            st.markdown("#### Verificacao automatica dos dados")
            st.caption("O aplicativo detecta e explica. Ele nao corrige nada sozinho.")
            achados = diagnosticar(tab, p)
            st.session_state["achados"] = achados
            caixa_achados(achados)

        # --- plano de linhas ---
        with aba3:
            st.markdown("#### Plano de linhas reconstruido a partir da tabela de cotas")
            Tmax = calado_max(tab)
            Tv = st.slider("Calado indicado nos desenhos (m)", 0.0, float(Tmax),
                           float(min(st.session_state.T_sel, Tmax)), step=float(Tmax / 200))
            if np.isfinite(tab.Y).sum() < 4:
                st.warning("Ha poucos valores validos para desenhar o plano de linhas.")
            fig = plot_plano_de_linhas(tab, Tv)
            st.pyplot(fig, **W())
            st.download_button("Baixar plano de linhas (PNG)", fig_para_png(fig),
                               "plano_de_linhas.png", "image/png")
            plt.close(fig)
            st.caption("Compare o desenho com a forma esperada do casco. Formas com bicos, "
                       "cruzamentos ou secoes invertidas indicam erro na tabela de cotas.")

        # --- 3D ---
        with aba4:
            st.markdown("#### Casco 3D simplificado")
            st.warning("Esta **nao** e uma representacao fiel da embarcacao. E apenas a "
                       "superficie que passa pelos pontos da tabela de cotas, sem alisamento. "
                       "Nao substitui software de modelagem naval.")
            c1, c2 = st.columns([1, 3])
            with c1:
                sup = st.checkbox("Mostrar superficie", value=True)
                Tmax = calado_max(tab)
                T3 = st.slider("Plano d'agua (m)", 0.0, float(Tmax),
                               float(min(st.session_state.T_sel, Tmax)),
                               step=float(Tmax / 100), key="t3d")
                exa = st.slider("Exagero visual das escalas y e z", 1.0, 6.0, 1.0, 0.5,
                                help="1,0 mantem a escala real. Valores maiores apenas "
                                     "facilitam a visualizacao; nao alteram nenhum calculo.")
                elev = st.slider("Elevacao da camera", 0, 80, 22)
                azim = st.slider("Rotacao da camera", -180, 180, -125)
            with c2:
                if np.isfinite(tab.Y).all():
                    fig = plot_3d(tab, T3, sup, exa, elev, azim)
                    st.pyplot(fig, **W())
                    plt.close(fig)
                else:
                    st.info("O 3D so e gerado com a tabela completa. Preencha as lacunas "
                            "no Modulo 3.")


# ============= PAGINA: MODULO 3 - INTERPOLACAO E INTEGRACAO ================ #

elif pagina == "Modulo 3 - Interpolacao e integracao":
    st.title("Modulo 3 - Pre-processamento: interpolacao e integracao")
    if exige_tabela():
        tab = st.session_state.tab
        opt = st.session_state.opt

        st.subheader("3.1 Interpolacao")
        faltantes = int((~np.isfinite(tab.Y)).sum())
        if faltantes == 0:
            st.success("Nao ha lacunas: todos os valores da tabela vieram do arquivo ou "
                       "foram informados por voce.")
        else:
            st.warning(f"Ha **{faltantes} celula(s)** sem valor numerico.\n\n"
                       "**Por que a interpolacao e necessaria:** as integrais de area, "
                       "volume e momentos percorrem todas as estacoes e todas as linhas "
                       "d'agua. Um ponto faltante interrompe a integral naquela regiao e "
                       "distorce area seccional, A_WP, volume, LCB, LCF, KB e todas as curvas.\n\n"
                       "**Como sera feito:** interpolacao **linear**. Voce escolhe a hipotese "
                       "para as lacunas nas extremidades. Os valores gerados ficam marcados "
                       "e separados dos originais.")
            c1, c2 = st.columns(2)
            with c1:
                topo = st.radio("Lacunas ACIMA do ultimo valor conhecido (regiao do convés)",
                                ["manter", "zero", "extrapolar"],
                                format_func=lambda k: {
                                    "manter": "Manter a ultima meia-boca (costado vertical)",
                                    "zero": "Assumir zero (casco termina ali)",
                                    "extrapolar": "Extrapolar linearmente a tendencia"}[k])
            with c2:
                base = st.radio("Lacunas ABAIXO do primeiro valor conhecido (regiao do fundo)",
                                ["zero", "manter"],
                                format_func=lambda k: {
                                    "zero": "Assumir zero (o casco nao alcanca esse nivel)",
                                    "manter": "Manter a primeira meia-boca"}[k])
            st.caption("Consequencia: a hipotese do fundo afeta diretamente volume, KB e WSA; "
                       "a hipotese do topo so influencia calados proximos ao pontal.")
            if st.button("Aplicar interpolacao", type="primary"):
                nova, regs = interpolar_tabela(tab, topo, base)
                st.session_state.tab = nova
                st.session_state.interp_regs = regs
                registrar("Modulo 3", f"Interpolacao aplicada: {len(regs)} valor(es) gerado(s) "
                                      f"(topo='{topo}', fundo='{base}').",
                          nivel="ALTERACAO", autor="usuario",
                          consequencia="A tabela usada a partir deste ponto passa a conter "
                                       "valores nao originais, identificados na auditoria.")
                st.success(f"{len(regs)} valor(es) gerado(s).")
                rerodar()

        regs = st.session_state.interp_regs
        if regs:
            st.markdown("#### Detalhamento das interpolacoes")
            st.caption("Metodo, pontos utilizados, posicao interpolada e valor resultante. "
                       "Esta secao fica fora da tabela final, como previsto.")
            st.dataframe(pd.DataFrame(regs), **W(), height=280)
            st.markdown("**Tabela final que sera usada a partir deste momento:**")
            st.dataframe(tab.como_df(), **W(), height=280)
            st.info(f"Dados originais: {int(tab.original.sum())} celulas | "
                    f"Dados gerados: {tab.n_interpolados()} celulas.")

        with st.expander("Discordo de um valor interpolado e quero informar outro"):
            st.caption("Voce pode substituir qualquer valor. O aplicativo avalia a "
                       "consistencia e registra que o valor foi definido por voce.")
            c1, c2, c3 = st.columns(3)
            bi = c1.selectbox("Baliza", list(range(tab.n_est)),
                              format_func=lambda i: f"{i} - {tab.rotulos[i]} (x={fmt(tab.x[i],2)})")
            wj = c2.selectbox("Linha d'agua", list(range(tab.n_wl)),
                              format_func=lambda j: f"WL{j} (z={fmt(tab.z[j],3)})")
            novo = c3.number_input("Novo valor de meia-boca (m)", value=float(
                tab.Y[bi, wj]) if np.isfinite(tab.Y[bi, wj]) else 0.0,
                step=0.01, format="%.5f")
            if st.button("Substituir valor"):
                col = tab.Y[:, wj]
                viz = [v for v in [tab.Y[max(bi - 1, 0), wj], tab.Y[min(bi + 1, tab.n_est - 1), wj]]
                       if np.isfinite(v)]
                if viz and (novo < min(viz) * 0.5 - 1e-9 or novo > max(viz) * 1.5 + 1e-9):
                    st.warning("O valor informado destoa bastante das balizas vizinhas. "
                               "Isso pode gerar uma irregularidade no plano de linhas e um "
                               "salto na curva de areas seccionais. O valor sera usado assim "
                               "mesmo, conforme sua decisao.")
                antes = tab.Y[bi, wj]
                tab.Y[bi, wj] = novo
                tab.original[bi, wj] = False
                tab.origem[bi, wj] = "valor definido pelo usuario (substituiu a interpolacao)"
                st.session_state.tab = tab
                registrar("Modulo 3", f"Valor substituido pelo usuario na baliza "
                                      f"{tab.rotulos[bi]}, WL{wj}",
                          nivel="DECISAO", antes=fmt(antes, 5), novo=fmt(novo, 5),
                          autor="usuario",
                          consequencia="O resultado nesta regiao passa a refletir a decisao "
                                       "do usuario, nao o dado original nem a interpolacao.")
                st.success("Valor substituido e registrado.")
                rerodar()

        with st.expander("Reamostrar as linhas d'agua em malha uniforme (opcional)"):
            st.caption("Util quando o espacamento vertical e irregular e voce quer aplicar "
                       "Simpson em toda a integracao. Introduz erro de interpolacao adicional.")
            n_alvo = st.number_input("Numero de linhas d'agua na nova malha", 3, 201,
                                     max(tab.n_wl, 11), step=2)
            if st.button("Reamostrar"):
                nova, znovo = reamostrar_z(tab, int(n_alvo))
                st.session_state.tab = nova
                registrar("Modulo 3", f"Malha vertical reamostrada para {int(n_alvo)} linhas "
                                      "d'agua uniformes (interpolacao linear).",
                          nivel="ALTERACAO", autor="usuario",
                          consequencia="Permite Simpson em todo o eixo z, mas acrescenta "
                                       "erro de interpolacao aos dados originais.")
                rerodar()

        st.divider()
        st.subheader("3.2 Metodos de integracao")
        st.markdown("Regras implementadas diretamente no codigo, sem biblioteca pronta:")
        c1, c2, c3 = st.columns(3)
        c1.latex(r"\int_a^b f\,dv \approx \frac{h}{2}(f_0+f_1)")
        c1.caption("Trapezio")
        c2.latex(r"\frac{h}{3}(f_0+4f_1+2f_2+\dots+f_n)")
        c2.caption("Simpson 1/3 (n par)")
        c3.latex(r"\frac{3h}{8}(f_0+3f_1+3f_2+f_3)")
        c3.caption("Simpson 3/8 (n multiplo de 3)")

        c1, c2 = st.columns(2)
        opcoes = ["auto", "simpson13", "simpson38", "trapezio"]
        nomes = {"auto": "Automatico (mistura as regras)", "simpson13": "So Simpson 1/3",
                 "simpson38": "So Simpson 3/8", "trapezio": "So Trapezio"}
        with c1:
            opt["metodo_x"] = st.selectbox("Integracao longitudinal (eixo x)", opcoes,
                                           index=opcoes.index(opt.get("metodo_x", "auto")),
                                           format_func=lambda k: nomes[k])
        with c2:
            opt["metodo_z"] = st.selectbox("Integracao vertical (eixo z)", opcoes,
                                           index=opcoes.index(opt.get("metodo_z", "auto")),
                                           format_func=lambda k: nomes[k])

        if opt["metodo_x"] != "auto" or opt["metodo_z"] != "auto":
            st.warning("**Implicacoes de forcar um unico metodo:** Simpson 1/3 exige numero "
                       "par de intervalos e Simpson 3/8 exige multiplo de tres. Quando a "
                       "quantidade nao fecha, o trecho restante e integrado pelo Trapezio e "
                       "isso aparece na auditoria. Forcar o Trapezio em todo o dominio reduz "
                       "a ordem de precisao e tende a subestimar areas de secoes convexas.")

        st.markdown("#### Auditoria da integracao (trechos e regras)")
        px = planejar_integracao(tab.x, opt["metodo_x"])
        pz = planejar_integracao(tab.z, opt["metodo_z"])
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Eixo x (estacoes)**")
            st.code(" ; ".join(f"estacoes {a}-{b}: {m}" for a, b, m in px) or "-")
            st.dataframe(pd.DataFrame([{"Trecho": f"{a}-{b}", "Regra": m,
                                        "x inicial": tab.x[a], "x final": tab.x[b],
                                        "h": (tab.x[b]-tab.x[a])/(b-a)} for a, b, m in px]),
                         **W(), hide_index=True)
        with c2:
            st.markdown("**Eixo z (linhas d'agua)**")
            st.code(" ; ".join(f"WL {a}-{b}: {m}" for a, b, m in pz) or "-")
            st.dataframe(pd.DataFrame([{"Trecho": f"{a}-{b}", "Regra": m,
                                        "z inicial": tab.z[a], "z final": tab.z[b],
                                        "h": (tab.z[b]-tab.z[a])/(b-a)} for a, b, m in pz]),
                         **W(), hide_index=True)
        st.caption("Na malha vertical do calculo o ultimo trecho pode ser um intervalo parcial "
                   "ate o calado escolhido; nesse caso ele aparece como Trapezio na auditoria "
                   "do Modulo 4.")


# ============== PAGINA: MODULO 4 - CALCULO HIDROSTATICO ==================== #

elif pagina == "Modulo 4 - Calculo hidrostatico":
    st.title("Modulo 4 - Propriedades hidrostaticas para um calado")
    if exige_pronta():
        tab = st.session_state.tab
        opt = st.session_state.opt
        Tmax = calado_max(tab)

        st.caption(f"Calado medido a partir da linha de base z = {fmt(z_base(tab))} m. "
                   f"Calado maximo coberto pela tabela: {fmt(Tmax)} m.")
        c1, c2 = st.columns([3, 1])
        with c1:
            T = st.slider("Calado T (m)", 0.01, float(Tmax),
                          float(min(max(st.session_state.T_sel, 0.01), Tmax)),
                          step=float(max(Tmax / 400, 0.001)),
                          help="Arraste livremente para frente e para tras; todos os "
                               "resultados abaixo acompanham o calado escolhido.")
        with c2:
            T = st.number_input("ou digite T (m)", 0.01, float(Tmax), float(T),
                                step=0.01, format="%.4f")
        st.session_state.T_sel = T
        st.info(f"**Calado selecionado: T = {fmt(T)} m** "
                f"(nivel absoluto z = {fmt(z_base(tab)+T)} m)")

        with st.spinner("Calculando..."):
            r = hidrostatica(tab, T, opt)
        st.session_state["r_atual"] = r

        # --- resumo ---
        st.subheader("4.1 Resultados")
        cols = st.columns(6)
        resumo = [("VOL", "∇"), ("DESL", "Δ"), ("AWP", "A_WP"), ("KB", "KB"),
                  ("KMT", "KM_t"), ("TPC", "TPC")]
        for c, (k, rot) in zip(cols, resumo):
            _, uni, casas = PROPRIEDADES[k]
            c.metric(f"{rot} [{uni}]", fmt(r[k], casas))
        cols = st.columns(6)
        resumo2 = [("LCB", "LCB"), ("LCF", "LCF"), ("BMT", "BM_t"),
                   ("BML", "BM_l"), ("CB", "C_B"), ("WSA", "WSA")]
        for c, (k, rot) in zip(cols, resumo2):
            _, uni, casas = PROPRIEDADES[k]
            v = converter_origem(r[k], tab, opt["origem_x"]) if k in ("LCB", "LCF") else r[k]
            c.metric(f"{rot} [{uni}]", fmt(v, casas))
        st.caption(f"LCB e LCF apresentados com {origem_texto(opt)}.")

        df_res = df_resumo_propriedades(r, tab, opt)
        if opt.get("calculos"):
            manter = [PROPRIEDADES[k][0] for k in opt["calculos"]]
            df_res = df_res[df_res["Propriedade"].isin(manter)]
        st.dataframe(df_res, **W(), hide_index=True, height=560)

        # --- aviso do volume ---
        E = r["E_VOL"]
        st.subheader("4.2 Comparacao entre os dois caminhos de volume")
        c1, c2, c3 = st.columns(3)
        c1.metric("∇ longitudinal [m3]", fmt(r["VOL_L"]))
        c2.metric("∇ vertical [m3]", fmt(r["VOL_V"]))
        c3.metric("E∇ [%]", fmt(E, 4))
        if not np.isfinite(E):
            interp = "Nao foi possivel comparar os dois caminhos."
            st.error(interp)
        elif E < 0.5:
            interp = (f"A diferenca de {fmt(E,4)} % entre os dois caminhos e pequena e "
                      "compativel com o erro de discretizacao das duas integracoes. "
                      "Isso indica que a malha de estacoes e de linhas d'agua descreve "
                      "a carena de forma coerente.")
            st.success(interp)
        elif E < 2.0:
            interp = (f"A diferenca de {fmt(E,4)} % e moderada. Ela costuma vir de poucas "
                      "linhas d'agua perto do fundo, de variacao brusca de forma nas "
                      "extremidades ou do trecho parcial ate o calado escolhido. "
                      "Os resultados podem ser usados com a ressalva registrada.")
            st.warning(interp)
        else:
            interp = (f"A diferenca de {fmt(E,4)} % e alta. Os dois caminhos deveriam levar "
                      "ao mesmo volume; uma divergencia desse tamanho aponta para malha "
                      "insuficiente, hipotese inadequada no fundo ou erro na tabela de cotas. "
                      "Deslocamento, KB, BM e todos os coeficientes herdam esse erro.")
            st.error(interp)
            if st.checkbox("Ciente da diferenca de volume, desejo prosseguir", key="ig_evol"):
                txt = f"[VOL-DIF] Diferenca de volume de {fmt(E,4)} % aceita pelo usuario."
                if txt not in st.session_state.avisos_ignorados:
                    st.session_state.avisos_ignorados.append(txt)
                    registrar("Modulo 4", "Usuario decidiu prosseguir com E_vol elevado.",
                              nivel="DECISAO", autor="usuario", novo=f"{fmt(E,4)} %",
                              consequencia="Todas as propriedades derivadas do volume "
                                           "carregam essa incerteza.")
        st.session_state["interp_evol"] = interp

        # --- curva de areas ---
        st.subheader("4.3 Areas seccionais A = A(x)")
        A = r["_vol"]["A"]
        df_areas = pd.DataFrame({
            "Baliza": tab.rotulos,
            "x (m)": [converter_origem(v, tab, opt["origem_x"]) for v in tab.x],
            "A_i (m2)": A})
        c1, c2 = st.columns([1.6, 1])
        with c1:
            fig = plot_areas_seccionais(tab, A, T, opt["origem_x"])
            st.pyplot(fig, **W())
            st.session_state["img_areas"] = fig_para_b64(fig)
        with c2:
            st.dataframe(df_areas, **W(), hide_index=True, height=340)
        st.session_state["df_areas"] = df_areas

        # --- MOSTRAR CALCULO ---
        st.divider()
        st.subheader("4.4 MOSTRAR CALCULO (auditoria de qualquer resultado)")
        st.caption("Selecione uma propriedade para ver: dados utilizados, formula, "
                   "valores intermediarios, resultado e unidade.")
        chave = st.selectbox("Propriedade", list(PROPRIEDADES.keys()),
                             format_func=lambda k: PROPRIEDADES[k][0], index=2)
        rot, uni, casas = PROPRIEDADES[chave]
        v = r["_vol"]
        pw = r["_pw"]

        with st.container(border=True):
            st.markdown(f"### {rot}  [{uni}]")

            if chave in ("VOL_L", "VOL", "LCB"):
                st.markdown("**1. Dados utilizados:** area seccional A(x) de cada baliza, "
                            "no calado selecionado.")
                st.latex(r"\nabla_L=\int A(x)\,dx \approx \sum a_i A_i \qquad "
                         r"LCB=\frac{\int x\,A(x)\,dx}{\nabla}=\frac{\sum a_i A_i x_i}{\nabla}")
                st.markdown("**2. Valores intermediarios:**")
                st.dataframe(v["df_L"], **W(), hide_index=True)
                st.markdown(f"**3. Auditoria da integracao:** `{auditoria_texto(v['aud_L'])}`")
                st.markdown(f"**4. Resultado:** ∇_L = Σ a_i·A_i = **{fmt(v['VOL_L'])} m3**  \n"
                            f"Σ a_i·A_i·x_i = {fmt(np.sum(v['df_L']['a_i * A * x']))} m4  \n"
                            f"LCB = {fmt(np.sum(v['df_L']['a_i * A * x']))} / {fmt(v['VOL_L'])} "
                            f"= **{fmt(converter_origem(v['LCB'], tab, opt['origem_x']))} m** "
                            f"({origem_texto(opt)})")

            elif chave in ("VOL_V", "KB", "E_VOL"):
                st.markdown("**1. Dados utilizados:** area do plano d'agua A_WP em cada "
                            "linha d'agua ate o calado.")
                st.latex(r"\nabla_V=\int_0^T A_{WP}(z)\,dz \qquad "
                         r"KB=VCB=\frac{\int_0^T z\,A_{WP}(z)\,dz}{\nabla_V}")
                st.dataframe(v["df_V"], **W(), hide_index=True)
                st.markdown(f"**Auditoria:** `{auditoria_texto(v['aud_V'])}`")
                st.markdown(f"**Resultado:** ∇_V = **{fmt(v['VOL_V'])} m3** ; "
                            f"KB = {fmt(np.sum(v['df_V']['a_i * A_WP * z']))} / "
                            f"{fmt(v['VOL_V'])} = **{fmt(v['KB'], 4)} m**  \n"
                            f"E∇ = |{fmt(v['VOL_L'])} − {fmt(v['VOL_V'])}| / "
                            f"{fmt(v['VOL_L'])} × 100 = **{fmt(v['E_VOL'], 4)} %**")

            elif chave in ("AWP", "LCF", "IT", "IL", "TPC", "CWP"):
                st.markdown("**1. Dados utilizados:** meia-boca y de cada baliza na altura "
                            "do calado (interpolada verticalmente quando necessario).")
                st.latex(r"A_{WP}=2\int y\,dx \quad LCF=\frac{\int x\cdot 2y\,dx}{A_{WP}}"
                         r"\quad I_t=\frac{2}{3}\int y^3 dx \quad "
                         r"I_l=\int x^2 2y\,dx - A_{WP}\,LCF^2")
                st.dataframe(pw["df"], **W(), hide_index=True)
                st.markdown(f"**Auditoria:** `{auditoria_texto(pw['aud'])}`")
                st.markdown(
                    f"**Resultado:**  \n"
                    f"A_WP = 2 × {fmt(np.sum(pw['df']['a_i * y']))} = **{fmt(r['AWP'])} m2**  \n"
                    f"LCF = {fmt(pw['Mx'])} / {fmt(r['AWP'])} = "
                    f"**{fmt(converter_origem(r['LCF'], tab, opt['origem_x']))} m**  \n"
                    f"I_t = (2/3) × {fmt(np.sum(pw['df']['a_i * y^3']))} = "
                    f"**{fmt(r['IT'])} m4**  \n"
                    f"I_l = {fmt(pw['IL0'])} − {fmt(r['AWP'])} × {fmt(r['LCF'])}² = "
                    f"**{fmt(r['IL'])} m4** ({pw['eixo_IL']})  \n"
                    f"TPC = ρ·A_WP/100 = {fmt(r['rho'],4)} × {fmt(r['AWP'])} / 100 = "
                    f"**{fmt(r['TPC'],4)} t/cm**")

            elif chave == "WSA":
                st.markdown("**1. Dados utilizados:** contorno submerso de cada baliza.")
                st.latex(r"s_i=y_i(z_{base})+\sum\sqrt{\Delta y^2+\Delta z^2}\qquad "
                         r"WSA=2\int s(x)\,dx")
                st.dataframe(r["_wsa_df"], **W(), hide_index=True)
                st.markdown(f"**Resultado:** WSA = **{fmt(r['WSA'])} m2**")
                st.caption("Limitacoes: nao inclui popa espelhada, apendices, leme ou helice; "
                           "a precisao depende do numero de linhas d'agua.")

            elif chave in ("BMT", "KMT", "BML", "KML"):
                st.markdown("**1. Dados utilizados:** momentos de inercia do plano d'agua "
                            "e volume deslocado.")
                st.latex(r"BM_t=\frac{I_t}{\nabla}\;\; KM_t=KB+BM_t\;\;"
                         r"BM_l=\frac{I_l}{\nabla}\;\; KM_l=KB+BM_l")
                st.markdown(
                    f"**2. Valores:** I_t = {fmt(r['IT'])} m4 ; I_l = {fmt(r['IL'])} m4 ; "
                    f"∇ = {fmt(r['VOL'])} m3 ; KB = {fmt(r['KB'],4)} m  \n"
                    f"**3. Resultado:**  \n"
                    f"BM_t = {fmt(r['IT'])} / {fmt(r['VOL'])} = **{fmt(r['BMT'],4)} m**  \n"
                    f"KM_t = {fmt(r['KB'],4)} + {fmt(r['BMT'],4)} = **{fmt(r['KMT'],4)} m**  \n"
                    f"BM_l = {fmt(r['IL'])} / {fmt(r['VOL'])} = **{fmt(r['BML'],4)} m**  \n"
                    f"KM_l = {fmt(r['KB'],4)} + {fmt(r['BML'],4)} = **{fmt(r['KML'],4)} m**")

            elif chave == "DESL":
                st.latex(r"\Delta=\rho\nabla")
                st.markdown(f"Δ = {fmt(r['rho'],4)} t/m3 × {fmt(r['VOL'])} m3 = "
                            f"**{fmt(r['DESL'])} t**")

            elif chave in ("CB", "CM", "CP", "AM", "BWL", "LWL"):
                st.latex(r"C_B=\frac{\nabla}{LBT}\quad C_{WP}=\frac{A_{WP}}{LB}\quad "
                         r"C_M=\frac{A_M}{BT}\quad C_P=\frac{\nabla}{A_M L}")
                st.markdown(
                    f"L = {fmt(r['L_usado'])} m ({opt['L_ref']}) ; B = {fmt(r['B_usado'])} m "
                    f"({opt['B_ref']}) ; T = {fmt(T)} m ; A_M = {fmt(r['AM'])} m2 "
                    f"(baliza {tab.rotulos[r['i_AM']]})  \n"
                    f"C_B = {fmt(r['VOL'])} / ({fmt(r['L_usado'])}×{fmt(r['B_usado'])}×{fmt(T)}) "
                    f"= **{fmt(r['CB'],4)}**  \n"
                    f"C_WP = **{fmt(r['CWP'],4)}** ; C_M = **{fmt(r['CM'],4)}** ; "
                    f"C_P = **{fmt(r['CP'],4)}**  \n"
                    f"Verificacao C_B ≈ C_M·C_P : {fmt(r['CB'],5)} ≈ "
                    f"{fmt(r['CM']*r['CP'],5)}")
                dif = abs(r["CB"] - r["CM"] * r["CP"])
                if np.isfinite(dif) and dif > 1e-4:
                    st.warning(f"Diferenca de {fmt(dif,6)} entre C_B e C_M·C_P. Como as quatro "
                               "definicoes usam o mesmo L, B e T, a identidade deveria ser "
                               "exata; uma diferenca indica inconsistencia nas referencias "
                               "escolhidas. Revise L e B no Modulo 1 ou prossiga ciente disso.")
                else:
                    st.success("Verificacao C_B ≈ C_M·C_P satisfeita.")

            else:  # areas seccionais e demais
                st.markdown("**1. Dados utilizados:** meias-bocas da baliza ao longo de z, "
                            "do fundo ate o calado.")
                st.latex(r"A_i(T)=2\int_0^T y(x_i,z)\,dz \approx 2\sum a_j y_j")
                i = st.selectbox("Baliza para detalhar", list(range(tab.n_est)),
                                 format_func=lambda i: f"{i} - {tab.rotulos[i]} "
                                                       f"(x={fmt(tab.x[i],2)} m)",
                                 key="sel_baliza_calc")
                det = v["det_A"][i]
                c1, c2 = st.columns([1.4, 1])
                with c1:
                    st.dataframe(det["df"], **W(), hide_index=True)
                    st.markdown(f"**Auditoria:** `{auditoria_texto(det['aud'])}`")
                    st.markdown(f"**Resultado:** A = 2 × Σ a_j·y_j = 2 × "
                                f"{fmt(det['meia_area'])} = **{fmt(det['area'])} m2**")
                with c2:
                    fig = plot_secao(tab, i, T)
                    st.pyplot(fig, **W())
                    plt.close(fig)


# ================ PAGINA: MODULO 5 - HYDROSTATIC TABLE ===================== #

elif pagina == "Modulo 5 - Hydrostatic Table":
    st.title("Modulo 5 - Hydrostatic Table")
    if exige_pronta():
        tab = st.session_state.tab
        opt = st.session_state.opt
        p = st.session_state.principais
        Tmax_disp = calado_max(tab)

        st.caption(f"O calculo e repetido automaticamente para T1, T2, ..., Tn. "
                   f"Calado maximo coberto pela tabela de cotas: {fmt(Tmax_disp)} m.")
        c1, c2, c3 = st.columns(3)
        Tmin = c1.number_input("T minimo (m)", 0.001, float(Tmax_disp),
                               float(max(Tmax_disp / 10, 0.001)), step=0.05, format="%.4f")
        Tmax = c2.number_input("T maximo (m)", 0.002, float(Tmax_disp),
                               float(Tmax_disp), step=0.05, format="%.4f")
        dT = c3.number_input("Incremento ΔT (m)", 0.001, float(Tmax_disp),
                             float(max(Tmax_disp / 10, 0.01)), step=0.05, format="%.4f")

        if Tmax > Tmax_disp + 1e-9:
            st.error("O calado maximo pedido ultrapassa a altura coberta pela tabela de cotas. "
                     "Acima do ultimo valor conhecido o casco seria extrapolado e o resultado "
                     "nao teria base nos dados.")
        n_prev = int(np.floor((Tmax - Tmin) / dT + 1e-9)) + 1 if dT > 0 else 0
        st.info(f"Serao calculados **{n_prev} calados**.")

        if st.button("▶ Calcular Hydrostatic Table", type="primary"):
            barra = st.progress(0.0)
            with st.spinner("Executando o calculo para toda a faixa de calados..."):
                df_ht, brutos = tabela_hidrostatica(tab, Tmin, Tmax, dT, opt, barra)
            barra.empty()
            st.session_state.df_ht = df_ht
            st.session_state.brutos_ht = brutos
            st.session_state["ht_params"] = (Tmin, Tmax, dT)
            registrar("Modulo 5", f"Hydrostatic Table calculada para {len(df_ht)} calados "
                                  f"({fmt(Tmin)} a {fmt(Tmax)} m, ΔT = {fmt(dT)} m).",
                      autor="usuario")
            st.success(f"{len(df_ht)} calados calculados.")

        df_ht = st.session_state.df_ht
        if df_ht is not None and len(df_ht):
            mostra = df_ht
            if opt.get("calculos"):
                manter = ["T (calado) [m]"] + [f"{PROPRIEDADES[k][0]} [{PROPRIEDADES[k][1]}]"
                                               for k in opt["calculos"]]
                mostra = df_ht[[c for c in df_ht.columns if c in manter]]
            st.dataframe(mostra.style.format("{:.4f}"), **W(), height=460)

            c1, c2 = st.columns(2)
            with c1:
                xls = excel_hydrostatic_table(
                    df_ht, tab, p, historico_df(),
                    pd.DataFrame(st.session_state.interp_regs))
                st.download_button("⬇ Baixar Hydrostatic Table (.xlsx)", xls,
                                   "hydrostatic_table.xlsx",
                                   "application/vnd.openxmlformats-officedocument."
                                   "spreadsheetml.sheet", **W())
            with c2:
                st.download_button("⬇ Baixar em CSV", df_ht.to_csv(index=False, sep=";",
                                                                   decimal=",").encode("utf-8-sig"),
                                   "hydrostatic_table.csv", "text/csv",
                                   **W())

            st.markdown("#### Verificacao do comportamento das curvas")
            colT = [c for c in df_ht.columns if c.startswith("T (calado)")][0]
            checagens = []
            for chave, esperado in [("VOL", "crescente"), ("DESL", "crescente"),
                                    ("AWP", "nao decrescente"), ("KB", "crescente"),
                                    ("BMT", "-"), ("TPC", "nao decrescente")]:
                col = f"{PROPRIEDADES[chave][0]} [{PROPRIEDADES[chave][1]}]"
                if col not in df_ht.columns:
                    continue
                v = df_ht[col].to_numpy(float)
                d = np.diff(v)
                if esperado == "crescente":
                    ok = np.all(d > -1e-9)
                elif esperado == "nao decrescente":
                    ok = np.all(d > -1e-6 * max(np.nanmax(np.abs(v)), 1))
                else:
                    ok = True
                checagens.append({"Curva": f"T × {PROPRIEDADES[chave][0]}",
                                  "Comportamento esperado": esperado,
                                  "Situacao": "OK" if ok else "INCOERENTE"})
            dfc = pd.DataFrame(checagens)
            st.dataframe(dfc, **W(), hide_index=True)
            if (dfc["Situacao"] == "INCOERENTE").any():
                st.warning("Alguma curva nao segue o comportamento fisico esperado. Isso "
                           "aponta para problema na tabela de cotas (ordem das linhas d'agua, "
                           "valores faltantes ou geometria incoerente) e nao para o metodo de "
                           "integracao. Revise o Modulo 2 antes de usar estes resultados.")
            else:
                st.success("Todas as curvas verificadas seguem o comportamento esperado.")


# ================ PAGINA: MODULO 6 - HYDROSTATIC CURVES ==================== #

elif pagina == "Modulo 6 - Hydrostatic Curves":
    st.title("Modulo 6 - Hydrostatic Curves")
    df_ht = st.session_state.df_ht
    if df_ht is None or not len(df_ht):
        st.warning("Calcule a Hydrostatic Table no **Modulo 5** antes de gerar as curvas.")
    else:
        st.caption("Convencao naval: o calado no eixo vertical.")
        aba1, aba2, aba3 = st.tabs(["Curvas individuais", "Diagrama combinado",
                                    "Consulta numerica"])
        with aba1:
            escolhidas = st.multiselect(
                "Curvas a exibir", CURVAS_OBRIGATORIAS, default=CURVAS_OBRIGATORIAS,
                format_func=lambda k: f"T × {PROPRIEDADES[k][0]}")
            if escolhidas:
                fig = plot_curvas(df_ht, escolhidas)
                st.pyplot(fig, **W())
                st.download_button("⬇ Baixar curvas (PNG)", fig_para_png(fig),
                                   "hydrostatic_curves.png", "image/png")
                st.session_state["img_curvas"] = fig_para_b64(fig)
        with aba2:
            fig = plot_diagrama_combinado(df_ht)
            st.pyplot(fig, **W())
            st.download_button("⬇ Baixar diagrama combinado (PNG)", fig_para_png(fig),
                               "diagrama_hidrostatico.png", "image/png")
            st.session_state["img_combinado"] = fig_para_b64(fig)
            st.caption("Cada curva foi dividida pelo proprio valor maximo para caberem no "
                       "mesmo eixo; o fator de escala aparece na legenda.")
        with aba3:
            st.markdown("#### Consultar numericamente um ponto das curvas")
            colT = [c for c in df_ht.columns if c.startswith("T (calado)")][0]
            Ts = df_ht[colT].to_numpy(float)
            Tq = st.slider("Calado de consulta (m)", float(Ts.min()), float(Ts.max()),
                           float(Ts.mean()), step=float((Ts.max()-Ts.min())/200 or 0.01))
            saida = consultar_curva(df_ht, Tq)
            dfq = pd.DataFrame([{"Propriedade": k, "Valor": v} for k, v in saida.items()])
            st.dataframe(dfq, **W(), hide_index=True, height=520)
            st.caption("Valores obtidos por interpolacao linear entre os calados calculados "
                       "na Hydrostatic Table.")


# ============== PAGINA: MODULO 7 - VALIDACAO E AUDITORIA =================== #

elif pagina == "Modulo 7 - Validacao e auditoria":
    st.title("Modulo 7 - Validacao e auditoria")
    aba1, aba2, aba3, aba4 = st.tabs(
        ["Validacao 1 - analitica", "Validacao 2 - consistencia interna",
         "Validacao 3 - Maxsurf", "Historico completo"])

    # --- validacao analitica ---
    with aba1:
        st.markdown("#### Barcaca paralelepipedica (solucao analitica exata)")
        st.latex(r"\nabla=LBT\quad KB=\frac{T}{2}\quad LCB=LCF=\frac{L}{2}\quad "
                 r"A_{WP}=LB\quad BM_t=\frac{B^2}{12T}\quad C_B=C_M=C_P=C_{WP}=1")
        c1, c2, c3, c4, c5 = st.columns(5)
        Lb = c1.number_input("L (m)", 1.0, 1000.0, 40.0, step=1.0)
        Bb = c2.number_input("B (m)", 0.5, 200.0, 10.0, step=0.5)
        Db = c3.number_input("Pontal (m)", 0.5, 100.0, 5.0, step=0.5)
        Tb = c4.number_input("Calado de teste (m)", 0.1, 99.0, 2.0, step=0.1)
        nb = c5.number_input("Estacoes / WL", 3, 101, 11, step=2)
        if st.button("Executar validacao analitica", type="primary"):
            tb = barcaca_teste(Lb, Bb, Db, int(nb), int(nb))
            optb = dict(st.session_state.opt)
            optb.update({"LPP": Lb, "B": Bb, "L_ref": "LPP", "B_ref": "BWL"})
            rb = hidrostatica(tb, Tb, optb)
            dfv = validacao_analitica(rb, Lb, Bb, Tb, optb["rho"])
            st.session_state["df_val_ana"] = dfv
            registrar("Modulo 7", f"Validacao analitica executada (barcaca {Lb}x{Bb}x{Db} m, "
                                  f"T={Tb} m). Erro maximo: "
                                  f"{fmt(np.nanmax(dfv['Erro (%)']),6)} %.", autor="usuario")
        dfv = st.session_state.get("df_val_ana")
        if dfv is not None:
            st.dataframe(dfv.style.format({"Analitico": "{:.6f}", "Aplicativo": "{:.6f}",
                                           "Erro (%)": "{:.6f}"}),
                         **W(), height=420)
            emax = float(np.nanmax(dfv["Erro (%)"]))
            if emax < 1e-6:
                st.success(f"Erro maximo de {emax:.2e} %. O nucleo de calculo reproduz "
                           "exatamente a solucao analitica.")
            elif emax < 0.5:
                st.success(f"Erro maximo de {fmt(emax,6)} %, dentro do esperado para "
                           "discretizacao.")
            else:
                st.error(f"Erro maximo de {fmt(emax,4)} %. Investigue o metodo de integracao "
                         "ou o numero de estacoes antes de confiar nos resultados.")

    # --- consistencia interna ---
    with aba2:
        st.markdown("#### Consistencia interna no calado selecionado no Modulo 4")
        r = st.session_state.get("r_atual")
        if r is None:
            st.info("Calcule primeiro um calado no Modulo 4.")
        else:
            dfi = verificacoes_internas(r)
            dfi_extra = pd.DataFrame([{
                "Verificacao": "Quantidade de dados interpolados",
                "Esperado": 0, "Obtido": st.session_state.tab.n_interpolados(),
                "Erro absoluto": st.session_state.tab.n_interpolados(),
                "Erro (%)": np.nan, "Unidade": "celulas"}])
            dfi = pd.concat([dfi, dfi_extra], ignore_index=True)
            st.session_state["df_val_int"] = dfi
            st.dataframe(dfi.style.format({"Esperado": "{:.6f}", "Obtido": "{:.6f}",
                                           "Erro absoluto": "{:.6e}", "Erro (%)": "{:.6f}"}),
                         **W(), hide_index=True)
            st.caption("As tres primeiras verificacoes sao identidades algebricas e devem dar "
                       "erro praticamente nulo. A diferenca entre os volumes reflete a "
                       "discretizacao e e a mais informativa sobre a qualidade da malha.")

    # --- maxsurf ---
    with aba3:
        st.markdown("#### Comparacao com software de referencia (Maxsurf)")
        st.latex(r"\text{Erro}=\frac{|X_{app}-X_{Maxsurf}|}{|X_{Maxsurf}|}\times 100")
        st.caption("Informe os valores obtidos no Maxsurf em tres condicoes: calado baixo, "
                   "intermediario e de projeto. O aplicativo calcula os proprios valores nos "
                   "mesmos calados e monta a tabela de erros.")
        if not exige_pronta():
            st.stop()
        tab = st.session_state.tab
        opt = st.session_state.opt
        Tmax_d = calado_max(tab)
        props = ["VOL", "DESL", "LCB", "LCF", "KB", "BMT", "KMT", "AWP", "CB"]
        base = pd.DataFrame({
            "Condicao": ["1 - calado baixo", "2 - intermediario", "3 - de projeto"],
            "T (m)": [round(Tmax_d * 0.3, 3), round(Tmax_d * 0.6, 3),
                      round(float(st.session_state.principais.get("Td") or Tmax_d * 0.9), 3)],
        })
        for k in props:
            base[f"{PROPRIEDADES[k][0]} (Maxsurf)"] = 0.0
        ent = st.data_editor(base, **W(), num_rows="fixed",
                             key="editor_maxsurf")
        if st.button("Comparar com o Maxsurf", type="primary"):
            linhas = []
            for _, lin in ent.iterrows():
                T = float(lin["T (m)"])
                if not (0 < T <= Tmax_d):
                    continue
                r = hidrostatica(tab, T, opt)
                for k in props:
                    ref = float(lin[f"{PROPRIEDADES[k][0]} (Maxsurf)"])
                    if abs(ref) < EPS:
                        continue
                    val = r[k]
                    if k in ("LCB", "LCF"):
                        val = converter_origem(val, tab, opt["origem_x"])
                    linhas.append({"Condicao": lin["Condicao"], "T (m)": T,
                                   "Grandeza": PROPRIEDADES[k][0],
                                   "Aplicativo": val, "Maxsurf": ref,
                                   "Erro (%)": abs(val - ref) / abs(ref) * 100,
                                   "Unidade": PROPRIEDADES[k][1]})
            if linhas:
                dfm = pd.DataFrame(linhas)
                st.session_state.df_val_max = dfm
                registrar("Modulo 7", f"Comparacao com Maxsurf registrada "
                                      f"({len(dfm)} grandezas).", autor="usuario")
            else:
                st.warning("Preencha ao menos um valor de referencia diferente de zero.")
        dfm = st.session_state.df_val_max
        if dfm is not None and len(dfm):
            st.dataframe(dfm.style.format({"Aplicativo": "{:.4f}", "Maxsurf": "{:.4f}",
                                           "Erro (%)": "{:.3f}"}),
                         **W(), hide_index=True)
            st.info("**Como interpretar as diferencas:** discretizacao (numero de estacoes e "
                    "de linhas d'agua), interpolacao linear entre pontos, aproximacao "
                    "geometrica das extremidades, referencia de coordenadas adotada, "
                    "superficie moldada versus externa e o metodo de integracao. Diferencas "
                    "de poucos por cento em volume e em A_WP sao usuais; diferencas grandes "
                    "em LCB ou LCF costumam indicar origem longitudinal diferente.")

    # --- historico ---
    with aba4:
        st.markdown("#### Historico completo")
        st.caption("Data/hora, etapa, acao, valor anterior, valor novo, autor e consequencias.")
        h = historico_df()
        st.dataframe(h, **W(), height=480)
        if st.session_state.avisos_ignorados:
            st.warning("**Avisos ignorados pelo usuario:**\n\n" +
                       "\n".join(f"- {a}" for a in st.session_state.avisos_ignorados))
        st.download_button("⬇ Baixar historico (CSV)",
                           h.to_csv(index=False, sep=";").encode("utf-8-sig"),
                           "historico.csv", "text/csv")


# ==================== PAGINA: RELATORIO FINAL ============================== #

elif pagina == "Relatorio final":
    st.title("Relatorio final")
    st.markdown("Documento unico com **tudo o que foi feito**: dados, interpretacao da "
                "tabela, problemas detectados, decisoes tomadas, interpolacoes, metodos de "
                "integracao, memoria de calculo, graficos, Hydrostatic Table, curvas, "
                "validacoes e historico completo.")

    if exige_tabela():
        tab = st.session_state.tab
        opt = st.session_state.opt
        pronto = np.isfinite(tab.Y).all()

        c1, c2, c3 = st.columns(3)
        c1.metric("Eventos no historico", len(st.session_state.get("hist", [])))
        c2.metric("Celulas interpoladas", tab.n_interpolados())
        c3.metric("Avisos ignorados", len(st.session_state.avisos_ignorados))

        st.divider()
        st.subheader("Conteudo a incluir")
        c1, c2 = st.columns(2)
        with c1:
            inc_linhas = st.checkbox("Plano de linhas", value=True)
            inc_3d = st.checkbox("Casco 3D simplificado", value=True)
        with c2:
            inc_curvas = st.checkbox("Hydrostatic Curves", value=st.session_state.df_ht is not None)
            inc_calc = st.checkbox("Memoria de calculo do calado selecionado", value=True)

        if not pronto:
            st.warning("A tabela ainda tem lacunas. O relatorio sera gerado com o que existe, "
                       "sem as secoes de calculo.")

        if st.button("📄 Gerar relatorio completo", type="primary", **W()):
            with st.spinner("Montando o relatorio..."):
                ctx = {
                    "principais": {**st.session_state.principais,
                                   "densidade rho (t/m3)": opt.get("rho")},
                    "tab": tab, "opt": opt,
                    "unidade_origem": tab.unidade,
                    "origem_txt": origem_texto(opt),
                    "arquivo": st.session_state.arquivo_nome or "(entrada manual)",
                    "aba": st.session_state.aba_sel or "-",
                    "notas_deteccao": (st.session_state.deteccao.notas
                                       if st.session_state.deteccao else []),
                    "tab_original_df": st.session_state.tab_arquivo_df
                                       if st.session_state.tab_arquivo_df is not None
                                       else tab.como_df(),
                    "achados": (st.session_state.get("achados")
                                if st.session_state.get("achados") is not None
                                else diagnosticar(tab, st.session_state.principais)),
                    "avisos_ignorados": st.session_state.avisos_ignorados,
                    "interpolacoes": st.session_state.interp_regs,
                    "aud_x": " ; ".join(f"estacoes {a}-{b}: {m}" for a, b, m in
                                        planejar_integracao(tab.x, opt["metodo_x"])),
                    "aud_z": " ; ".join(f"WL {a}-{b}: {m}" for a, b, m in
                                        planejar_integracao(tab.z, opt["metodo_z"])),
                    "historico": historico_df(),
                    "df_ht": st.session_state.df_ht,
                    "df_val_int": st.session_state.get("df_val_int"),
                    "df_val_ana": st.session_state.get("df_val_ana"),
                    "df_val_max": st.session_state.df_val_max,
                    "interpretacao_evol": st.session_state.get("interp_evol", ""),
                }
                if st.session_state.get("ht_params"):
                    ctx["Tmin"], ctx["Tmax"], ctx["dT"] = st.session_state["ht_params"]

                if pronto and inc_calc:
                    T = st.session_state.T_sel
                    r = st.session_state.get("r_atual")
                    if r is None or abs(r.get("T", -1) - T) > 1e-12:
                        r = hidrostatica(tab, T, opt)
                    ctx["resultado"] = r
                    ctx["LCF_apr"] = converter_origem(r["LCF"], tab, opt["origem_x"])
                    ctx["df_resumo"] = df_resumo_propriedades(r, tab, opt)
                    df_ar = st.session_state.get("df_areas")
                    if df_ar is None or not len(df_ar):
                        df_ar = pd.DataFrame({"Baliza": tab.rotulos, "x (m)": tab.x,
                                              "A_i (m2)": r["_vol"]["A"]})
                    ctx["df_areas"] = df_ar
                    ctx["img_areas"] = st.session_state.get("img_areas") or fig_para_b64(
                        plot_areas_seccionais(tab, r["_vol"]["A"], T, opt["origem_x"]))
                if inc_linhas:
                    ctx["img_linhas"] = fig_para_b64(
                        plot_plano_de_linhas(tab, st.session_state.T_sel if pronto else None))
                if inc_3d and pronto:
                    ctx["img_3d"] = fig_para_b64(plot_3d(tab, st.session_state.T_sel))
                if inc_curvas and st.session_state.df_ht is not None:
                    ctx["img_curvas"] = st.session_state.get("img_curvas") or fig_para_b64(
                        plot_curvas(st.session_state.df_ht))
                    ctx["img_combinado"] = st.session_state.get("img_combinado") or \
                        fig_para_b64(plot_diagrama_combinado(st.session_state.df_ht))

                html = gerar_relatorio(ctx)
                st.session_state["relatorio_html"] = html
                registrar("Relatorio", "Relatorio completo gerado.", autor="usuario")
            st.success("Relatorio gerado.")

        html = st.session_state.get("relatorio_html")
        if html:
            nome = (st.session_state.principais.get("nome") or "embarcacao").replace(" ", "_")
            c1, c2 = st.columns(2)
            c1.download_button("⬇ Baixar relatorio (.html)", html.encode("utf-8"),
                               f"relatorio_hidrostatico_{nome}.html", "text/html",
                               **W(), type="primary")
            if st.session_state.df_ht is not None:
                xls = excel_hydrostatic_table(
                    st.session_state.df_ht, tab, st.session_state.principais,
                    historico_df(), pd.DataFrame(st.session_state.interp_regs))
                c2.download_button("⬇ Baixar Hydrostatic Table (.xlsx)", xls,
                                   "hydrostatic_table.xlsx",
                                   "application/vnd.openxmlformats-officedocument."
                                   "spreadsheetml.sheet", **W())
            st.caption("O arquivo .html abre em qualquer navegador e ja contem os graficos "
                       "embutidos. Para gerar um PDF, abra e use Imprimir → Salvar como PDF.")
            with st.expander("Pre-visualizar o relatorio"):
                st.components.v1.html(html, height=700, scrolling=True)
