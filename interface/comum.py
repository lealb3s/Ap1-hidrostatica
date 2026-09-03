# -*- coding: utf-8 -*-
"""Estado da sessao, barra lateral e atalhos compartilhados pelas telas."""

import numpy as np
import pandas as pd
import streamlit as st

import hidro as H


PAGINAS = ["Inicio",
           "1. Dados do navio",
           "2. Tabela de cotas",
           "3. Conferir a geometria",
           "4. Metodos de calculo",
           "5. Resultados no calado",
           "6. Tabela e curvas",
           "7. Validacao",
           "Relatorio final"]


def W(esticar: bool = True) -> dict:
    """Argumento de largura compativel com versoes novas e antigas do Streamlit."""
    try:
        v = tuple(int(p) for p in st.__version__.split(".")[:2])
    except Exception:
        v = (99, 99)
    if v >= (1, 49):
        return {"width": "stretch" if esticar else "content"}
    return {"use_container_width": bool(esticar)}


PADRAO = {
    "hist": [],
    "uploader_id": 0,
    "abas": None, "aba_sel": None, "grade": None, "deteccao": None,
    "transposta": False, "arquivo_nome": None,
    "tab_original": None, "tab": None, "tab_arquivo_df": None,
    "interp_regs": [], "avisos_ignorados": [], "achados": None,
    "df_ht": None, "brutos_ht": None, "df_val_max": None,
    "df_val_int": None, "df_val_ana": None,
    "principais": {"nome": "", "LPP": 0.0, "B": 0.0, "D": 0.0, "Td": 0.0},
    "opt": {"rho": 1.025, "metodo_x": "auto", "metodo_z": "auto",
            "volume_adotado": "longitudinal", "eixo_IL": "LCF",
            "origem_x": "tabela", "L_ref": "LPP", "B_ref": "BWL",
            "sub_vertical": 4, "espessura_quilha": 0.0},
    "T_sel": 1.0,
}


def iniciar_estado():
    """
    Garante que o estado da sessao existe E tem o tipo certo.

    A verificacao de tipo importa: uma aba aberta antes de uma atualizacao do
    programa continua com o estado antigo na memoria do navegador, e uma chave
    que virou None ou mudou de formato derruba a barra lateral em toda execucao,
    sem deixar caminho de volta. Aqui a chave estragada e simplesmente refeita.
    """
    for k, v in PADRAO.items():
        atual = st.session_state.get(k, None)
        precisa = (k not in st.session_state)
        if not precisa and isinstance(v, (dict, list)):
            precisa = not isinstance(atual, type(v))
        if precisa:
            st.session_state[k] = (v.copy() if isinstance(v, (dict, list)) else v)


def principais() -> dict:
    """Dados do navio, sempre como dicionario."""
    p = st.session_state.get("principais")
    if not isinstance(p, dict):
        p = PADRAO["principais"].copy()
        st.session_state["principais"] = p
    return p


def opcoes() -> dict:
    """
    Convencoes de calculo, sempre como dicionario e sem chave faltando.

    As dimensoes principais sao copiadas para dentro das opcoes a cada chamada.
    O nucleo le o comprimento e a boca dos coeficientes em opt["LPP"] e opt["B"];
    sem essa copia ele nao os encontrava e caia no comprimento na linha d'agua,
    de modo que escolher "LPP" na etapa 1 nao surtia efeito algum e as curvas de
    C_B, C_WP e C_P saiam serrilhadas mesmo com a opcao correta marcada.
    """
    o = st.session_state.get("opt")
    if not isinstance(o, dict):
        o = PADRAO["opt"].copy()
        st.session_state["opt"] = o
    for k, v in PADRAO["opt"].items():
        o.setdefault(k, v)

    p = principais()
    for chave in ("LPP", "B", "D", "Td"):
        valor = p.get(chave)
        if valor:
            o[chave] = float(valor)
        else:
            o.pop(chave, None)
    return o


CHAVES_RESULTADO = ("rho", "metodo_x", "metodo_z", "volume_adotado", "eixo_IL",
                    "origem_x", "L_ref", "B_ref", "sub_vertical", "espessura_quilha",
                    "LPP", "B")


def assinatura_calculo(opt: dict) -> dict:
    """Fotografia das opcoes que mudam os numeros, para detectar tabela desatualizada."""
    return {k: opt.get(k) for k in CHAVES_RESULTADO}


def rerodar():
    try:
        st.rerun()
    except AttributeError:
        st.experimental_rerun()


def reiniciar_tudo():
    uid = st.session_state.get("uploader_id", 0) + 1
    for k in list(st.session_state.keys()):
        if k == "pagina":          # chave do radio: so pode mudar antes do widget
            continue
        del st.session_state[k]
    iniciar_estado()
    st.session_state["uploader_id"] = uid
    st.session_state["_ir_para"] = "Inicio"
    H.registrar("Sistema", "Aplicativo reiniciado. Dados, decisoes e resultados anteriores "
                           "foram descartados.", nivel="DECISAO", autor="usuario",
                consequencia="Uma nova tabela de cotas pode ser carregada do zero.")


def ir_para(pagina: str):
    """
    Leva o usuario a outra etapa.

    O destino nao pode ser escrito direto em st.session_state["pagina"]: essa e a
    chave do radio da barra lateral, e o Streamlit proibe alterar a chave de um
    widget depois que ele ja foi criado na mesma execucao. Entao o destino fica
    numa chave comum e a barra lateral o aplica no comeco da execucao seguinte,
    antes de montar o radio.
    """
    st.session_state["_ir_para"] = pagina
    rerodar()


def botao_proximo(destino: str, rotulo: str = None):
    """Botao que leva a proxima etapa do roteiro."""
    st.divider()
    if st.button(rotulo or f"Proximo passo:  {destino}  >", type="primary", **W()):
        ir_para(destino)


# ---------------------------------------------------------------------------
# Estado da tabela
# ---------------------------------------------------------------------------

def tem_tabela() -> bool:
    return st.session_state.get("tab") is not None


def esta_completa() -> bool:
    t = st.session_state.get("tab")
    return t is not None and bool(np.isfinite(t.Y).all()) and t.n_est >= 3 and t.n_wl >= 2


def exige_tabela() -> bool:
    if tem_tabela():
        return True
    st.info("Nenhuma tabela de cotas carregada ainda.")
    if st.button("Ir para a etapa 2 e carregar a tabela", type="primary"):
        ir_para("2. Tabela de cotas")
    return False


def exige_completa() -> bool:
    if not exige_tabela():
        return False
    t = st.session_state.tab
    if t.n_est < 3 or t.n_wl < 2:
        st.error("Sao necessarias pelo menos 3 balizas e 2 linhas d'agua para calcular.")
        return False
    if not np.isfinite(t.Y).all():
        n = int((~np.isfinite(t.Y)).sum())
        st.warning(f"A tabela ainda tem **{n} celula(s) sem valor**. O aplicativo nao calcula "
                   "a partir de dados incompletos sem que voce decida como preenche-los.")
        if st.button("Ir para a etapa 2 e completar a tabela", type="primary"):
            ir_para("2. Tabela de cotas")
        return False
    return True


def calado_maximo() -> float:
    t = st.session_state.tab
    return float(H.calado_max(t)) if t is not None else 1.0


# ---------------------------------------------------------------------------
# Widgets protegidos: nunca quebram quando a faixa e degenerada
# ---------------------------------------------------------------------------

def slider_seguro(rotulo, vmin, vmax, valor=None, passo=None, key=None, ajuda=None):
    """
    st.slider que tolera faixa nula ou invalida.

    O aplicativo ja quebrou por causa disso: quando a Hydrostatic Table saiu com
    uma unica linha, o slider de consulta recebeu minimo igual ao maximo e o
    Streamlit levantou excecao. Aqui esse caso vira uma mensagem, nao um erro.
    """
    vmin, vmax = float(vmin), float(vmax)
    if not (np.isfinite(vmin) and np.isfinite(vmax)) or vmax - vmin <= 1e-9:
        v = vmin if np.isfinite(vmin) else 0.0
        st.caption(f"{rotulo}: valor unico disponivel, {H.fmt(v)}.")
        return v
    if valor is None or not np.isfinite(valor):
        valor = 0.5 * (vmin + vmax)
    valor = float(min(max(valor, vmin), vmax))
    if passo is None or not np.isfinite(passo) or passo <= 0:
        passo = (vmax - vmin) / 200.0
    passo = float(min(passo, vmax - vmin))
    return st.slider(rotulo, vmin, vmax, valor, step=passo, key=key, help=ajuda)


def numero_seguro(rotulo, vmin, vmax, valor, passo=0.01, fmt_="%.4f", key=None, ajuda=None):
    vmin, vmax = float(vmin), float(vmax)
    if vmax < vmin:
        vmax = vmin
    valor = float(min(max(float(valor), vmin), vmax))
    return st.number_input(rotulo, vmin, vmax, valor, step=float(passo),
                           format=fmt_, key=key, help=ajuda)


# ---------------------------------------------------------------------------
# Barra lateral
# ---------------------------------------------------------------------------

def origem_texto(opt) -> str:
    return {"tabela": "x conforme o arquivo",
            "pp_re": "x = 0 na perpendicular de re",
            "meia_nau": "x = 0 na meia-nau"}[opt.get("origem_x", "tabela")]


def barra_lateral() -> str:
    # aplica a navegacao pedida na execucao anterior, antes de criar o radio
    destino = st.session_state.pop("_ir_para", None)
    if destino in PAGINAS:
        st.session_state["pagina"] = destino
    if "pagina" not in st.session_state:
        st.session_state["pagina"] = "Inicio"

    with st.sidebar:
        st.markdown("### Calculo Hidrostatico")
        st.caption("AP1.1 - Projeto Integrador")

        pagina = st.radio("Etapas", PAGINAS, key="pagina", label_visibility="collapsed")

        p = principais()
        o = opcoes()
        if any(p.get(k) for k in ("nome", "LPP", "B", "D", "Td")):
            st.divider()
            st.markdown("**Dados do navio**")
            linhas = [("Nome", p.get("nome") or "-"),
                      ("LPP", f"{H.fmt(p.get('LPP'), 2)} m"),
                      ("Boca B", f"{H.fmt(p.get('B'), 2)} m"),
                      ("Pontal D", f"{H.fmt(p.get('D'), 2)} m"),
                      ("Calado Td", f"{H.fmt(p.get('Td'), 2)} m"),
                      ("rho", f"{H.fmt(o.get('rho'), 3)} t/m3")]
            st.dataframe(pd.DataFrame(linhas, columns=["Grandeza", "Valor"]),
                         hide_index=True, **W())

        st.divider()
        t = st.session_state.get("tab")
        if t is None:
            st.caption("Tabela de cotas: nao carregada")
        else:
            falta = int((~np.isfinite(t.Y)).sum())
            st.caption(f"Tabela: {t.n_est} balizas x {t.n_wl} linhas d'agua")
            st.caption(f"Comprimento {H.fmt(abs(t.x[-1]-t.x[0]), 2)} m  |  "
                       f"altura {H.fmt(t.z[-1]-t.z[0], 2)} m")
            if falta:
                st.caption(f"{falta} celula(s) por preencher")

            Tmax = calado_maximo()
            if Tmax > 1e-9:
                atual = float(st.session_state.get("T_sel") or Tmax * 0.5)
                st.session_state["T_sel"] = float(min(max(atual, 0.0), Tmax))
                st.markdown("**Calado de interesse**")
                st.session_state["T_sel"] = slider_seguro(
                    "T (m)", 0.0, Tmax, st.session_state["T_sel"],
                    passo=max(Tmax / 200, 1e-4),
                    ajuda="Vale para as telas de geometria e de resultados. "
                          "Medido a partir da primeira linha d'agua da tabela.")

        st.divider()
        if st.button("Reiniciar tudo", **W()):
            st.session_state["_confirmar_reset"] = True
        if st.session_state.get("_confirmar_reset"):
            st.caption("Apaga a tabela, as decisoes e os resultados.")
            c1, c2 = st.columns(2)
            if c1.button("Apagar", type="primary", **W()):
                reiniciar_tudo()
                rerodar()
            if c2.button("Cancelar", **W()):
                st.session_state["_confirmar_reset"] = False
                rerodar()

    return pagina
