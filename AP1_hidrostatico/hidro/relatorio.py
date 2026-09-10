# -*- coding: utf-8 -*-
"""Relatorio HTML autocontido e exportacao para Excel."""

import io
import re
import base64
import datetime as _dt
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st

from .base import *          # noqa: F401,F403
from .hidrostatica import *  # noqa: F401,F403


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
