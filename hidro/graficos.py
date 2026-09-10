# -*- coding: utf-8 -*-
"""Graficos: plano de linhas, body plan, linhas d'agua, linhas de alto,
casco 3D, areas seccionais e curvas hidrostaticas."""

import io
import re
import base64
import datetime as _dt
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401

from .base import *          # noqa: F401,F403
from .tabela import *        # noqa: F401,F403
from .hidrostatica import *  # noqa: F401,F403


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
    # a legenda vai para FORA: num casco longo esta vista fica baixa e estreita,
    # e a legenda por dentro cobre justamente as curvas das extremidades
    if ax.get_legend_handles_labels()[0]:
        ax.legend(fontsize=6, loc="center left", bbox_to_anchor=(1.01, 0.5),
                  frameon=True, borderpad=0.4)
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
    def _dim2(v, minimo=1e-6):
        v = abs(float(v)) if np.isfinite(v) else 0.0
        return v if v > minimo else minimo

    Lx = _dim2(tab.x[-1] - tab.x[0])
    Ly = _dim2(2 * np.nanmax(Y) if np.isfinite(Y).any() else 0.0) * max(exagero, 1e-6)
    Lz = _dim2(tab.z[-1] - tab.z[0]) * max(exagero, 1e-6)
    try:
        ax.set_box_aspect((Lx, Ly, Lz))
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
    colT = coluna_calado(df)
    if colT is None:
        raise ValueError("A tabela nao tem coluna de calado: refaca a Hydrostatic Table.")
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


def _fator_bonito(v: float) -> float:
    """Arredonda para o 1, 2 ou 5 vezes potencia de dez mais proximo por cima."""
    if not np.isfinite(v) or v <= 0:
        return 1.0
    e = np.floor(np.log10(v))
    m = v / 10 ** e
    for c in (1, 2, 5):
        if m <= c:
            return float(c * 10 ** e)
    return float(10 ** (e + 1))


def plot_diagrama_combinado(df: pd.DataFrame, chaves=None, separacao=28.0):
    """
    Diagrama hidrostatico combinado na convencao naval classica.

    Cada curva e dividida por um fator de escala e deslocada horizontalmente, e
    ambos aparecem na legenda no formato usual: "Vol (m3) [1:1000] +0".

    Por que nao normalizar pelo maximo: grandezas proporcionais entre si ficariam
    exatamente sobrepostas e sumiriam do desenho. Delta = rho x Vol e
    TPC = rho x A_WP / 100, entao esses pares dariam a MESMA curva normalizada e
    o leitor veria menos linhas do que a legenda promete. Com escala e
    deslocamento independentes, cada grandeza ocupa a sua propria faixa.
    """
    chaves = chaves or CURVAS_OBRIGATORIAS
    colT = coluna_calado(df)
    if colT is None:
        raise ValueError("A tabela nao tem coluna de calado: refaca a Hydrostatic Table.")
    T = df[colT].to_numpy(float)

    fig, ax = plt.subplots(figsize=(12.0, 7.4))
    cmap = plt.get_cmap("tab20")
    k = 0
    for chave in chaves:
        rot, uni, _ = PROPRIEDADES[chave]
        col = f"{rot} [{uni}]"
        if col not in df.columns:
            continue
        v = df[col].to_numpy(float)
        bons = np.isfinite(v)
        if bons.sum() < 2:
            continue
        vmin, vmax = float(np.nanmin(v)), float(np.nanmax(v))
        faixa = vmax - vmin
        if faixa <= EPS:
            faixa = max(abs(vmax), 1.0)
        esc = _fator_bonito(faixa / 100.0)
        vp = v / esc
        desloc = k * separacao - float(np.nanmin(vp))
        desloc = round(desloc / 5.0) * 5.0
        ax.plot(vp + desloc, T, lw=1.7, color=cmap(k % 20),
                label=f"{rot} [{uni}]  [1:{esc:g}] {desloc:+.0f}")
        k += 1

    ax.set_xlabel("valor de cada grandeza dividido pela sua escala e deslocado "
                  "(ver legenda)", fontsize=9)
    ax.set_ylabel("Calado T (m)", fontsize=10)
    ax.set_title("Diagrama hidrostatico combinado", fontsize=12, fontweight="bold")
    ax.grid(True, ls=":", lw=0.6)
    ax.legend(fontsize=7, loc="center left", bbox_to_anchor=(1.01, 0.5),
              frameon=True, title="grandeza  [1:escala] deslocamento",
              title_fontsize=7.5)
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


# ---------------------------------------------------------------------------
# S8.1 - CASCO 3D INTERATIVO
# ---------------------------------------------------------------------------

def plot_3d_interativo(tab: Tabela, T=None, superficie=True, exagero=1.0,
                       mostrar_balizas=True, mostrar_linhas=True):
    """
    Mesmo casco do `plot_3d`, mas em Plotly: o usuario gira, aproxima e desloca
    a vista com o mouse, dentro da propria tela, sem depender de sliders.

    Devolve None quando o Plotly nao esta instalado, para que a interface possa
    cair no desenho estatico do matplotlib.
    """
    try:
        import plotly.graph_objects as go
    except ImportError:
        return None

    Y = np.nan_to_num(tab.Y, nan=0.0)
    X, Z = np.meshgrid(tab.x, tab.z, indexing="ij")
    fig = go.Figure()

    if superficie:
        for lado in (1.0, -1.0):
            fig.add_trace(go.Surface(
                x=X, y=lado * Y, z=Z, showscale=False, opacity=0.85,
                colorscale=[[0, "#3d6f8e"], [1, "#a8cadd"]], surfacecolor=Z,
                hovertemplate="x %{x:.3f} m<br>y %{y:.3f} m<br>z %{z:.3f} m<extra></extra>"))

    if mostrar_balizas:
        for i in range(tab.n_est):
            for lado in (1.0, -1.0):
                fig.add_trace(go.Scatter3d(
                    x=np.full(tab.n_wl, tab.x[i]), y=lado * Y[i], z=tab.z,
                    mode="lines", line=dict(color="#16394f", width=3),
                    showlegend=False, hoverinfo="skip"))
    if mostrar_linhas:
        for j in range(tab.n_wl):
            for lado in (1.0, -1.0):
                fig.add_trace(go.Scatter3d(
                    x=tab.x, y=lado * Y[:, j], z=np.full(tab.n_est, tab.z[j]),
                    mode="lines", line=dict(color="#16394f", width=2),
                    opacity=0.55, showlegend=False, hoverinfo="skip"))

    if T is not None and T > 0:
        nivel = z_base(tab) + T
        ymax = float(np.nanmax(Y)) * 1.15 + 1e-6
        xx, yy = np.meshgrid([float(tab.x[0]), float(tab.x[-1])], [-ymax, ymax])
        fig.add_trace(go.Surface(
            x=xx, y=yy, z=np.full_like(xx, nivel, dtype=float), showscale=False,
            opacity=0.25, colorscale=[[0, COR_AGUA], [1, COR_AGUA]],
            name="linha d'agua", hoverinfo="skip"))

    # As proporcoes da caixa 3D precisam ser numeros positivos e finitos. Um casco
    # com x em ordem decrescente da comprimento negativo; uma tabela toda zerada da
    # largura nula; e ambos fazem o Plotly recusar a figura inteira. Aqui cada
    # dimensao e saneada antes de virar proporcao.
    def _dim(v, minimo=1e-6):
        v = abs(float(v)) if np.isfinite(v) else 0.0
        return v if v > minimo else minimo

    Lx = _dim(tab.x[-1] - tab.x[0])
    Ly = _dim(2 * np.nanmax(Y) if np.isfinite(Y).any() else 0.0) * max(exagero, 1e-6)
    Lz = _dim(tab.z[-1] - tab.z[0]) * max(exagero, 1e-6)
    maior = max(Lx, Ly, Lz)
    # nenhuma dimensao some por completo: abaixo de 5 % a figura fica ilegivel
    prop = {k: min(max(v / maior, 0.05), 1.0) for k, v in
            (("x", Lx), ("y", Ly), ("z", Lz))}
    fig.update_layout(
        scene=dict(
            xaxis_title="x (m)", yaxis_title="y (m)", zaxis_title="z (m)",
            aspectmode="manual", aspectratio=prop,
            camera=dict(eye=dict(x=1.6, y=-1.5, z=0.9)),
        ),
        margin=dict(l=0, r=0, t=10, b=0), height=620,
        paper_bgcolor="rgba(0,0,0,0)")
    return fig
