# -*- coding: utf-8 -*-
"""
Testes do nucleo de calculo (secoes S1 a S9 do app.py), sem a interface Streamlit.
Execute:  python testes.py
"""
import io
import os
import sys
import numpy as np
import pandas as pd

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import hidro as _H
g = {k: getattr(_H, k) for k in dir(_H)}

falhas = []


def checa(nome, cond, detalhe=""):
    print(f"  {'OK  ' if cond else 'FALHA'}  {nome}" + (f"   {detalhe}" if detalhe else ""))
    if not cond:
        falhas.append(nome)


def perto(a, b, tol=1e-9):
    return abs(a - b) <= tol * max(1.0, abs(b))


# ============================================================================
print("\n[1] Leitura de numeros em formatos variados")
casos = [("1,25", 1.25), ("1.25", 1.25), ("1.234,56", 1234.56), ("1,234.56", 1234.56),
         ("  2,50 m ", 2.5), ("WL 3.5", 3.5), ("-0,75", -0.75), ("", np.nan),
         ("n/a", np.nan), ("-", np.nan), (3, 3.0), (2.5, 2.5), ("1.234.567,89", 1234567.89)]
for txt, esp in casos:
    v = g["para_float"](txt)
    ok = (np.isnan(v) and np.isnan(esp)) or perto(v, esp, 1e-12)
    checa(f"para_float({txt!r}) -> {v}", ok)


# ============================================================================
print("\n[2] Integracao numerica: exatidao das regras")
x = np.linspace(0, 6, 7)

# trapezio exato para funcao linear
f = 2 * x + 1
I, _ = g["integrar"](x, f, "trapezio")
checa("Trapezio exato em polinomio de grau 1", perto(I, 6 ** 2 + 6), f"I={I}")

# Simpson 1/3 exato ate grau 3
f = x ** 3 - 2 * x ** 2 + 5
I, _ = g["integrar"](x, f, "simpson13")
exato = 6 ** 4 / 4 - 2 * 6 ** 3 / 3 + 5 * 6
checa("Simpson 1/3 exato em polinomio de grau 3", perto(I, exato, 1e-10), f"I={I}")

# Simpson 3/8 exato ate grau 3
x2 = np.linspace(0, 6, 7)
I, aud = g["integrar"](x2, f, "simpson38")
checa("Simpson 3/8 exato em polinomio de grau 3", perto(I, exato, 1e-10), f"I={I}")

# automatico com numero impar de intervalos: 3/8 + 1/3
x3 = np.linspace(0, 7, 8)  # 7 intervalos
f3 = x3 ** 3 - 2 * x3 ** 2 + 5
I, aud = g["integrar"](x3, f3, "auto")
exato3 = 7 ** 4 / 4 - 2 * 7 ** 3 / 3 + 5 * 7
regras = [a["Regra"] for a in aud]
checa("Auto (7 intervalos) exato em grau 3", perto(I, exato3, 1e-10), f"I={I}")
checa("Auto usa 3/8 + 1/3 em numero impar",
      "Simpson 3/8" in regras and "Simpson 1/3" in regras, str(regras))

# pesos reproduzem a integral
a, mult, plano = g["pesos_integracao"](x3, "auto")
checa("Soma dos pesos a_i reproduz a integral", perto(float(np.dot(a, f3)), I, 1e-12))
checa("Soma dos pesos = comprimento do intervalo", perto(float(a.sum()), 7.0, 1e-12))

# passo nao uniforme -> trapezio nos trechos irregulares
xn = np.array([0, 1, 2, 3, 5, 7.0])
fn = 3 * xn + 2
I, aud = g["integrar"](xn, fn, "auto")
checa("Passo nao uniforme: linear ainda exato",
      perto(I, 3 * 7 ** 2 / 2 + 2 * 7, 1e-10), f"I={I}")
checa("Auditoria em formato do enunciado",
      "estacoes 0-" in g["auditoria_texto"](aud), g["auditoria_texto"](aud))


# ============================================================================
print("\n[3] Barcaca paralelepipedica: comparacao com a solucao analitica")
L, B, D, T = 40.0, 10.0, 5.0, 2.0
tab = g["barcaca_teste"](L, B, D, 11, 11)
opt = {"rho": 1.025, "metodo_x": "auto", "metodo_z": "auto",
       "volume_adotado": "longitudinal", "eixo_IL": "LCF",
       "origem_x": "tabela", "L_ref": "LPP", "B_ref": "BWL", "LPP": L, "B": B}
r = g["hidrostatica"](tab, T, opt)

checa("Volume = L*B*T", perto(r["VOL_L"], L * B * T, 1e-10), f"{r['VOL_L']}")
checa("Volume vertical = Volume longitudinal", perto(r["VOL_V"], L * B * T, 1e-10))
checa("E_vol ~ 0", r["E_VOL"] < 1e-8, f"{r['E_VOL']}")
checa("KB = T/2", perto(r["KB"], T / 2, 1e-10), f"{r['KB']}")
checa("LCB = L/2", perto(r["LCB"], L / 2, 1e-10), f"{r['LCB']}")
checa("LCF = L/2", perto(r["LCF"], L / 2, 1e-10), f"{r['LCF']}")
checa("A_WP = L*B", perto(r["AWP"], L * B, 1e-10), f"{r['AWP']}")
checa("BM_t = B^2/(12T)", perto(r["BMT"], B ** 2 / (12 * T), 1e-9), f"{r['BMT']}")
checa("BM_l = L^2/(12T)", perto(r["BML"], L ** 2 / (12 * T), 1e-9), f"{r['BML']}")
checa("KM_t = KB + BM_t", perto(r["KMT"], r["KB"] + r["BMT"], 1e-12))
checa("Delta = rho*Vol", perto(r["DESL"], 1.025 * L * B * T, 1e-10))
checa("TPC = rho*AWP/100", perto(r["TPC"], 1.025 * L * B / 100, 1e-10))
for c in ("CB", "CWP", "CM", "CP"):
    checa(f"{c} = 1", perto(r[c], 1.0, 1e-9), f"{r[c]}")
checa("C_B = C_M * C_P", perto(r["CB"], r["CM"] * r["CP"], 1e-12))
checa("WSA = L*B + 2*L*T", perto(r["WSA"], L * B + 2 * L * T, 1e-9), f"{r['WSA']}")

df = g["validacao_analitica"](r, L, B, T)
checa("Tabela de validacao analitica com erro < 1e-6 %",
      float(np.nanmax(df["Erro (%)"])) < 1e-6, f"max={np.nanmax(df['Erro (%)']):.2e}")

# calado entre linhas d'agua (interpolacao do calado)
T2 = 1.73
r2 = g["hidrostatica"](tab, T2, opt)
checa("Barcaca com calado fora da malha: Vol = L*B*T",
      perto(r2["VOL_L"], L * B * T2, 1e-9), f"{r2['VOL_L']}")
checa("Barcaca com calado fora da malha: KB = T/2",
      perto(r2["KB"], T2 / 2, 1e-9), f"{r2['KB']}")


# ============================================================================
print("\n[4] Casco em V (prisma triangular): segunda solucao analitica")
Lv, Bv, Dv, Tv = 30.0, 8.0, 4.0, 3.0
nx, nz = 13, 17
xv = np.linspace(0, Lv, nx)
zv = np.linspace(0, Dv, nz)
Yv = np.tile((Bv / 2) * (zv / Dv), (nx, 1))
tv = g["nova_tabela"](xv, zv, Yv)
optv = dict(opt)
optv.update({"LPP": Lv, "B": Bv})
rv = g["hidrostatica"](tv, Tv, optv)

vol_ex = Lv * (Bv / (2 * Dv)) * Tv ** 2
awp_ex = Lv * Bv * Tv / Dv
kb_ex = 2.0 / 3.0 * Tv
it_ex = (2.0 / 3.0) * Lv * (Bv * Tv / (2 * Dv)) ** 3
checa("V: Volume longitudinal", perto(rv["VOL_L"], vol_ex, 1e-9), f"{rv['VOL_L']} vs {vol_ex}")
checa("V: Volume vertical", perto(rv["VOL_V"], vol_ex, 1e-9), f"{rv['VOL_V']}")
checa("V: A_WP", perto(rv["AWP"], awp_ex, 1e-9), f"{rv['AWP']}")
checa("V: KB = 2T/3", perto(rv["KB"], kb_ex, 1e-9), f"{rv['KB']}")
checa("V: I_t", perto(rv["IT"], it_ex, 1e-9), f"{rv['IT']}")
checa("V: LCB = L/2", perto(rv["LCB"], Lv / 2, 1e-9))
checa("V: C_M = 0,5", perto(rv["CM"], 0.5, 1e-9), f"{rv['CM']}")
checa("V: C_B = C_M*C_P", perto(rv["CB"], rv["CM"] * rv["CP"], 1e-12))
lado = np.hypot(Bv * Tv / (2 * Dv), Tv)
checa("V: WSA = 2*L*lado", perto(rv["WSA"], 2 * Lv * lado, 1e-9), f"{rv['WSA']}")


# ============================================================================
print("\n[5] Comportamento das curvas hidrostaticas")
df_ht, brutos = g["tabela_hidrostatica"](tv, 0.5, 4.0, 0.25, optv)
colT = [c for c in df_ht.columns if c.startswith("T (calado)")][0]
for chave, nome in [("VOL", "Volume"), ("DESL", "Deslocamento"), ("AWP", "A_WP"),
                    ("KB", "KB"), ("TPC", "TPC")]:
    col = f"{g['PROPRIEDADES'][chave][0]} [{g['PROPRIEDADES'][chave][1]}]"
    v = df_ht[col].to_numpy(float)
    checa(f"Curva T x {nome} e crescente", bool(np.all(np.diff(v) > 0)))
col = f"{g['PROPRIEDADES']['BMT'][0]} [m]"
bmt = df_ht[col].to_numpy(float)
# casco em V prismatico: I_t ~ T^3 e Vol ~ T^2, logo BM_t cresce linearmente com T
checa("Curva T x BM_t cresce no casco em V", bool(np.all(np.diff(bmt) > 0)))
raz = bmt / df_ht[colT].to_numpy(float)
checa("BM_t/T constante no casco em V (comportamento analitico)",
      bool(np.allclose(raz, raz[0], rtol=1e-9)), f"{raz[:3]}")
lcb = df_ht[f"{g['PROPRIEDADES']['LCB'][0]} [m]"].to_numpy(float)
checa("LCB constante = L/2 em casco simetrico prismatico",
      bool(np.allclose(lcb, Lv / 2, atol=1e-8)), f"{lcb[:3]}")
q = g["consultar_curva"](df_ht, 2.0)
checa("Consulta numerica das curvas em T=2 m",
      perto(q["Vol (adotado) [m3]"], Lv * (Bv / (2 * Dv)) * 4.0, 5e-3),
      f"{q['Vol (adotado) [m3]']}")


# ============================================================================
print("\n[6] Leitura de arquivos: quatro layouts diferentes")


class Falso:
    """Imita o objeto retornado pelo file_uploader do Streamlit."""
    def __init__(self, nome, dados):
        self.name = nome
        self._d = dados

    def getvalue(self):
        return self._d


def canonico_de(arquivo):
    abas = g["ler_arquivo_bruto"](arquivo)
    grade = g["limpar_grade"](list(abas.values())[0])
    longo = g["detectar_formato_longo"](grade)
    if longo is not None:
        return longo
    det, gu, transp = g["detectar_melhor"](grade)
    assert det.ok, "deteccao falhou"
    x, z, Y, rot = g["montar_canonico"](gu, det)
    return x, z, Y


# --- referencia: barcaca 20 x 6 x 4, 5 estacoes, 5 WL
xr = np.array([0.0, 5.0, 10.0, 15.0, 20.0])
zr = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
Yr = np.full((5, 5), 3.0)
Yr[0] = [1.0, 1.5, 2.0, 2.5, 3.0]      # popa afinada
Yr[4] = [0.5, 1.0, 1.8, 2.4, 3.0]      # proa afinada


def confere(nome, x, z, Y):
    ok = (np.allclose(x, xr) and np.allclose(z, zr) and np.allclose(Y, Yr))
    checa(nome, ok, "" if ok else f"\n   x={x}\n   z={z}\n   Y=\n{Y}")


# --- Formato A: WL nas colunas, com linha de rotulos e linha de z (xlsx)
linhas = [["TABELA DE COTAS - NAVIO TESTE", None, None, None, None, None, None],
          [None, None, "WL 0", "WL 1", "WL 2", "WL 3", "WL 4"],
          ["Baliza", "X", 0.0, 1.0, 2.0, 3.0, 4.0]]
for i in range(5):
    linhas.append([i, xr[i]] + list(Yr[i]))
buf = io.BytesIO()
pd.DataFrame(linhas).to_excel(buf, index=False, header=False)
x, z, Y = canonico_de(Falso("formatoA.xlsx", buf.getvalue()))
confere("Formato A (WL nas colunas, rotulos + linha de z, .xlsx)", x, z, Y)

# --- Formato A-bis: layout exato do documento (z em linha propria, esquerda vazia)
linhas = [["Balizas", "X"] + [f"WL {j}" for j in range(5)],
          [None, None] + list(zr)]
for i in range(5):
    linhas.append([i, xr[i]] + list(Yr[i]))
buf = io.BytesIO()
pd.DataFrame(linhas).to_excel(buf, index=False, header=False)
x, z, Y = canonico_de(Falso("formatoAbis.xlsx", buf.getvalue()))
confere("Formato A-bis (layout do documento: linha de z abaixo dos rotulos)", x, z, Y)

# --- Formato A2: apenas rotulos "WL 0.0" com a altura embutida, sem linha de z
linhas = [["Baliza", "X"] + [f"WL {zz:.1f}" for zz in zr]]
for i in range(5):
    linhas.append([i, xr[i]] + list(Yr[i]))
buf = io.BytesIO()
pd.DataFrame(linhas).to_excel(buf, index=False, header=False)
x, z, Y = canonico_de(Falso("formatoA2.xlsx", buf.getvalue()))
confere("Formato A2 (altura embutida no rotulo da coluna)", x, z, Y)

# --- Formato B: transposta (balizas nas colunas)
linhas = [["WL / z"] + [f"Est {i}" for i in range(5)],
          ["X"] + list(xr)]
for j in range(5):
    linhas.append([zr[j]] + [Yr[i][j] for i in range(5)])
buf = io.BytesIO()
pd.DataFrame(linhas).to_excel(buf, index=False, header=False)
x, z, Y = canonico_de(Falso("formatoB.xlsx", buf.getvalue()))
confere("Formato B (tabela transposta, balizas nas colunas)", x, z, Y)

# --- Formato C: CSV brasileiro (ponto e virgula + virgula decimal)
lin = ["Baliza;X;WL0;WL1;WL2;WL3;WL4", ";;0,00;1,00;2,00;3,00;4,00"]
for i in range(5):
    lin.append(f"{i};" + str(xr[i]).replace(".", ",") + ";" +
               ";".join(str(v).replace(".", ",") for v in Yr[i]))
dados = ("\n".join(lin)).encode("utf-8")
x, z, Y = canonico_de(Falso("formatoC.csv", dados))
confere("Formato C (CSV com ';' e virgula decimal)", x, z, Y)

# --- Formato D: tabela longa x, z, y
lin = ["x;z;y"]
for i in range(5):
    for j in range(5):
        lin.append(f"{xr[i]};{zr[j]};{Yr[i][j]}")
x, z, Y = canonico_de(Falso("formatoD.csv", ("\n".join(lin)).encode("utf-8")))
confere("Formato D (tabela longa x, z, y)", x, z, Y)

# --- Formato E: matriz nua, sem qualquer cabecalho de texto
linhas = [[None, 0.0, 1.0, 2.0, 3.0, 4.0]]
for i in range(5):
    linhas.append([xr[i]] + list(Yr[i]))
buf = io.BytesIO()
pd.DataFrame(linhas).to_excel(buf, index=False, header=False)
x, z, Y = canonico_de(Falso("formatoE.xlsx", buf.getvalue()))
confere("Formato E (matriz nua: z na primeira linha, x na primeira coluna)", x, z, Y)

# --- todos os layouts devem levar ao mesmo resultado hidrostatico
t_ref = g["nova_tabela"](xr, zr, Yr)
opt_ref = dict(opt)
opt_ref.update({"LPP": 20.0, "B": 6.0})
r_ref = g["hidrostatica"](t_ref, 2.0, opt_ref)
checa("Casco assimetrico: LCB deslocado da meia-nau",
      abs(r_ref["LCB"] - 10.0) > 1e-3, f"LCB={r_ref['LCB']}")
checa("Casco assimetrico: volume positivo e coerente",
      0 < r_ref["VOL_L"] < 20 * 6 * 2, f"{r_ref['VOL_L']}")
checa("Casco assimetrico: E_vol pequeno", r_ref["E_VOL"] < 1.0, f"{r_ref['E_VOL']:.4f} %")


# --- arquivos de exemplo entregues junto com o aplicativo -------------------
pasta = os.path.join(AQUI, "exemplos")
if os.path.isdir(pasta):
    ref = None
    for arq in sorted(os.listdir(pasta)):
        if "barcaca" in arq:
            continue
        with open(os.path.join(pasta, arq), "rb") as fh:
            x, z, Y = canonico_de(Falso(arq, fh.read()))
        t = g["nova_tabela"](x, z, Y)
        o = dict(opt); o.update({"L_ref": "LWL", "B_ref": "BWL"})
        rr = g["hidrostatica"](t, 4.0, o)
        if ref is None:
            ref = rr["VOL_L"]
        checa(f"Exemplo '{arq}' lido e com volume identico aos demais",
              perto(rr["VOL_L"], ref, 1e-9), f"Vol={rr['VOL_L']:.4f} m3")


# ============================================================================
print("\n[7] Interpolacao e diagnostico")
Yf = Yr.astype(float).copy()
Yf[2, 2] = np.nan          # buraco interno
Yf[3, 4] = np.nan          # topo
tf = g["nova_tabela"](xr, zr, Yf)
ti, regs = g["interpolar_tabela"](tf, topo="manter", base="zero")
checa("Interpolacao preencheu todas as lacunas", bool(np.isfinite(ti.Y).all()))
checa("Lacuna interna por interpolacao linear em z", perto(ti.Y[2, 2], 3.0, 1e-12),
      f"{ti.Y[2,2]}")
checa("Lacuna no topo mantendo o ultimo valor", perto(ti.Y[3, 4], Yf[3, 3], 1e-12))
checa("Registro de cada interpolacao", len(regs) == 2, f"{len(regs)} registros")
checa("Dados originais e interpolados separados", ti.n_interpolados() == 2)

ach = g["diagnosticar"](tf, {"LPP": 20.0, "B": 6.0})
cods = [a.codigo for a in ach]
checa("Diagnostico detecta celulas vazias", "CEL-VAZIA" in cods, str(cods))

Yd = Yr.astype(float).copy()
td = g["nova_tabela"](np.array([0, 5, 5, 15, 20.0]), zr, Yd)
checa("Diagnostico detecta estacoes duplicadas",
      "EST-DUP" in [a.codigo for a in g["diagnosticar"](td, {})])

tm = g["nova_tabela"](xr, zr, Yr * 1000)
checa("Diagnostico suspeita de unidade errada",
      "UNI-SUSP" in [a.codigo for a in g["diagnosticar"](tm, {})])

tc = g["converter_unidade"](tm, "mm (milimetro)", "m (metro)")
checa("Conversao de unidade mm -> m", perto(float(tc.Y[0, 0]), Yr[0, 0], 1e-12),
      f"{tc.Y[0,0]}")


# ============================================================================
print("\n[8] Verificacoes internas e relatorio")
dfv = g["verificacoes_internas"](r)
checa("Consistencia interna com erro desprezivel",
      float(np.nanmax(dfv["Erro absoluto"])) < 1e-8,
      f"max={np.nanmax(dfv['Erro absoluto']):.2e}")

html = g["gerar_relatorio"]({
    "principais": {"nome": "Teste", "LPP": L, "B": B},
    "tab": tab, "opt": opt, "unidade_origem": "m (metro)",
    "origem_txt": "x conforme a tabela", "arquivo": "teste.xlsx", "aba": "-",
    "notas_deteccao": [], "tab_original_df": tab.como_df(), "achados": [],
    "avisos_ignorados": [], "interpolacoes": [], "aud_x": "-", "aud_z": "-",
    "historico": pd.DataFrame([{"n": 1, "acao": "teste"}]),
    "df_ht": df_ht, "resultado": r,
    "df_resumo": pd.DataFrame([{"Propriedade": "Vol", "Valor": r["VOL"], "Unidade": "m3"}]),
    "df_areas": pd.DataFrame({"Baliza": tab.rotulos, "A_i (m2)": r["_vol"]["A"]}),
    "df_val_int": dfv, "interpretacao_evol": "ok",
})
checa("Relatorio HTML gerado", len(html) > 5000 and "Hydrostatic Table" in html,
      f"{len(html)} caracteres")

xls = g["excel_hydrostatic_table"](df_ht, tab, {"nome": "Teste"},
                                   pd.DataFrame([{"n": 1}]), pd.DataFrame())
checa("Exportacao .xlsx da Hydrostatic Table", len(xls) > 3000, f"{len(xls)} bytes")


# ============================================================================
print("\n[9] Graficos")
import matplotlib.pyplot as plt
for nome, fn in [("plano de linhas", lambda: g["plot_plano_de_linhas"](tab, 2.0)),
                 ("body plan", lambda: g["plot_body_plan"](tab, 2.0)),
                 ("meia-boca", lambda: g["plot_meia_boca"](tab, 2.0)),
                 ("linhas de alto", lambda: g["plot_alto"](tab, 2.0)),
                 ("3D", lambda: g["plot_3d"](tab, 2.0)),
                 ("areas seccionais", lambda: g["plot_areas_seccionais"](
                     tab, r["_vol"]["A"], 2.0)),
                 ("secao isolada", lambda: g["plot_secao"](tab, 3, 2.0)),
                 ("curvas", lambda: g["plot_curvas"](df_ht)),
                 ("diagrama combinado", lambda: g["plot_diagrama_combinado"](df_ht))]:
    try:
        fig = fn()
        png = g["fig_para_png"](fig)
        plt.close(fig)
        checa(f"Grafico: {nome}", len(png) > 3000, f"{len(png)} bytes")
    except Exception as e:
        checa(f"Grafico: {nome}", False, repr(e))

# grafico do casco em V para inspecao visual
try:
    fig = g["plot_plano_de_linhas"](tv, 3.0)
    fig.savefig(os.path.join(AQUI, "saida_plano_linhas_V.png"), dpi=100,
                bbox_inches="tight")
    plt.close(fig)
    fig = g["plot_curvas"](df_ht)
    fig.savefig(os.path.join(AQUI, "saida_curvas_V.png"), dpi=100, bbox_inches="tight")
    plt.close(fig)
    fig = g["plot_3d"](tv, 3.0)
    fig.savefig(os.path.join(AQUI, "saida_3d_V.png"), dpi=100, bbox_inches="tight")
    plt.close(fig)
except Exception as e:
    checa("Figuras de inspecao salvas", False, repr(e))


# ============================================================================


# ============================================================================
print("\n[10] Interpolacao monotona e refinamento da tabela")
xr_ = np.array([0, 1, 2, 3, 4.0])
yr_ = np.array([0, 1.0, 1.4, 1.5, 1.5])
qq = np.linspace(0, 4, 41)
mm = g["interp_monotona"](xr_, yr_, qq)
checa("Curva monotona passa pelos pontos originais",
      bool(np.allclose(g["interp_monotona"](xr_, yr_, xr_), yr_)))
checa("Curva monotona nao ultrapassa os valores dos dados",
      bool(mm.max() <= yr_.max() + 1e-12 and mm.min() >= yr_.min() - 1e-12))
checa("Curva monotona nao oscila em dados crescentes",
      bool(np.all(np.diff(mm) >= -1e-12)))

# casco de secao semicircular: solucao exata conhecida
Lc, Rc = 30.0, 2.0
vol_ex = Lc * np.pi * Rc ** 2 / 2
kb_ex = Rc - 4 * Rc / (3 * np.pi)
xc = np.linspace(0, Lc, 11)
zc = np.linspace(0, Rc, 5)
tc = g["nova_tabela"](xc, zc, np.tile(np.sqrt(np.clip(zc * (2 * Rc - zc), 0, None)), (11, 1)))
oc = dict(opt); oc.update({"LPP": Lc, "B": 2 * Rc, "sub_vertical": 4})
r_bruto = g["hidrostatica"](tc, Rc, oc)
tref, resumo = g["refinar_tabela"](tc, 1, 4, "monotona")
r_ref = g["hidrostatica"](tref, Rc, oc)
e0 = abs(r_bruto["VOL_L"] - vol_ex) / vol_ex * 100
e1 = abs(r_ref["VOL_L"] - vol_ex) / vol_ex * 100
checa("Refinar aproxima o volume da solucao exata", e1 < e0,
      f"{e0:.3f} % -> {e1:.3f} %")
k0 = abs(r_bruto["KB"] - kb_ex) / kb_ex * 100
k1 = abs(r_ref["KB"] - kb_ex) / kb_ex * 100
checa("Refinar aproxima o KB da solucao exata", k1 < k0, f"{k0:.3f} % -> {k1:.3f} %")
checa("Refinamento preserva os pontos originais como dados de arquivo",
      int(tref.original.sum()) == tc.n_est * tc.n_wl,
      f"{int(tref.original.sum())} de {tc.n_est * tc.n_wl}")

# refinamento linear nao pode alterar resultado nenhum
tlin, _ = g["refinar_tabela"](tc, 1, 4, "linear")
checa("Refinamento linear nao altera o volume",
      perto(g["hidrostatica"](tlin, Rc, oc)["VOL_L"], r_bruto["VOL_L"], 1e-9))

# a barcaca continua exata depois de refinada
tbr, _ = g["refinar_tabela"](tab, 2, 2, "monotona")
rbr = g["hidrostatica"](tbr, T, opt)
checa("Barcaca refinada continua exata", perto(rbr["VOL_L"], L * B * T, 1e-9),
      f"{rbr['VOL_L']}")

# malha vertical subdividida corrige o KB de calado baixo
tv2 = g["nova_tabela"](np.linspace(0, 20, 11), np.array([0.0, 1.0]),
                       np.tile(np.array([0.0, 2.0]), (11, 1)))
o2 = dict(opt); o2.update({"LPP": 20.0, "B": 4.0})
kb_sub1 = g["hidrostatica"](tv2, 1.0, {**o2, "sub_vertical": 1})["KB"]
kb_sub8 = g["hidrostatica"](tv2, 1.0, {**o2, "sub_vertical": 8})["KB"]
checa("Sem subdividir, KB de um unico intervalo da o valor impossivel T",
      perto(kb_sub1, 1.0, 1e-9), f"KB={kb_sub1}")
checa("Subdividindo, KB do casco em V converge para 2T/3",
      perto(kb_sub8, 2.0 / 3.0, 1e-3), f"KB={kb_sub8}")


print("\n" + "=" * 70)
if falhas:
    print(f"{len(falhas)} FALHA(S):")
    for f_ in falhas:
        print("   -", f_)
    sys.exit(1)
print("TODOS OS TESTES PASSARAM.")
