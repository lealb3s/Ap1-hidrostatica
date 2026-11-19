# -*- coding: utf-8 -*-
"""
Etapa 2: tabela de cotas.

Importa o arquivo, mostra o que entendeu, deixa corrigir a interpretacao e
completa as lacunas. Esta e a tela que garante que qualquer embarcacao seja
processada sem alterar o codigo-fonte.
"""

import re
import numpy as np
import pandas as pd
import streamlit as st

import hidro as H
from .comum import W, rerodar, botao_proximo, tem_tabela, principais


def _guardar(t, arquivo=None):
    st.session_state.tab = t
    st.session_state.tab_original = t.copia()
    st.session_state.tab_arquivo_df = t.como_df()
    st.session_state.interp_regs = []
    st.session_state.achados = None
    st.session_state.df_ht = None
    if arquivo:
        st.session_state.arquivo_nome = arquivo


def _alturas_manuais(n, prefixo="", dz_padrao=1.0):
    """Widgets para informar as alturas z quando o arquivo nao as traz ou traz erradas."""
    modo = st.radio("Como informar as alturas?",
                    ["Espacamento uniforme", "Digitar a lista"],
                    horizontal=True, key=f"modo_z_{prefixo}")
    if modo == "Espacamento uniforme":
        c1, c2 = st.columns(2)
        z0 = c1.number_input("Altura da primeira linha d'agua (m)", value=0.0,
                             step=0.1, format="%.4f", key=f"z0_{prefixo}")
        dz = c2.number_input("Espacamento vertical entre linhas d'agua (m)",
                             value=float(dz_padrao), min_value=0.0001, step=0.1,
                             format="%.4f", key=f"dz_{prefixo}")
        z = [z0 + k * dz for k in range(n)]
        st.caption(f"{n} alturas: " + "; ".join(H.fmt(v, 3) for v in z) +
                   f"  |  altura total {H.fmt(z[-1] - z[0])} m")
        return z
    txt = st.text_input(f"{n} valores separados por ; ou espaco", key=f"lz_{prefixo}")
    vals = [H.para_float(s) for s in re.split(r"[;,\s]+", txt) if s.strip()]
    if txt.strip() and (len(vals) != n or not all(np.isfinite(vals))):
        st.error(f"Foram lidos {len(vals)} valores validos; sao necessarios {n}.")
        return None
    if not txt.strip():
        return None
    st.caption("Altura total " + H.fmt(vals[-1] - vals[0]) + " m")
    return vals


# ---------------------------------------------------------------------------
# 2.1  importar o arquivo
# ---------------------------------------------------------------------------

def _importar():
    st.subheader("Enviar o arquivo")
    st.caption("O arquivo original nunca e alterado: o aplicativo trabalha sobre uma copia.")

    up = st.file_uploader("Tabela de cotas", type=["xlsx", "xlsm", "xls", "csv", "txt", "tsv"],
                          key=f"upl_{st.session_state.uploader_id}",
                          label_visibility="collapsed")
    if up is None:
        st.caption("Formatos aceitos: .xlsx, .xlsm, .xls, .csv, .txt e .tsv.")
        return

    if st.session_state.arquivo_nome != up.name or st.session_state.abas is None:
        try:
            st.session_state.abas = H.ler_arquivo_bruto(up)
            st.session_state.arquivo_nome = up.name
            st.session_state.aba_sel = list(st.session_state.abas.keys())[0]
            H.registrar("Etapa 2", f"Arquivo '{up.name}' importado.", autor="usuario",
                        consequencia="O arquivo original permanece intacto.")
        except Exception as e:
            st.error(f"Nao foi possivel ler o arquivo: {e}")
            st.session_state.abas = None
            return

    abas = st.session_state.abas
    if len(abas) > 1:
        st.session_state.aba_sel = st.selectbox(
            "Aba da planilha", list(abas.keys()),
            index=list(abas.keys()).index(st.session_state.aba_sel))
    aba = st.session_state.aba_sel
    g0 = H.limpar_grade(abas[aba])

    with st.expander(f"Ver o conteudo bruto da aba '{aba}' "
                     f"({g0.shape[0]} linhas x {g0.shape[1]} colunas)"):
        st.dataframe(g0, **W())

    longo = H.detectar_formato_longo(g0)
    det, gu, transp = H.detectar_melhor(g0)
    st.session_state.grade, st.session_state.deteccao = gu, det
    st.session_state.transposta = transp

    st.divider()
    st.subheader("O que o aplicativo entendeu")

    if longo is not None:
        st.info("O arquivo parece estar no formato simples de tres colunas (x, z, y).")
        if st.button("Usar essa leitura", type="primary"):
            x, z, Y = longo
            _guardar(H.nova_tabela(x, z, Y), up.name)
            H.registrar("Etapa 2", "Tabela lida no formato de tres colunas (x, z, y).",
                        autor="programa")
            rerodar()

    if not det.ok:
        st.error("Nao consegui identificar a estrutura sozinho. Use o painel abaixo para "
                 "indicar onde estao os dados.")
    else:
        n_est = det.lin_fim - det.lin_ini + 1
        n_wl = det.col_y_fim - det.col_y_ini + 1
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Balizas", n_est)
        c2.metric("Linhas d'agua", n_wl)
        c3.metric("Coluna do X", det.col_x + 1 if det.col_x is not None else "nenhuma")
        c4.metric("Linha das alturas z", det.lin_z + 1 if det.lin_z is not None else "nenhuma")

        if det.z_valores:
            alt = det.z_valores[-1] - det.z_valores[0]
            st.markdown("**Alturas das linhas d'agua lidas:** " +
                        "; ".join(H.fmt(v, 3) for v in det.z_valores))
            st.markdown(f"**Altura total coberta pela tabela: {H.fmt(alt)} m**")
            D = principais().get("D") or 0.0
            Td = principais().get("Td") or 0.0
            suspeito = (alt <= 1e-9
                        or (D > 0 and (alt < 0.3 * D or alt > 3 * D))
                        or (Td > 0 and alt < Td))
            if suspeito:
                st.error(
                    "**Essas alturas nao combinam com a embarcacao.** A altura total da "
                    f"tabela ({H.fmt(alt)} m) nao bate com o pontal ({H.fmt(D)} m) nem com "
                    f"o calado de projeto ({H.fmt(Td)} m) informados na etapa 1.\n\n"
                    "**O que acontece se voce seguir assim:** o calado maximo do aplicativo "
                    "fica limitado a essa altura, a Hydrostatic Table sai com pouquissimas "
                    "linhas ou apenas uma, e as curvas nao tem como ser tracadas.\n\n"
                    "**Provavel causa:** a linha apontada acima nao e a das alturas. "
                    "Corrija a linha no painel abaixo, ou informe as alturas na mao.")
            else:
                st.success("As alturas lidas sao coerentes com as dimensoes informadas.")
        else:
            st.warning("As alturas das linhas d'agua nao foram encontradas no arquivo. "
                       "Sem elas a integracao vertical fica sem escala e areas, volumes e "
                       "KB saem errados.")
            z_sug, expl = H.alturas_sugeridas(
                gu, n_wl, principais().get("Td") or None)
            if z_sug:
                st.success(
                    f"**Encontrei uma pista no proprio arquivo:** {expl}.\n\n"
                    f"Alturas propostas: " + "; ".join(H.fmt(v, 3) for v in z_sug) +
                    f"  |  altura total {H.fmt(z_sug[-1] - z_sug[0])} m")
                if st.button("Usar estas alturas e carregar a tabela", type="primary"):
                    x, z, Y, rot = H.montar_canonico(gu, det, z_manual=z_sug)
                    _guardar(H.nova_tabela(x, z, Y, rot), up.name)
                    H.registrar("Etapa 2", "Alturas das linhas d'agua obtidas do cabecalho "
                                           f"da planilha ({expl}).", nivel="DECISAO",
                                autor="usuario", novo=f"z de {H.fmt(z_sug[0])} a "
                                                      f"{H.fmt(z_sug[-1])} m",
                                consequencia="Define a escala vertical de toda a "
                                             "integracao e a faixa de calados possivel.")
                    rerodar()
            else:
                st.caption("Informe as alturas no painel abaixo.")

        for n in det.notas:
            st.caption(f"- {n}")

        pistas = H.pistas_cabecalho(gu)
        NOMES = {"lpp": "LPP - entre perpendiculares", "loa": "LOA - comprimento total",
                 "comprimento": "comprimento (tipo nao identificado)",
                 "boca": "boca B", "pontal": "pontal D", "calado": "calado de projeto Td"}
        uteis = {k: v for k, v in pistas.items() if k in NOMES}
        if uteis:
            with st.expander("O arquivo tambem traz os dados principais do navio"):
                st.dataframe(pd.DataFrame(
                    [{"Grandeza": NOMES[k], "Rotulo na planilha": onde, "Valor": v}
                     for k, (v, onde) in uteis.items()]), hide_index=True, **W())

                # o LPP e o que entra nos coeficientes; o LOA NAO serve para isso
                if "lpp" in uteis:
                    origem_lpp = ("lpp", "o proprio LPP encontrado na planilha")
                elif "comprimento" in uteis:
                    origem_lpp = ("comprimento", "um comprimento generico da planilha")
                elif "loa" in uteis:
                    origem_lpp = ("loa", "o COMPRIMENTO TOTAL, que nao e o LPP")
                else:
                    origem_lpp = (None, "")

                if origem_lpp[0] == "lpp":
                    st.caption(f"O LPP sera preenchido com {H.fmt(uteis['lpp'][0])} m.")
                elif origem_lpp[0] is not None:
                    st.warning(
                        f"A planilha nao traz o LPP explicitamente. O campo seria "
                        f"preenchido com {H.fmt(uteis[origem_lpp[0]][0])} m, que e "
                        f"{origem_lpp[1]}. O LPP costuma ser menor que o comprimento "
                        "total, e usar o valor errado reduz C_B, C_P e C_WP na mesma "
                        "proporcao. Confira na etapa 1 antes de calcular.")

                if st.button("Preencher a etapa 1 com estes valores"):
                    p = principais()
                    for k, destino in {"boca": "B", "pontal": "D", "calado": "Td"}.items():
                        if k in uteis:
                            p[destino] = float(uteis[k][0])
                    if origem_lpp[0] is not None:
                        p["LPP"] = float(uteis[origem_lpp[0]][0])
                    H.registrar("Etapa 2", "Dados principais preenchidos a partir do "
                                           "cabecalho da planilha.", autor="usuario",
                                novo=f"LPP = {H.fmt(p.get('LPP'))} m ({origem_lpp[1]})",
                                consequencia="O LPP entra em C_B, C_P e C_WP.")
                    st.success("Dados do navio preenchidos. Confira na etapa 1.")
                    rerodar()

    # ---- painel de ajuste manual -----------------------------------------
    aberto = (not det.ok) or (not det.z_valores)
    with st.expander("Corrigir a interpretacao", expanded=aberto):
        st.caption("Tudo o que o aplicativo detectou pode ser mudado aqui. E assim que uma "
                   "tabela de cotas desconhecida e processada sem alterar o codigo-fonte.")

        nova_or = st.radio("Orientacao",
                           ["Linhas d'agua nas COLUNAS (balizas nas linhas)",
                            "Linhas d'agua nas LINHAS (balizas nas colunas)"],
                           index=1 if transp else 0)
        quer = nova_or.startswith("Linhas d'agua nas LINHAS")
        if quer != transp:
            base = H.limpar_grade(abas[aba])
            gu = H.limpar_grade(base.T.reset_index(drop=True)) if quer else base
            gu.columns = range(gu.shape[1])
            det = H.detectar_layout(gu)
            st.session_state.grade, st.session_state.deteccao = gu, det
            st.session_state.transposta = quer

        nlin, ncol = gu.shape
        c1, c2 = st.columns(2)
        with c1:
            li = st.number_input("Primeira linha de dados", 1, nlin, min(det.lin_ini + 1, nlin))
            lf = st.number_input("Ultima linha de dados", 1, nlin, min(det.lin_fim + 1, nlin))
            cx = st.number_input("Coluna das posicoes X (0 = nao existe)", 0, ncol,
                                 (det.col_x + 1) if det.col_x is not None else 0)
        with c2:
            ci = st.number_input("Primeira coluna de meias-bocas", 1, ncol,
                                 min(det.col_y_ini + 1, ncol))
            cf = st.number_input("Ultima coluna de meias-bocas", 1, ncol,
                                 min(det.col_y_fim + 1, ncol))
            lz = st.number_input("Linha das alturas z (0 = nao existe)", 0, nlin,
                                 (det.lin_z + 1) if det.lin_z is not None else 0)

        n_wl_prev = int(cf - ci + 1)
        n_est_prev = int(lf - li + 1)

        z_manual = None
        if lz > 0:
            num = H.matriz_numerica(gu)
            lidos = [num[int(lz - 1), c] for c in range(int(ci - 1), int(cf))]
            if all(np.isfinite(lidos)):
                st.caption("Alturas na linha indicada: " +
                           "; ".join(H.fmt(v, 3) for v in lidos) +
                           f"  |  altura total {H.fmt(lidos[-1] - lidos[0])} m")
            else:
                st.warning("A linha indicada nao contem alturas numericas em todas as "
                           "colunas de meias-bocas.")
        st.markdown("**Alturas das linhas d'agua**")
        usar_manual = st.checkbox("Informar as alturas na mao em vez de ler da planilha",
                                  value=(lz == 0))
        if usar_manual:
            z_sug, _expl = H.alturas_sugeridas(
                gu, n_wl_prev, principais().get("Td") or None)
            dz_pad = (z_sug[1] - z_sug[0]) if (z_sug and len(z_sug) > 1) else 1.0
            z_manual = _alturas_manuais(n_wl_prev, "ajuste", dz_pad)

        x_manual = None
        if cx == 0:
            st.warning("Sem coluna X o aplicativo nao conhece as posicoes das balizas.")
            lpp = principais().get("LPP") or 0.0
            if lpp > 0:
                x_manual = list(np.linspace(0.0, lpp, n_est_prev))
                st.caption(f"Serao geradas a partir do LPP: h = LPP/(n-1) = "
                           f"{H.fmt(lpp / max(n_est_prev - 1, 1))} m")
            else:
                st.error("Informe o LPP na etapa 1 para gerar as posicoes X.")

        pronto = (not usar_manual or z_manual is not None) and (cx > 0 or x_manual is not None)
        if st.button("Aplicar esta interpretacao", type="primary", disabled=not pronto):
            d = H.Deteccao(ok=True, lin_ini=int(li - 1), lin_fim=int(lf - 1),
                           col_y_ini=int(ci - 1), col_y_fim=int(cf - 1),
                           col_x=(int(cx - 1) if cx > 0 else None), col_id=det.col_id,
                           lin_z=(int(lz - 1) if lz > 0 else None))
            if d.lin_z is not None and z_manual is None:
                num = H.matriz_numerica(gu)
                d.z_valores = [num[d.lin_z, c] for c in range(d.col_y_ini, d.col_y_fim + 1)]
            x, z, Y, rot = H.montar_canonico(gu, d, z_manual, x_manual)
            _guardar(H.nova_tabela(x, z, Y, rot), up.name)
            H.registrar("Etapa 2", "Interpretacao da tabela definida pelo usuario.",
                        nivel="DECISAO", autor="usuario",
                        novo=f"{len(x)} balizas x {len(z)} linhas d'agua, "
                             f"altura total {H.fmt(z[-1] - z[0])} m")
            rerodar()

    if det.ok and det.z_valores and not tem_tabela():
        if st.button("Aceitar a leitura automatica", type="primary", **W()):
            x, z, Y, rot = H.montar_canonico(gu, det)
            _guardar(H.nova_tabela(x, z, Y, rot), up.name)
            H.registrar("Etapa 2", "Leitura automatica aceita pelo usuario.",
                        nivel="DECISAO", autor="usuario")
            rerodar()


# ---------------------------------------------------------------------------
# 2.2  ajustes sobre a tabela ja carregada
# ---------------------------------------------------------------------------

def _ajustes():
    tab = st.session_state.tab
    p = principais()

    alerta = H.coerencia_alturas(tab, p)
    if alerta:
        st.error(f"**Atencao as alturas das linhas d'agua:** {alerta}.\n\n"
                 "Com esses valores o calado maximo do aplicativo fica limitado a "
                 f"{H.fmt(H.calado_max(tab))} m e a Hydrostatic Table sai praticamente "
                 "vazia. Corrija abaixo antes de seguir.")

    a1, a2, a3, a4 = st.tabs(["Alturas e posicoes", "Unidade", "Lacunas",
                              "Tabela de trabalho"])

    # --- alturas e posicoes ------------------------------------------------
    with a1:
        st.markdown("**Alturas das linhas d'agua em uso**")
        st.caption("; ".join(H.fmt(v, 3) for v in tab.z) +
                   f"   |   altura total {H.fmt(tab.z[-1] - tab.z[0])} m")
        if st.checkbox("Substituir as alturas", value=bool(alerta)):
            z_novo = _alturas_manuais(tab.n_wl, "troca")
            if z_novo is not None and st.button("Aplicar novas alturas", type="primary"):
                antes = f"{H.fmt(tab.z[0])} a {H.fmt(tab.z[-1])}"
                st.session_state.tab = H.aplicar_alturas(tab, z_novo)
                H.registrar("Etapa 2", "Alturas das linhas d'agua substituidas.",
                            nivel="ALTERACAO", antes=antes,
                            novo=f"{H.fmt(z_novo[0])} a {H.fmt(z_novo[-1])}",
                            autor="usuario",
                            consequencia="Muda a faixa de calados, as areas seccionais, "
                                         "o volume, KB e todas as curvas.")
                st.session_state.df_ht = None
                rerodar()

        st.divider()
        st.markdown("**Posicoes longitudinais das balizas**")
        st.caption(f"de {H.fmt(tab.x[0])} m a {H.fmt(tab.x[-1])} m   |   "
                   f"comprimento {H.fmt(abs(tab.x[-1] - tab.x[0]))} m")
        if st.checkbox("Gerar as posicoes a partir do LPP"):
            lpp = st.number_input("LPP (m)", value=float(p.get("LPP") or 0.0),
                                  min_value=0.0001, step=0.1, format="%.4f")
            x_novo = list(np.linspace(0.0, lpp, tab.n_est))
            st.caption(f"h = LPP/(n-1) = {H.fmt(lpp / max(tab.n_est - 1, 1))} m")
            if st.button("Aplicar novas posicoes", type="primary"):
                st.session_state.tab = H.aplicar_posicoes(tab, x_novo)
                H.registrar("Etapa 2", "Posicoes X geradas a partir do LPP.",
                            nivel="ALTERACAO", novo=f"0 a {H.fmt(lpp)} m", autor="usuario",
                            consequencia="Muda o passo h e todas as integrais longitudinais.")
                st.session_state.df_ht = None
                rerodar()

        st.divider()
        desordenada = not (np.all(np.diff(tab.x) > 0) and np.all(np.diff(tab.z) > 0))
        if desordenada:
            st.warning("Ha balizas ou linhas d'agua fora de ordem crescente, ou repetidas. "
                       "Integrais podem sair negativas ou perder trechos.")
            if st.button("Ordenar e remover repetidas"):
                nova, (dx, dz) = H.remover_duplicatas(tab)
                st.session_state.tab = nova
                H.registrar("Etapa 2", f"Tabela reordenada; {dx} baliza(s) e {dz} linha(s) "
                                       "d'agua repetidas removidas.", nivel="ALTERACAO",
                            autor="usuario",
                            consequencia="Os dados removidos nao entram mais em nenhum calculo.")
                rerodar()
        else:
            st.caption("Balizas e linhas d'agua estao em ordem crescente, sem repeticoes.")

    # --- unidade -----------------------------------------------------------
    with a2:
        st.caption("Os calculos internos sao sempre em metros. Se a tabela veio em outra "
                   "unidade, converta aqui.")
        uni = st.selectbox("Unidade dos valores da tabela", list(H.UNIDADES.keys()),
                           index=list(H.UNIDADES.keys()).index(tab.unidade))
        if np.isfinite(tab.Y).any() and np.nanmax(tab.Y) > 100:
            st.warning("Meias-bocas acima de 100 na unidade atual: verifique se a tabela nao "
                       "esta em milimetros.")
        if uni != tab.unidade:
            f = H.UNIDADES[tab.unidade] / H.UNIDADES[uni]
            st.info(f"Converter de {tab.unidade} para {uni} multiplica x, z e y por "
                    f"{H.fmt(f, 6)}. Isso muda todos os resultados.")
            if st.button("Confirmar conversao", type="primary"):
                antes = tab.unidade
                st.session_state.tab = H.converter_unidade(tab, antes, uni)
                st.session_state.tab_original = H.converter_unidade(
                    st.session_state.tab_original, antes, uni)
                H.registrar("Etapa 2", "Unidade da tabela convertida.", nivel="ALTERACAO",
                            antes=antes, novo=uni, autor="usuario",
                            consequencia="Comprimentos, areas, volumes e coeficientes "
                                         "foram reescalados.")
                st.session_state.df_ht = None
                rerodar()

    # --- lacunas -----------------------------------------------------------
    with a3:
        falta = int((~np.isfinite(tab.Y)).sum())
        if falta == 0:
            st.success("Nao ha lacunas: todos os valores vieram do arquivo ou foram "
                       "informados por voce.")
        else:
            st.warning(
                f"Ha **{falta} celula(s)** sem valor numerico.\n\n"
                "As integrais percorrem todas as balizas e todas as linhas d'agua. "
                "Um ponto faltante interrompe a integral naquela regiao e distorce area "
                "seccional, A_WP, volume, LCB, LCF, KB e as curvas.")
            c1, c2 = st.columns(2)
            with c1:
                topo = st.radio("Lacunas acima do ultimo valor conhecido",
                                ["manter", "zero", "extrapolar"],
                                format_func=lambda k: {
                                    "manter": "Repetir a ultima meia-boca (costado vertical)",
                                    "zero": "Assumir zero (o casco termina ali)",
                                    "extrapolar": "Seguir a tendencia (extrapolar)"}[k])
            with c2:
                base = st.radio("Lacunas abaixo do primeiro valor conhecido",
                                ["zero", "manter"],
                                format_func=lambda k: {
                                    "zero": "Assumir zero (o casco nao chega a esse nivel)",
                                    "manter": "Repetir a primeira meia-boca"}[k])
            st.caption("A hipotese do fundo afeta volume, KB e superficie molhada; a do topo "
                       "so influencia calados proximos ao pontal.")
            if st.button("Completar por interpolacao linear", type="primary"):
                nova, regs = H.interpolar_tabela(tab, topo, base)
                st.session_state.tab = nova
                st.session_state.interp_regs = regs
                H.registrar("Etapa 2", f"Interpolacao aplicada: {len(regs)} valor(es) gerado(s) "
                                       f"(topo '{topo}', fundo '{base}').",
                            nivel="ALTERACAO", autor="usuario",
                            consequencia="A tabela passa a conter valores nao originais, "
                                         "identificados na auditoria.")
                rerodar()

        regs = st.session_state.interp_regs
        if regs:
            st.markdown("**Valores gerados** (metodo, pontos usados, posicao e resultado)")
            st.dataframe(pd.DataFrame(regs), **W())
            st.caption(f"Originais do arquivo: {int(tab.original.sum())} celulas  |  "
                       f"gerados: {tab.n_interpolados()} celulas.")

    # --- tabela editavel ---------------------------------------------------
    with a4:
        st.caption("Toda celula pode ser corrigida. As mudancas nao alteram o arquivo "
                   "original e ficam registradas no historico.")
        edit = st.data_editor(tab.como_df(), num_rows="fixed", key="editor_cotas",
                              height=420, **W())
        if st.button("Aplicar edicoes", type="primary"):
            mudou = 0
            novo_x = np.array([H.para_float(v) for v in edit["X"]], float)
            for i in range(tab.n_est):
                if np.isfinite(novo_x[i]) and abs(novo_x[i] - tab.x[i]) > 1e-12:
                    H.registrar("Etapa 2", f"Posicao X da baliza {tab.rotulos[i]} alterada",
                                nivel="ALTERACAO", antes=H.fmt(tab.x[i], 4),
                                novo=H.fmt(novo_x[i], 4), autor="usuario",
                                consequencia="Muda o passo h e as integrais longitudinais.")
                    tab.x[i] = novo_x[i]
                    mudou += 1
            cols = [c for c in edit.columns if c.startswith("WL")]
            for j, c in enumerate(cols):
                vals = np.array([H.para_float(v) for v in edit[c]], float)
                for i in range(tab.n_est):
                    a, b = tab.Y[i, j], vals[i]
                    dif = (np.isfinite(a) != np.isfinite(b)) or \
                          (np.isfinite(a) and np.isfinite(b) and abs(a - b) > 1e-12)
                    if dif:
                        H.registrar("Etapa 2",
                                    f"Meia-boca alterada na baliza {tab.rotulos[i]}, WL{j}",
                                    nivel="ALTERACAO", antes=H.fmt(a, 4), novo=H.fmt(b, 4),
                                    autor="usuario",
                                    consequencia="Afeta area seccional, A_WP, volume e "
                                                 "as propriedades derivadas.")
                        tab.Y[i, j] = b
                        tab.original[i, j] = False
                        tab.origem[i, j] = "valor informado manualmente pelo usuario"
                        mudou += 1
            st.session_state.tab = tab
            st.session_state.df_ht = None
            st.success(f"{mudou} alteracao(oes) aplicada(s) e registrada(s).")
            rerodar()

        with st.expander("Comparar com a tabela como foi lida do arquivo"):
            st.dataframe(st.session_state.tab_arquivo_df, **W())
        with st.expander("Origem de cada celula"):
            org = pd.DataFrame(tab.origem, columns=[f"WL{j}" for j in range(tab.n_wl)])
            org.insert(0, "Baliza", tab.rotulos)
            st.dataframe(org, **W())


def render():
    st.title("2. Tabela de cotas")
    if tem_tabela():
        tab = st.session_state.tab
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Balizas", tab.n_est)
        c2.metric("Linhas d'agua", tab.n_wl)
        c3.metric("Comprimento", f"{H.fmt(abs(tab.x[-1] - tab.x[0]), 2)} m")
        c4.metric("Altura coberta", f"{H.fmt(tab.z[-1] - tab.z[0], 2)} m")
        _ajustes()
        with st.expander("Enviar outro arquivo"):
            _importar()
        botao_proximo("3. Conferir a geometria")
    else:
        _importar()
