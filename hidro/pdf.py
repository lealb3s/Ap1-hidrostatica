# -*- coding: utf-8 -*-
"""
Relatorio final em PDF.

Monta o mesmo conteudo do relatorio HTML usando a biblioteca reportlab, que e
Python puro e nao exige nada instalado no sistema operacional. Assim o download
em PDF funciona igual no computador e no Streamlit Cloud.
"""

import io
import base64

import numpy as np
import pandas as pd

from .base import *          # noqa: F401,F403
from .hidrostatica import *  # noqa: F401,F403


def pdf_disponivel() -> bool:
    try:
        import reportlab  # noqa: F401
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------

def _estilos():
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib import colors

    e = getSampleStyleSheet()
    e.add(ParagraphStyle("Titulo", parent=e["Title"], fontSize=20, spaceAfter=4 * mm,
                         textColor=colors.HexColor("#20465e")))
    e.add(ParagraphStyle("Sub", parent=e["Normal"], fontSize=9,
                         textColor=colors.HexColor("#5a6b78"), spaceAfter=6 * mm))
    e.add(ParagraphStyle("H1", parent=e["Heading1"], fontSize=14, spaceBefore=7 * mm,
                         spaceAfter=2.5 * mm, textColor=colors.HexColor("#20465e")))
    e.add(ParagraphStyle("H2", parent=e["Heading2"], fontSize=11, spaceBefore=4 * mm,
                         spaceAfter=1.5 * mm, textColor=colors.HexColor("#2c6382")))
    e.add(ParagraphStyle("Texto", parent=e["Normal"], fontSize=9, leading=13,
                         spaceAfter=2 * mm))
    e.add(ParagraphStyle("Nota", parent=e["Normal"], fontSize=8, leading=11,
                         textColor=colors.HexColor("#5a6b78"), spaceAfter=2 * mm))
    e.add(ParagraphStyle("Celula", parent=e["Normal"], fontSize=6.5, leading=8.5,
                         textColor=colors.HexColor("#1a1a1a")))
    e.add(ParagraphStyle("CelulaCab", parent=e["Normal"], fontSize=6.5, leading=8.5,
                         textColor=colors.white))
    return e


def _tabela_pdf(df: pd.DataFrame, larg_total, casas=4, max_linhas=40, fonte=6.5):
    """Converte um DataFrame em uma tabela do reportlab, com colunas proporcionais."""
    from reportlab.platypus import Table, TableStyle, Paragraph
    from reportlab.lib import colors

    if df is None or len(df) == 0:
        return None
    d = df.head(max_linhas).copy()
    for c in d.columns:
        if pd.api.types.is_numeric_dtype(d[c]):
            d[c] = d[c].map(lambda v: fmt(v, casas))
        else:
            d[c] = d[c].astype(str).str.slice(0, 90)

    est = _estilos()
    cabecalho = [Paragraph(f"<b>{str(c)[:40]}</b>", est["CelulaCab"]) for c in d.columns]
    corpo = [[Paragraph(str(v), est["Celula"]) for v in linha] for linha in d.values]
    dados = [cabecalho] + corpo

    n = len(d.columns)
    larguras = [larg_total / n] * n
    t = Table(dados, colWidths=larguras, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#20465e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#c8d6e0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#f4f8fa")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
    ]))
    return t


def _imagem_pdf(b64: str, larg_max, alt_max=None):
    """
    Insere uma figura codificada em base64, preservando a proporcao.
    A altura tambem e limitada: uma figura mais alta que a area util da pagina
    faz o reportlab abortar a montagem inteira do documento.
    """
    from reportlab.platypus import Image
    from reportlab.lib.utils import ImageReader
    if not b64:
        return None
    dados = io.BytesIO(base64.b64decode(b64))
    larg, alt = ImageReader(dados).getSize()
    escala = min(larg_max / larg, 1.0)
    if alt_max:
        escala = min(escala, alt_max / alt)
    dados.seek(0)
    return Image(dados, width=larg * escala, height=alt * escala)


# ---------------------------------------------------------------------------

def gerar_relatorio_pdf(ctx: dict) -> bytes:
    """Monta o relatorio completo em PDF e devolve os bytes do arquivo."""
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                    PageBreak, KeepTogether)

    est = _estilos()
    buf = io.BytesIO()
    pagina = landscape(A4)
    margem = 14 * mm
    larg = pagina[0] - 2 * margem

    principais = ctx["principais"]
    tab = ctx["tab"]
    opt = ctx["opt"]
    nome = principais.get("nome") or "(sem nome)"

    def rodape(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColorRGB(0.4, 0.45, 0.5)
        canvas.drawString(margem, 9 * mm,
                          f"{APP_NOME} v{APP_VERSAO}  |  {nome}  |  {agora()}")
        canvas.drawRightString(pagina[0] - margem, 9 * mm, f"pagina {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(buf, pagesize=pagina, leftMargin=margem, rightMargin=margem,
                            topMargin=13 * mm, bottomMargin=15 * mm,
                            title=f"Relatorio hidrostatico - {nome}",
                            author=APP_NOME)
    E = []
    A = E.append

    def titulo(txt):
        A(Paragraph(txt, est["H1"]))

    def sub(txt):
        A(Paragraph(txt, est["H2"]))

    def texto(txt, estilo="Texto"):
        A(Paragraph(txt, est[estilo]))

    def tabela(df, casas=4, max_linhas=40):
        t = _tabela_pdf(df, larg, casas, max_linhas)
        if t is not None:
            A(t)
            A(Spacer(1, 3 * mm))
            if df is not None and len(df) > max_linhas:
                texto(f"(exibindo as primeiras {max_linhas} de {len(df)} linhas; "
                      "a lista completa esta no relatorio em HTML e no arquivo Excel)",
                      "Nota")
        else:
            texto("(sem registros)", "Nota")

    alt_util = pagina[1] - 30 * mm

    def figura(chave, largura=0.92, altura=0.82):
        img = _imagem_pdf(ctx.get(chave), larg * largura, alt_util * altura)
        if img is not None:
            A(Spacer(1, 2 * mm))
            A(img)
            A(Spacer(1, 3 * mm))

    # ---- capa -------------------------------------------------------------
    A(Paragraph("Relatorio de Calculo Hidrostatico", est["Titulo"]))
    texto(f"<b>Embarcacao:</b> {nome} &nbsp;&nbsp; <b>Emitido em:</b> {agora()} "
          f"&nbsp;&nbsp; <b>Aplicativo:</b> {APP_NOME} v{APP_VERSAO}", "Sub")
    texto("<b>Aviso de responsabilidade.</b> Este aplicativo trabalha com uma "
          "representacao geometrica simplificada, obtida por interpolacao de uma tabela "
          "de cotas discreta. Ele pode cometer erros e nao substitui software de "
          "modelagem naval avancada. Todos os resultados devem ser conferidos. As "
          "alteracoes feitas dentro do aplicativo nao modificam o arquivo importado.")

    # ---- 1. dados principais ---------------------------------------------
    titulo("1. Dados principais da embarcacao")
    tabela(pd.DataFrame([{"Grandeza": k, "Valor": v} for k, v in principais.items()]))
    texto(f"<b>Unidade da tabela de cotas:</b> {ctx.get('unidade_origem','-')} &nbsp;&nbsp; "
          f"<b>Calculos internos:</b> SI (metros) &nbsp;&nbsp; "
          f"<b>Densidade:</b> {fmt(opt.get('rho'), 4)} t/m3")
    texto(f"<b>Referencia longitudinal:</b> {ctx.get('origem_txt','-')} &nbsp;&nbsp; "
          f"<b>Linha de base:</b> z = {fmt(z_base(tab))} m "
          "(o calado T e medido a partir dela)")

    # ---- 2. arquivo e interpretacao --------------------------------------
    titulo("2. Arquivo de origem e interpretacao da tabela")
    texto(f"<b>Arquivo:</b> {ctx.get('arquivo','(entrada manual)')} &nbsp;&nbsp; "
          f"<b>Aba:</b> {ctx.get('aba','-')}")
    for n in ctx.get("notas_deteccao", []):
        texto(f"- {n}", "Nota")
    texto(f"<b>Balizas:</b> {tab.n_est} &nbsp;&nbsp; "
          f"<b>Linhas d'agua:</b> {tab.n_wl} &nbsp;&nbsp; "
          f"<b>Comprimento:</b> {fmt(abs(tab.x[-1]-tab.x[0]))} m &nbsp;&nbsp; "
          f"<b>Altura coberta:</b> {fmt(tab.z[-1]-tab.z[0])} m")
    sub("2.1 Tabela de trabalho utilizada nos calculos")
    tabela(tab.como_df(), 4, 30)
    texto(f"Celulas vindas do arquivo: {int(tab.original.sum())} &nbsp;&nbsp; "
          f"Celulas geradas por interpolacao ou hipotese: {tab.n_interpolados()}")

    # ---- 3. diagnostico ---------------------------------------------------
    A(PageBreak())
    titulo("3. Diagnostico da geometria")
    ach = ctx.get("achados", [])
    if not ach:
        texto("Nenhum problema detectado nas verificacoes automaticas.")
    else:
        tabela(pd.DataFrame([{"Codigo": a.codigo, "Nivel": a.nivel, "Problema": a.titulo,
                              "Onde": a.onde, "Consequencias": a.consequencia}
                             for a in ach]), 4, 20)
    if ctx.get("avisos_ignorados"):
        sub("Avisos que o usuario decidiu ignorar")
        for i in ctx["avisos_ignorados"]:
            texto(f"- {i}", "Nota")

    # ---- 4. interpolacao --------------------------------------------------
    titulo("4. Interpolacao")
    regs = ctx.get("interpolacoes", [])
    if not regs:
        texto("Nenhuma interpolacao foi necessaria: todos os valores vieram do arquivo.")
    else:
        texto(f"Foram gerados {len(regs)} valores por interpolacao linear. Dados originais "
              "e gerados sao mantidos separados.")
        tabela(pd.DataFrame(regs), 4, 25)

    # ---- 5. metodos -------------------------------------------------------
    titulo("5. Metodos de integracao")
    texto("Regras implementadas diretamente no codigo: Trapezio, Simpson 1/3 e Simpson 3/8. "
          "A escolha automatica aplica Simpson 1/3 em numero par de intervalos, Simpson 3/8 "
          "nos tres primeiros quando o numero e impar, e Trapezio nos trechos de passo "
          "variavel.")
    texto(f"<b>Auditoria longitudinal:</b> {ctx.get('aud_x','-')}")
    texto(f"<b>Auditoria vertical:</b> {ctx.get('aud_z','-')}")
    if ctx.get("df_aud_calado") is not None:
        sub("Regras aplicadas em cada calado")
        tabela(ctx["df_aud_calado"], 3, 30)

    # ---- 6. calculo detalhado --------------------------------------------
    r = ctx.get("resultado")
    if r:
        A(PageBreak())
        titulo(f"6. Calculo detalhado para o calado T = {fmt(r['T'])} m")
        sub("6.1 Areas seccionais")
        tabela(ctx.get("df_areas"), 4, 30)
        figura("img_areas")
        sub("6.2 Plano d'agua, LCF e momentos de inercia")
        tabela(r["_pw"]["df"], 5, 30)
        texto(f"A_WP = <b>{fmt(r['AWP'])} m2</b> &nbsp;&nbsp; "
              f"LCF = <b>{fmt(ctx.get('LCF_apr', r['LCF']))} m</b> &nbsp;&nbsp; "
              f"I_t = <b>{fmt(r['IT'])} m4</b> &nbsp;&nbsp; "
              f"I_l = <b>{fmt(r['IL'])} m4</b> ({r['_pw']['eixo_IL']})")
        A(PageBreak())
        sub("6.3 Volume pelo caminho longitudinal")
        tabela(r["_vol"]["df_L"], 5, 30)
        sub("6.4 Volume pelo caminho vertical")
        tabela(r["_vol"]["df_V"], 5, 30)
        texto(f"Vol_L = <b>{fmt(r['VOL_L'])} m3</b> &nbsp;&nbsp; "
              f"Vol_V = <b>{fmt(r['VOL_V'])} m3</b> &nbsp;&nbsp; "
              f"E_vol = <b>{fmt(r['E_VOL'], 4)} %</b> &nbsp;&nbsp; "
              f"Volume adotado: {opt.get('volume_adotado')} = {fmt(r['VOL'])} m3")
        if ctx.get("interpretacao_evol"):
            texto(ctx["interpretacao_evol"], "Nota")
        sub("6.5 Superficie molhada")
        texto("Metodo do semi-perimetro molhado. Nao inclui popa espelhada, apendices, "
              "leme nem helice.")
        texto(f"WSA = <b>{fmt(r['WSA'])} m2</b>")
        A(PageBreak())
        sub("6.6 Resumo das propriedades no calado selecionado")
        tabela(ctx.get("df_resumo"), 5, 40)
        sub("6.7 Memoria de calculo das propriedades derivadas")
        texto(
            f"BM_t = I_t / Vol = {fmt(r['IT'])} / {fmt(r['VOL'])} = <b>{fmt(r['BMT'],4)} m</b><br/>"
            f"KM_t = KB + BM_t = {fmt(r['KB'],4)} + {fmt(r['BMT'],4)} = <b>{fmt(r['KMT'],4)} m</b><br/>"
            f"BM_l = I_l / Vol = <b>{fmt(r['BML'],4)} m</b> &nbsp;&nbsp; "
            f"KM_l = <b>{fmt(r['KML'],4)} m</b><br/>"
            f"Delta = rho x Vol = {fmt(r['rho'],4)} x {fmt(r['VOL'])} = <b>{fmt(r['DESL'])} t</b><br/>"
            f"TPC = rho x A_WP / 100 = <b>{fmt(r['TPC'],4)} t/cm</b><br/>"
            f"C_B = Vol / (L B T) = {fmt(r['VOL'])} / ({fmt(r['L_usado'])} x "
            f"{fmt(r['B_usado'])} x {fmt(r['T'])}) = <b>{fmt(r['CB'],4)}</b><br/>"
            f"C_WP = <b>{fmt(r['CWP'],4)}</b> &nbsp;&nbsp; C_M = <b>{fmt(r['CM'],4)}</b> "
            f"&nbsp;&nbsp; C_P = <b>{fmt(r['CP'],4)}</b>")

    # ---- 7. geometria -----------------------------------------------------
    if ctx.get("img_linhas") or ctx.get("img_3d"):
        A(PageBreak())
        titulo("7. Representacao geometrica")
        if ctx.get("img_linhas"):
            sub("Plano de linhas reconstruido a partir da tabela de cotas")
            figura("img_linhas", 0.99)
        if ctx.get("img_3d"):
            sub("Casco 3D simplificado")
            figura("img_3d", 0.80)
            texto("Superficie aproximada construida apenas com os pontos da tabela de "
                  "cotas, sem alisamento. Nao representa fielmente o casco.", "Nota")

    # ---- 8 e 9. tabela e curvas ------------------------------------------
    if ctx.get("df_ht") is not None and len(ctx["df_ht"]):
        A(PageBreak())
        titulo("8. Hydrostatic Table")
        if ctx.get("Tmin") is not None:
            texto(f"Calados de {fmt(ctx.get('Tmin'))} m a {fmt(ctx.get('Tmax'))} m, "
                  f"com passo de {fmt(ctx.get('dT'))} m.")
        tabela(ctx["df_ht"], 4, 45)
    if ctx.get("img_curvas"):
        A(PageBreak())
        titulo("9. Hydrostatic Curves")
        figura("img_curvas", 0.99)
    if ctx.get("img_combinado"):
        titulo("Diagrama hidrostatico combinado")
        figura("img_combinado", 0.75)

    # ---- 10. validacao ----------------------------------------------------
    A(PageBreak())
    titulo("10. Validacao")
    if ctx.get("df_val_int") is not None:
        sub("10.1 Consistencia interna")
        tabela(ctx["df_val_int"], 6, 20)
    if ctx.get("df_val_ana") is not None:
        sub("10.2 Validacao analitica")
        tabela(ctx["df_val_ana"], 6, 20)
    if ctx.get("df_val_max") is not None:
        sub("10.3 Comparacao com software de referencia")
        tabela(ctx["df_val_max"], 4, 30)

    # ---- 11. historico ----------------------------------------------------
    A(PageBreak())
    titulo("11. Historico completo (auditoria)")
    texto("Registro cronologico do que foi detectado, alterado e decidido, com o autor "
          "de cada acao.")
    tabela(ctx.get("historico"), 4, 60)

    # ---- 12. limitacoes ---------------------------------------------------
    titulo("12. Limitacoes conhecidas")
    for lim in [
        "A geometria e reconstruida por interpolacao linear entre pontos discretos: "
        "quanto menos balizas e linhas d'agua, maior o erro de discretizacao.",
        "As regras de Simpson exigem passo constante; em trechos irregulares o "
        "aplicativo usa o Trapezio, o que fica registrado na auditoria.",
        "A superficie molhada nao inclui popa espelhada, apendices, leme nem helice.",
        "O volume abaixo da primeira linha d'agua e acima da ultima depende da hipotese "
        "escolhida pelo usuario.",
        "O modelo 3D e ilustrativo e nao substitui software de modelagem naval.",
    ]:
        texto(f"- {lim}", "Nota")

    doc.build(E, onFirstPage=rodape, onLaterPages=rodape)
    return buf.getvalue()
