# -*- coding: utf-8 -*-
"""Regras de integracao numerica implementadas diretamente: Trapezio,
Simpson 1/3 e Simpson 3/8, com planejamento por trecho e auditoria."""

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


def auditoria_texto(aud) -> str:
    """
    Auditoria no formato pedido pelo enunciado:
        "estacoes 0-2: Simpson 1/3 ; estacoes 2-5: Simpson 3/8 ; estacoes 5-6: Trapezio"
    """
    return " ; ".join(f"{a['Trecho']}: {a['Regra']}" for a in aud) if aud else "-"
