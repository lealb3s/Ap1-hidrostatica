# Hidrostatica a partir da tabela de cotas corrigida, para comparar com o Maxsurf.
RHO = 1000.0  # agua doce, kg/m3

t = open('/mnt/user-data/outputs/tabela_cotas_corrigida.csv', encoding='utf-8-sig').read().splitlines()
linhas = [l.split(';') for l in t[1:] if l.strip()]
f = lambda s: float(s.replace(',', '.'))

X  = [f(r[1]) for r in linhas]
Y  = [[f(c) for c in r[2:]] for r in linhas]      # Y[estacao][linha_dagua]
Z  = [i * (0.11/6) for i in range(7)]
hx = X[1] - X[0]
hz = Z[1] - Z[0]

def simpson(v, h):
    n = len(v) - 1
    assert n % 2 == 0, n
    s = v[0] + v[-1] + 4*sum(v[1:-1:2]) + 2*sum(v[2:-1:2])
    return s * h / 3.0

def hidrostaticos(k):                     # k = indice da linha d'agua (calado)
    T = Z[k]
    if k % 2: return None                 # Simpson exige numero par de intervalos
    y_wl = [Y[i][k] for i in range(len(X))]

    Awp  = 2 * simpson(y_wl, hx)
    Mx   = 2 * simpson([X[i]*y_wl[i] for i in range(len(X))], hx)
    LCF  = Mx / Awp if Awp else 0.0
    # inercias do plano de flutuacao
    It   = (2.0/3.0) * simpson([y**3 for y in y_wl], hx)
    Il_o = 2 * simpson([X[i]**2 * y_wl[i] for i in range(len(X))], hx)
    Il   = Il_o - Awp * LCF**2            # eixos paralelos, pelo LCF

    # areas seccionais imersas ate T
    A = [2 * simpson(Y[i][:k+1], hz) for i in range(len(X))]
    V = simpson(A, hx)
    if V <= 0: return None
    LCB = simpson([X[i]*A[i] for i in range(len(X))], hx) / V

    # KB por momento das areas de flutuacao
    Awp_z = [2*simpson([Y[i][j] for i in range(len(X))], hx) for j in range(k+1)]
    KB = simpson([Z[j]*Awp_z[j] for j in range(k+1)], hz) / V

    BMt, BMl = It/V, Il/V
    disp = RHO * V
    L = X[-1] - X[0]
    return dict(T=T, Awp=Awp, V=V, disp=disp, LCF=LCF, LCB=LCB, KB=KB,
                BMt=BMt, KMt=KB+BMt, BMl=BMl, KMl=KB+BMl,
                Amax=max(A), TPc=Awp*RHO/1000/100,
                MTc=(disp/1000)*(KB+BMl-KB)/(100*L),
                Cwp=Awp/(L*2*max(y_wl)) if max(y_wl) else 0,
                Cb=V/(L*2*max(y_wl)*T) if (max(y_wl) and T) else 0)

print("Calado    Desloc.   Awp      Amax     KB      KMt     KML     LCB     LCF")
print("  m         kg       m2       m2      m       m       m       m       m")
print("-"*78)
for k in (2, 4, 6):
    r = hidrostaticos(k)
    print("{T:.4f}  {disp:8.3f} {Awp:8.5f} {Amax:8.5f} {KB:7.5f} {KMt:7.5f} {KMl:7.4f} {LCB:7.5f} {LCF:7.5f}".format(**r))

r = hidrostaticos(6)
print("\nNo calado maximo T = 0,1100 m")
print("  Volume        = {:.6f} m3".format(r['V']))
print("  Deslocamento  = {:.3f} kg (agua doce)".format(r['disp']))
print("  Cwp           = {:.3f}".format(r['Cwp']))
print("  Cb            = {:.3f}".format(r['Cb']))
print("  TPc           = {:.6f} t/cm".format(r['TPc']))
print("  BMt           = {:.5f} m".format(r['BMt']))
print("  BML           = {:.4f} m".format(r['BMl']))


# ============================================================
# ESTABILIDADE INICIAL
# KG NAO e propriedade do casco: vem da distribuicao de pesos.
# Entra como dado do usuario; GM e derivado dele.
# ============================================================

def estabilidade_inicial(r, KG, momento_sup_livre=0.0):
    """
    r  : dicionario devolvido por hidrostaticos()
    KG : altura do centro de gravidade acima da linha de base [m]
    momento_sup_livre : soma de rho_liq * i_livre dos tanques [kg.m]

    Devolve GMt, GML, GMt efetivo e MTc calculado com GML.
    """
    L = X[-1] - X[0]

    GMt = r['KMt'] - KG
    GMl = r['KMl'] - KG

    # Correcao de superficie livre: reduz o GM aparente.
    ccs = momento_sup_livre / (RHO * r['V']) if r['V'] else 0.0
    GMt_ef = GMt - ccs

    # MTc com GML, nao com BML.
    MTc = (r['disp']/1000.0) * GMl / (100.0 * L)

    return dict(KG=KG, GMt=GMt, GMl=GMl, ccs=ccs, GMt_ef=GMt_ef, MTc=MTc)


r = hidrostaticos(6)
print("\n\nESTABILIDADE INICIAL no calado maximo T = 0,1100 m")
print("KMt = {:.5f} m   KML = {:.4f} m   Desloc. = {:.3f} kg".format(
    r['KMt'], r['KMl'], r['disp']))
print()
print("   KG        GMt       GML       MTc")
print("   m         m         m       t.m/cm     situacao")
print("-" * 56)
for KG in (0.040, 0.060, 0.080, 0.100, 0.120, 0.140):
    e = estabilidade_inicial(r, KG)
    if e['GMt'] > 0.05:
        sit = "estavel"
    elif e['GMt'] > 0:
        sit = "GM baixo"
    else:
        sit = "INSTAVEL"
    print("  {KG:.3f}   {GMt:8.5f}  {GMl:7.4f}  {MTc:.6f}   ".format(**e) + sit)

print("\nKG limite (GMt = 0) = KMt = {:.5f} m".format(r['KMt']))
print("Acima disso o casco nao tem estabilidade inicial positiva.")
