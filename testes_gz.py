# -*- coding: utf-8 -*-
"""
Testes do modulo de estabilidade (AP1.3), sem a interface Streamlit.
Execute:  python testes_gz.py     (leva poucos segundos)
"""
import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hidro as H
from hidro.hidrostatica import barcaca_teste, hidrostatica

falhas = []


def checa(nome, cond, detalhe=""):
    print(f"  {'OK  ' if cond else 'FALHA'}  {nome}" + (f"   {detalhe}" if detalhe else ""))
    if not cond:
        falhas.append(nome)


L, B, D, T, KG, RHO = 40.0, 10.0, 5.0, 2.0, 3.0, 1.025
tab = H.barcaca_teste(L, B, D, 11, 11)
V = L * B * T
motor = H.MotorGZ(tab)

print("\n[1] Barcaca: GZ do aplicativo contra a solucao analitica exata (0 a 85 graus)")
erro = 0.0
for ph in np.arange(2.5, 85.0, 2.5):
    r = motor.resolver(V, float(ph))
    gz = r["Yb"] * r["cs"] + (r["Zb"] - KG) * r["sn"]
    erro = max(erro, abs(gz - H.barcaca_gz_analitico(B, D, T, KG, ph)["GZ_exato"]))
checa("Erro maximo de GZ abaixo de 1e-12 m em 34 angulos", erro < 1e-12, f"{erro:.2e} m")

print("\n[2] Barcaca: formula de parede vertical onde ela vale")
for ph in (5, 10, 15, 20):
    a = H.barcaca_gz_analitico(B, D, T, KG, ph)
    r = motor.resolver(V, float(ph))
    gz = r["Yb"] * r["cs"] + (r["Zb"] - KG) * r["sn"]
    checa(f"phi = {ph}: GZ = sen(phi)[GM + 1/2 BM tan^2(phi)]",
          a["parede_valida"] and abs(gz - a["GZ_parede"]) < 1e-12, f"{gz:.8f}")
a = H.barcaca_gz_analitico(B, D, T, KG, 40)
checa("phi = 40 (borda imersa e bojo emerso): a parede vertical NAO vale",
      (not a["parede_valida"]) and abs(a["GZ_parede"] - a["GZ_exato"]) > 0.1)

print("\n[3] Simetria e posicao direita")
r0 = motor.resolver(V, 0.0)
checa("phi = 0: Y_B = 0 e KB = T/2", abs(r0["Yb"]) < 1e-12 and abs(r0["Zb"] - T / 2) < 1e-12)
rp, rn = motor.resolver(V, 30.0), motor.resolver(V, -30.0)
checa("GZ(-phi) = -GZ(phi)",
      abs((rp["Yb"] * rp["cs"] + (rp["Zb"] - KG) * rp["sn"])
          + (rn["Yb"] * rn["cs"] + (rn["Zb"] - KG) * rn["sn"])) < 1e-12)
checa("Volume submerso conservado em todas as bandas",
      all(abs(motor.resolver(V, float(p))["V"] - V) < 1e-9 for p in (10, 30, 60, 80)))

print("\n[4] Resumo da curva da barcaca")
c = H.curva_gz(tab, RHO * V, KG, RHO, 90.0, 5.0)
R = c["resumo"]
BM = B ** 2 / (12 * T)
checa("GM numerico = KB + BM - KG", abs(R["GM_numerico"] - (T / 2 + BM - KG)) < 1e-6,
      f"{R['GM_numerico']:.6f} vs {T / 2 + BM - KG:.6f}")
gz_fino = [H.barcaca_gz_analitico(B, D, T, KG, p)["GZ_exato"] for p in np.arange(30, 45, 0.01)]
checa("GZ maximo refinado confere com busca fina analitica", abs(R["GZ_max"] - max(gz_fino)) < 1e-4,
      f"{R['GZ_max']:.6f} vs {max(gz_fino):.6f}")
ang0 = np.degrees(np.arctan(0))  # so para clareza
checa("Estabilidade nula entre 75 e 80 graus", 75 < R["ang_estab_nula"] < 80, f"{R['ang_estab_nula']:.3f}")
checa("A curva completa difere muito de GM sen(phi) em 60 graus",
      abs(c["df"].set_index("Banda (graus)").loc[60.0, "GZ (m)"] - R["GM_numerico"] * np.sin(np.radians(60))) > 0.5)
checa("Borda do conves imerge antes do GZ maximo", R["ang_borda_conves"] < R["ang_GZ_max"],
      f"{R['ang_borda_conves']:.2f} < {R['ang_GZ_max']:.2f}")

print("\n[5] Casco com formas (tabela jara laranja): coerencia com a hidrostatica do aplicativo")
x = np.linspace(0, 0.95, 11)
z = np.array([0, .0183, .0367, .055, .0733, .0917, .11])
sec = np.array([0, 0, .0227, .0561, .0813, .0917 * 0, 0])  # placeholder substituido abaixo
Y = np.array([
    [0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, .001239], [0, 0, 0, 0, 0, .034446, .105463],
    [0, 0, 0, .037402, .076029, .104432, .124727], [0, .022738, .05613, .081329, .101672, .118497, .132231],
    [0, .035732, .065388, .088819, .107619, .122639, .134595], [0, .034116, .06348, .087665, .107279, .122771, .134842],
    [0, .031127, .0596, .083924, .104031, .120126, .132806], [0, .017532, .046394, .06966, .08929, .106542, .121923],
    [0, 0, 0, .024362, .048339, .067839, .085186], [0, 0, 0, 0, 0, 0, 0]])
tabj = H.nova_tabela(x, z, Y)
opt = {"rho": 1.025, "metodo_x": "auto", "metodo_z": "auto", "volume_adotado": "longitudinal",
       "eixo_IL": "LCF", "sub_vertical": 4}
for Tcal in (0.04, 0.06, 0.075):
    h = hidrostatica(tabj, Tcal, opt)
    KGj = h["KMT"] - 0.02
    cj = H.curva_gz(tabj, h["DESL"], KGj, 1.025, 60.0, 5.0)
    Rj = cj["resumo"]
    checa(f"T = {Tcal}: calado de equilibrio = T", abs(Rj["T_equilibrio"] - Tcal) < 1e-9)
    checa(f"T = {Tcal}: KB da carena = KB da hidrostatica", abs(Rj["KB"] - h["KB"]) < 1e-8,
          f"{Rj['KB']:.6f} vs {h['KB']:.6f}")
    checa(f"T = {Tcal}: GM pela curva = KM_t - KG da hidrostatica",
          abs(Rj["GM_numerico"] - 0.02) < 1e-6, f"{Rj['GM_numerico']:.7f}")
checa("GZ do casco real e positivo e cresce no inicio",
      cj["df"]["GZ (m)"].iloc[1] > 0 and cj["df"]["GZ (m)"].iloc[2] > cj["df"]["GZ (m)"].iloc[1])

print("\n[6] Compasso fixo e erros de entrada")
mt = H.MotorGZ(tab, "auto", 0.5)
rt = mt.resolver(V, 0.0)
checa("Compasso fixo, prisma: KB = T/2 + trim^2/(24 T) (solucao analitica)",
      abs(rt["Zb"] - (T / 2 + 0.5 ** 2 / (24 * T))) < 1e-9, f"{rt['Zb']:.8f}")
checa("Compasso fixo: volume conservado com banda", abs(mt.resolver(V, 25.0)["V"] - V) < 1e-9)
try:
    H.curva_gz(tab, RHO * 10 * L * B * D, KG, RHO)
    checa("Deslocamento acima do volume do casco e recusado", False)
except ValueError:
    checa("Deslocamento acima do volume do casco e recusado", True)
c_neg = H.curva_gz(tab, RHO * V, 6.0, RHO, 30.0, 5.0)
checa("KG acima do KM: GM negativo e avisado", c_neg["resumo"]["GM_numerico"] < 0 and
      any("instavel" in a for a in c_neg["avisos"]))

print("\n[7] Comparacao com referencia")
ang = [10, 20, 30, 40, 50]
ref = [H.barcaca_gz_analitico(B, D, T, KG, a)["GZ_exato"] for a in ang]
cm = H.comparar_curvas(ang, ref, motor, V, KG)
checa("Referencia igual ao aplicativo: diferenca nula", cm["Diferenca absoluta (m)"].abs().max() < 1e-12)
cm = H.comparar_curvas([0.0, 10.0], [0.0, 0.39186], motor, V, KG)
checa("Percentual nao e calculado perto de zero (GZ_ref = 0)", np.isnan(cm["Diferenca (%)"].iloc[0]))
df = H.ler_curva_referencia("Heel (deg);GZ (m)\n0;0\n10,0;0,39\n20;0,84\n")
checa("Leitura de referencia com virgula decimal e cabecalho", len(df) == 3 and abs(df["GZ (m)"].iloc[1] - 0.39) < 1e-12)

print("\n" + "=" * 70)
if falhas:
    print(f"{len(falhas)} FALHA(S):")
    for f_ in falhas:
        print("   -", f_)
    sys.exit(1)
print("TODOS OS TESTES DA GZ PASSARAM.")
