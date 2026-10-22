# -*- coding: utf-8 -*-
"""Constantes, utilitarios de numero e texto, unidades e registro de auditoria.
Nao depende de nenhum outro modulo do pacote."""

import io
import re
import base64
import datetime as _dt
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st


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
    "T":      ("T moldado",                  "m",    3),
    "T_EXT":  ("T extremo",                  "m",    3),
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
    "KG":     ("KG (informado)",             "m",    4),
    "GMT":    ("GM_t",                       "m",    4),
    "GML":    ("GM_l",                       "m",    4),
    "MTC":    ("MTC",                        "t.m/cm", 4),
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

# Curvas de estabilidade. So existem quando o KG e informado, porque KG depende da
# distribuicao de pesos a bordo e nao pode ser obtido da tabela de cotas.
CURVAS_ESTABILIDADE = ["GMT", "GML", "MTC"]


# ============================================================================ #
# S1 - UTILITARIOS                                                             #
# ============================================================================ #

def agora() -> str:
    return _dt.datetime.now().strftime("%d/%m/%Y %H:%M:%S")


_TOKEN_NUM = re.compile(r"[-+]?\d[\d.,]*(?:[eE][-+]?\d+)?")


def para_float(v: Any) -> float:
    """
    Converte qualquer celula para float, aceitando:
      - virgula decimal brasileira  (1,25  ->  1.25)
      - separador de milhar         (1.234,56 -> 1234.56  /  1,234.56 -> 1234.56)
      - texto com rotulo junto      ("1,50 m" -> 1.50 ; "WL 2.5" -> 2.5 ; "L.A 11" -> 11)
      - marcadores de vazio         ("-", "n/a", "" -> NaN)

    O numero e EXTRAIDO por expressao regular, nunca obtido apagando as letras.
    Apagar letras ja causou um erro grave: em "L.A 11" sobrava "..11", o ponto de
    "L.A" era lido como separador decimal e o rotulo virava 0,11 em vez de 11.
    """
    if v is None or isinstance(v, bool):
        return np.nan
    if isinstance(v, (int, float, np.integer, np.floating)):
        f = float(v)
        return f if np.isfinite(f) else np.nan

    s = str(v).strip().replace("\u00a0", " ")
    if s.lower() in NULOS:
        return np.nan

    achados = _TOKEN_NUM.findall(s)
    if not achados:
        return np.nan
    # o ultimo numero do texto e o que costuma carregar o valor
    # ("Espacamento T/10 = 0,91" -> 0,91 e nao 10)
    s = achados[-1].strip(".,")
    if s in ("", "-", "+"):
        return np.nan

    tem_v, tem_p = ("," in s), ("." in s)
    if tem_v and tem_p:
        # o separador que aparece por ULTIMO e o decimal
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif tem_v:
        s = s.replace(",", ".")          # virgula sozinha: decimal brasileiro

    if s.count(".") > 1:                 # sobraram pontos: eram milhares
        cabeca, _, cauda = s.rpartition(".")
        s = cabeca.replace(".", "") + "." + cauda

    try:
        f = float(s)
        return f if np.isfinite(f) else np.nan
    except ValueError:
        return np.nan


def numero_puro(v: Any) -> bool:
    """
    True quando a celula e um numero de verdade, e nao um rotulo que contem numero.
    "9,1" e numero puro; "L.A 11" e rotulo. Essa distincao evita que uma linha de
    rotulos seja confundida com a linha das alturas das linhas d'agua.
    """
    if v is None or isinstance(v, bool):
        return False
    if isinstance(v, (int, float, np.integer, np.floating)):
        return bool(np.isfinite(float(v)))
    s = str(v).strip()
    if not s or s.lower() in NULOS:
        return False
    if re.search(r"[A-Za-z]", s):
        return False
    return np.isfinite(para_float(s))


def sao_indices(vals) -> bool:
    """
    True quando a sequencia e apenas numeracao (0,1,2,... ou 1,2,3,...) e nao alturas.
    Rotulos como 'L.A 00' ate 'L.A 11' caem aqui: numeram as linhas d'agua, mas nao
    dizem a que altura cada uma esta.
    """
    v = np.asarray(vals, float)
    if len(v) < 3 or not np.all(np.isfinite(v)):
        return False
    if not np.allclose(v, np.round(v)):
        return False
    return bool(np.allclose(np.diff(v), 1.0) and (abs(v[0]) < 1e-9 or abs(v[0] - 1) < 1e-9))


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


def coluna_calado(df) -> str | None:
    """
    Nome da coluna de calado numa Hydrostatic Table, ou None se nao houver.

    Aceita tambem o rotulo antigo "T (calado)": uma tabela guardada na sessao do
    navegador pode ter sido calculada por uma versao anterior do programa, e nesse
    caso o certo e pedir um novo calculo, nunca quebrar a tela.
    """
    if df is None or not hasattr(df, "columns"):
        return None
    for prefixo in ("T moldado", "T (calado)"):
        for c in df.columns:
            if str(c).startswith(prefixo):
                return c
    for c in df.columns:                      # ultimo recurso: qualquer coluna "T ..."
        if str(c).startswith("T "):
            return c
    return None
