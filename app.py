# -*- coding: utf-8 -*-
"""
=============================================================================
 APLICATIVO DE CALCULO HIDROSTATICO - AP1.1 Projeto Integrador
 Arquitetura Naval
=============================================================================

 Ponto de entrada. Este arquivo so monta a pagina e chama a tela escolhida;
 toda a logica esta nos pacotes:

     hidro/       calculo (leitura, integracao, hidrostatica, graficos)
     interface/   telas (uma por etapa do roteiro)

 Execucao:  streamlit run app.py
=============================================================================
"""

import streamlit as st

st.set_page_config(page_title="Calculo Hidrostatico", page_icon="~",
                   layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
.block-container{padding-top:2.2rem;padding-bottom:3rem;max-width:1400px}
div[data-testid="stMetricValue"]{font-size:1.3rem}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Conferencia do pacote de calculo
#
# O pacote hidro reune suas funcoes no arquivo hidro/__init__.py. Se esse arquivo
# for enviado vazio ou incompleto, "import hidro" continua funcionando, mas nao
# traz funcao nenhuma junto: o programa so quebra bem mais tarde, com um erro que
# nao diz qual e o problema. Aqui o pacote e remontado na hora, a partir dos
# proprios modulos, para que isso nunca derrube o aplicativo.
# ---------------------------------------------------------------------------
import importlib                                                # noqa: E402
import pkgutil                                                    # noqa: E402

import hidro as _hidro                                            # noqa: E402

# Modulos que o pacote precisa ter, e o que cada um fornece ao restante.
_ESPERADOS = {
    "base": "constantes, leitura de numeros e historico",
    "leitura": "abertura do arquivo e deteccao do layout",
    "tabela": "modelo da tabela e diagnostico",
    "integracao": "Trapezio e Simpson",
    "hidrostatica": "areas, volumes e centros",
    "graficos": "plano de linhas e curvas",
    "relatorio": "relatorio HTML e Excel",
    "pdf": "relatorio em PDF (opcional)",
}

# erros que o proprio pacote registrou ao se carregar
_erros = dict(getattr(_hidro, "ERROS_IMPORT", {}))

if not hasattr(_hidro, "fmt") or not hasattr(_hidro, "gerar_relatorio_pdf"):
    # A lista de modulos e descoberta, e nao escrita a mao: quando o pacote ganha
    # um arquivo novo, ele entra sozinho.
    # so os modulos que o pacote realmente tem. Arquivos estranhos na pasta, como
    # uma copia do __init__.py enviada com outro nome, sao ignorados de proposito.
    _existentes = {i.name for i in pkgutil.iter_modules(_hidro.__path__)}
    for _n2 in [n for n in _ESPERADOS if n in _existentes]:
        try:
            _mod = importlib.import_module(f"hidro.{_n2}")
        except Exception as _e:                                    # noqa: BLE001
            _erros.setdefault(_n2, f"{type(_e).__name__}: {_e}")
            continue
        _erros.pop(_n2, None)
        for _nome in dir(_mod):
            # ERROS_IMPORT pertence ao pacote: copiar a de um modulo apagaria o
            # diagnostico verdadeiro por um de outro arquivo
            if not _nome.startswith("_") and _nome != "ERROS_IMPORT":
                setattr(_hidro, _nome, getattr(_mod, _nome))

# um modulo que nem chegou a ser encontrado no disco
_no_disco = {i.name for i in pkgutil.iter_modules(_hidro.__path__)}
for _n in _ESPERADOS:
    if _n not in _no_disco and _n not in _erros:
        _erros[_n] = "arquivo ausente na pasta hidro"

# arquivos que nao pertencem ao pacote costumam ser copias enviadas por engano
_intrusos = sorted(_no_disco - set(_ESPERADOS))
if _intrusos:
    st.warning(
        "Ha arquivo que nao faz parte do pacote na pasta **hidro**: "
        + ", ".join(f"`{n}.py`" for n in _intrusos) +
        ". Se for uma copia do `__init__.py` enviada com outro nome, apague do "
        "repositorio: ela nao e usada e pode atrapalhar o carregamento.")

_ausentes = [n for n in ("fmt", "hidrostatica", "plot_curvas", "ler_arquivo_bruto",
                         "gerar_relatorio")
             if not hasattr(_hidro, n)]

from interface import comum                                    # noqa: E402
from interface import (inicio, p1_dados, p2_cotas, p3_geometria,  # noqa: E402
                       p4_metodos, p5_calado, p6_curvas,
                       p7_validacao, p8_relatorio)

TELAS = {
    "Inicio": inicio.render,
    "1. Dados do navio": p1_dados.render,
    "2. Tabela de cotas": p2_cotas.render,
    "3. Conferir a geometria": p3_geometria.render,
    "4. Metodos de calculo": p4_metodos.render,
    "5. Resultados no calado": p5_calado.render,
    "6. Tabela e curvas": p6_curvas.render,
    "7. Validacao": p7_validacao.render,
    "Relatorio final": p8_relatorio.render,
}

_erros_pdf = {k: v for k, v in _erros.items() if k == "pdf"}
_erros = {k: v for k, v in _erros.items() if k != "pdf"}
if _erros_pdf and not _erros:
    st.warning("O relatorio em PDF nao esta disponivel: "
               + "; ".join(f"hidro/pdf.py - {v}" for v in _erros_pdf.values())
               + ". O relatorio em HTML continua funcionando normalmente.")

if _erros or _ausentes:
    _linhas = []
    for _n, _msg in _erros.items():
        _linhas.append(f"- **hidro/{_n}.py** — {_msg}  \n  "
                       f"_(fornece: {_ESPERADOS.get(_n, 'modulo extra')})_")
    # um modulo pode falhar so porque outro, do qual ele depende, falhou antes
    _raiz = [n for n in _erros if "No module named" not in _erros[n]
             and "ausente" not in _erros[n]]
    _sumidos = [n for n in _erros if "ausente" in _erros[n]
                or "No module named" in _erros[n]]
    st.error(
        "### O pacote de calculo nao foi carregado por inteiro\n\n"
        + "\n".join(_linhas) +
        ("\n\n**Comece pelos arquivos que faltam:** "
         + ", ".join(f"`hidro/{n}.py`" for n in _sumidos) +
         ". Os demais podem estar falhando so porque dependem deles."
         if _sumidos else "") +
        "\n\nEnvie os arquivos que faltam para a pasta **hidro** do repositorio e "
        "confira se nenhum ficou vazio.")
    if _ausentes and not _erros:
        st.error("Funcoes que o programa nao encontrou: "
                 + ", ".join(f"`{n}`" for n in _ausentes))
    st.stop()

comum.iniciar_estado()
pagina = comum.barra_lateral()
TELAS[pagina]()
