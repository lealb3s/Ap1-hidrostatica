# -*- coding: utf-8 -*-
"""
AP1.3 - Estabilidade estatica transversal: curva GZ a partir da tabela de cotas.

IDEIA DO CALCULO (nada de GZ = GM sen(phi) para a curva toda)
---------------------------------------------------------------------------
Para cada angulo de banda phi o casco e inclinado e a linha d'agua e reposicionada
ate que o volume submerso seja igual ao volume do deslocamento (V = Delta / rho).
Com a carena nova, o centro de carena B = (Y_B, Z_B) muda de lugar e

        GZ = Y_B cos(phi) + (Z_B - KG) sen(phi)

Passo a passo, para cada phi:

 1. Cada baliza da tabela de cotas e um poligono (meia-boca nas linhas d'agua,
    espelhada para os dois bordos, fechada no conves = ultima linha d'agua).
    E a mesma interpolacao linear entre pontos que o resto do aplicativo usa.
 2. A linha d'agua, no referencial do casco, e a reta   s + y sen(phi) - z cos(phi) = 0.
    Os pontos do casco com  s + y sen(phi) - z cos(phi) >= 0  estao submersos.
 3. Cada poligono e recortado por essa reta (Sutherland-Hodgman) e a area A_i e os
    momentos  int y dA  e  int z dA  saem exatos pela formula de Gauss (shoelace).
 4. Integra-se ao longo do comprimento com os MESMOS pesos a_i de Trapezio/Simpson
    do restante do aplicativo:  V = sum a_i A_i,   Y_B = sum a_i M_y,i / V,
    Z_B = sum a_i M_z,i / V.
 5. O parametro s e achado por busca (Illinois) ate  V(s) = V_alvo.

Convencoes
  * y positivo = boreste; banda positiva = BORESTE PARA BAIXO.
  * z medido a partir da linha de base (primeira linha d'agua da tabela), o mesmo
    referencial do KB, do KM e do KG do restante do aplicativo.
  * x cresce da popa para a proa (como na tabela). O compasso (trim) e opcional,
    positivo pela proa, e e mantido FIXO enquanto o casco inclina.

Hipoteses e limites (tambem listados no README)
  * Compasso fixo: o casco inclina sem mudar o trim. Nao ha trim livre.
  * O casco e fechado no conves (ultima linha d'agua): nao ha volume acima da tabela
    e nao ha alagamento. O angulo em que a borda do conves mergulha e informado.
  * Interpolacao linear da meia-boca entre linhas d'agua e entre balizas (as
    integracoes longitudinais usam Trapezio/Simpson conforme a malha).
  * Sem apendices, superestrutura, quilha de bolina ou tanques com superficie livre
    alem da correcao GG0 informada (que e a correcao de pequenos angulos).
---------------------------------------------------------------------------
"""

import numpy as np
import pandas as pd

from .base import *          # noqa: F401,F403
from .tabela import *        # noqa: F401,F403
from .integracao import *    # noqa: F401,F403

G_ACEL = 9.80665             # m/s2

__all__ = ["G_ACEL", "contornos_secoes", "MotorGZ", "curva_gz",
           "barcaca_gz_analitico", "comparar_curvas", "ler_curva_referencia",
           "modelo_curva_referencia"]


# ============================================================================ #
# GEOMETRIA DAS SECOES                                                         #
# ============================================================================ #

def contornos_secoes(tab: Tabela):
    """
    Poligono fechado de cada baliza, em coordenadas (y, z) com z a partir da base.
    Sobe pelo bordo de boreste, atravessa o conves e desce por bombordo: sentido
    anti-horario, area positiva.
    """
    z = np.asarray(tab.z, float) - float(tab.z[0])
    cont = []
    for i in range(tab.n_est):
        y = np.maximum(np.nan_to_num(np.asarray(tab.Y[i], float), nan=0.0), 0.0)
        cont.append((np.concatenate([y, -y[::-1]]), np.concatenate([z, z[::-1]])))
    return cont


def _momentos(py, pz):
    """Area, int y dA e int z dA de um poligono (formula de Gauss)."""
    n = len(py)
    if n < 3:
        return 0.0, 0.0, 0.0
    A = My = Mz = 0.0
    y0, z0 = py[-1], pz[-1]
    for y1, z1 in zip(py, pz):
        c = y0 * z1 - y1 * z0
        A += c
        My += (y0 + y1) * c
        Mz += (z0 + z1) * c
        y0, z0 = y1, z1
    return A / 2.0, My / 6.0, Mz / 6.0


def _recorte(ys, zs, s, sn, cs):
    """Parte do poligono com  s + y sn - z cs >= 0  (submersa), por Sutherland-Hodgman."""
    f = s + ys * sn - zs * cs
    n = len(ys)
    oy, oz = [], []
    for k in range(n):
        j = k + 1 if k + 1 < n else 0
        fk, fj = f[k], f[j]
        if fk >= 0.0:
            oy.append(ys[k])
            oz.append(zs[k])
        if (fk >= 0.0) != (fj >= 0.0):
            t = fk / (fk - fj)
            oy.append(ys[k] + t * (ys[j] - ys[k]))
            oz.append(zs[k] + t * (zs[j] - zs[k]))
    return oy, oz


# ============================================================================ #
# MOTOR: casco inclinado em equilibrio de volume                               #
# ============================================================================ #

class MotorGZ:
    """
    Pre-calcula o que nao depende do angulo (poligonos, pesos de integracao) e
    resolve a carena inclinada para qualquer banda.
    """

    def __init__(self, tab: Tabela, metodo_x="auto", compasso=0.0):
        self.tab = tab
        self.cont = contornos_secoes(tab)
        self.x = np.asarray(tab.x, float)
        self.a = np.abs(pesos_integracao(self.x, metodo_x)[0])
        self.L = float(abs(self.x[-1] - self.x[0]))
        self.m = float(compasso) / self.L if self.L > 0 else 0.0     # tan(trim)
        self.x0 = 0.5 * float(self.x.min() + self.x.max())
        self.cheio = [_momentos(ys, zs) for ys, zs in self.cont]
        self.V_total = float(np.dot(self.a, [c[0] for c in self.cheio]))
        self.z_topo = float(tab.z[-1] - tab.z[0])
        y_topo = np.array([ys[len(ys) // 2 - 1] for ys, _ in self.cont])
        self.i_borda = int(np.argmax(y_topo))       # baliza mais larga no conves
        self.y_borda = float(y_topo[self.i_borda])

    # -- volume e momentos para uma posicao s da linha d'agua --------------
    def _integrais(self, s, sn, cs):
        V = MY = MZ = 0.0
        off = self.m * cs
        for k, (ys, zs) in enumerate(self.cont):
            sk = s + (self.x[k] - self.x0) * off
            f = sk + ys * sn - zs * cs
            if f.min() >= 0.0:
                A, My, Mz = self.cheio[k]
            elif f.max() < 0.0:
                continue
            else:
                oy, oz = _recorte(ys, zs, sk, sn, cs)
                A, My, Mz = _momentos(oy, oz)
            a = self.a[k]
            V += a * A
            MY += a * My
            MZ += a * Mz
        return V, MY, MZ

    def _faixa_s(self, sn, cs):
        off = self.m * cs
        lo, hi = np.inf, -np.inf
        for k, (ys, zs) in enumerate(self.cont):
            d = (self.x[k] - self.x0) * off
            v = zs * cs - ys * sn
            lo = min(lo, float(v.min()) - d)
            hi = max(hi, float(v.max()) - d)
        return lo, hi

    def resolver(self, V_alvo: float, phi_deg: float, tol=1e-12) -> dict:
        """Acha a linha d'agua que da o volume V_alvo na banda phi e devolve a carena."""
        phi = np.radians(phi_deg)
        sn, cs = float(np.sin(phi)), float(np.cos(phi))
        if not (0.0 < V_alvo < self.V_total):
            raise ValueError(
                f"Volume {V_alvo:.4f} m3 fora da faixa do casco (0 a {self.V_total:.4f} m3): "
                "a embarcacao afunda ou nao ha deslocamento.")
        lo, hi = self._faixa_s(sn, cs)

        def F(s):
            return self._integrais(s, sn, cs)[0] - V_alvo

        a, b = lo, hi
        fa, fb = F(a), F(b)
        for _ in range(8):                         # bissecoes iniciais: robustez
            c = 0.5 * (a + b)
            fc = F(c)
            if fc < 0:
                a, fa = c, fc
            else:
                b, fb = c, fc
        side = 0
        s = 0.5 * (a + b)
        for _ in range(200):
            if fb == fa:
                s = 0.5 * (a + b)
            else:
                s = (a * fb - b * fa) / (fb - fa)
            fs = F(s)
            if abs(fs) <= tol * V_alvo:
                break
            if fs * fb > 0:
                b, fb = s, fs
                if side == -1:
                    fa *= 0.5
                side = -1
            elif fs * fa > 0:
                a, fa = s, fs
                if side == 1:
                    fb *= 0.5
                side = 1
            else:
                break
        V, MY, MZ = self._integrais(s, sn, cs)
        Yb, Zb = MY / V, MZ / V
        # a borda do conve (ponto mais externo do conves) esta abaixo da linha d'agua?
        ks = self.i_borda
        folga = s + (self.x[ks] - self.x0) * self.m * cs + self.y_borda * abs(sn) - self.z_topo * cs
        return {"phi": float(phi_deg), "s": float(s), "V": float(V), "Yb": float(Yb),
                "Zb": float(Zb), "sn": sn, "cs": cs,
                "T_LC": float(s / cs) if abs(cs) > 1e-9 else np.nan,
                "folga_borda": float(folga)}


def _gz(res: dict, KG: float) -> float:
    return res["Yb"] * res["cs"] + (res["Zb"] - KG) * res["sn"]


# ============================================================================ #
# CURVA GZ                                                                     #
# ============================================================================ #

def _secante_zero(f, a, b, fa, fb, n=60, tol=1e-10):
    """Raiz de f em [a, b] (f(a) e f(b) de sinais opostos), Illinois."""
    side = 0
    c = 0.5 * (a + b)
    for _ in range(n):
        c = (a * fb - b * fa) / (fb - fa) if fb != fa else 0.5 * (a + b)
        fc = f(c)
        if abs(fc) <= tol:
            return c
        if fc * fb > 0:
            b, fb = c, fc
            if side == -1:
                fa *= 0.5
            side = -1
        elif fc * fa > 0:
            a, fa = c, fc
            if side == 1:
                fb *= 0.5
            side = 1
        else:
            return c
    return c


def curva_gz(tab: Tabela, delta: float, KG: float, rho: float = 1.025,
             phi_max: float = 90.0, passo: float = 5.0, metodo_x: str = "auto",
             compasso: float = 0.0, GG0: float = 0.0, refinar: bool = True,
             motor: MotorGZ = None) -> dict:
    """
    Curva GZ completa. delta em toneladas, KG e GG0 em metros (KG a partir da base).
    Devolve {"df", "resumo", "motor", "avisos"}.
    """
    if delta <= 0 or rho <= 0:
        raise ValueError("Deslocamento e densidade precisam ser positivos.")
    if passo <= 0 or phi_max <= 0:
        raise ValueError("Angulo maximo e passo precisam ser positivos.")
    motor = motor or MotorGZ(tab, metodo_x, compasso)
    V = delta / rho
    KGe = float(KG) + float(GG0)                    # KG fluido (superficie livre)
    avisos = []

    angulos = np.arange(0.0, phi_max + 1e-9, passo)
    if abs(angulos[-1] - phi_max) > 1e-9:
        angulos = np.append(angulos, phi_max)

    res0 = motor.resolver(V, 0.0)
    linhas = []
    resultados = []
    for ph in angulos:
        r = res0 if ph == 0.0 else motor.resolver(V, float(ph))
        resultados.append(r)
        gz = _gz(r, KGe)
        linhas.append({
            "Banda (graus)": float(ph),
            "Banda (rad)": float(np.radians(ph)),
            "Calado no plano de centro (m)": r["T_LC"],
            "Volume (m3)": r["V"],
            "Y_B (m)": r["Yb"],
            "Z_B = KB_phi (m)": r["Zb"],
            "GZ (m)": gz,
            "Momento de endireitamento (t.m)": delta * gz,
            "Momento de endireitamento (kN.m)": delta * G_ACEL * gz,
            "Borda do conves imersa": bool(r["folga_borda"] >= 0.0),
        })
    df = pd.DataFrame(linhas)
    gz_v = df["GZ (m)"].to_numpy()
    ang = df["Banda (graus)"].to_numpy()

    # --- GM inicial pela propria curva (extrapolacao de Richardson em 0,5 e 1 grau)
    def g_sobre_sen(ph):
        r = motor.resolver(V, ph)
        return _gz(r, KGe) / r["sn"]
    g05, g10 = g_sobre_sen(0.5), g_sobre_sen(1.0)
    GM_num = (4.0 * g05 - g10) / 3.0

    # --- GZ maximo, refinado por secao aurea ao redor do maximo da malha
    k = int(np.argmax(gz_v))
    gz_max, ang_max = float(gz_v[k]), float(ang[k])
    max_no_extremo = (k == len(ang) - 1)
    if max_no_extremo and gz_v[k] > 0:
        avisos.append("O maximo de GZ esta no ultimo angulo calculado: a curva ainda sobe. "
                      "Aumente o angulo maximo para localizar o maximo verdadeiro.")
    elif refinar and 0 < k < len(ang) - 1 and gz_max > 0:
        a_, b_ = float(ang[k - 1]), float(ang[k + 1])
        fi = (np.sqrt(5.0) - 1.0) / 2.0
        c_, d_ = b_ - fi * (b_ - a_), a_ + fi * (b_ - a_)
        fc = _gz(motor.resolver(V, c_), KGe)
        fd = _gz(motor.resolver(V, d_), KGe)
        for _ in range(28):
            if fc > fd:
                b_, d_, fd = d_, c_, fc
                c_ = b_ - fi * (b_ - a_)
                fc = _gz(motor.resolver(V, c_), KGe)
            else:
                a_, c_, fc = c_, d_, fd
                d_ = a_ + fi * (b_ - a_)
                fd = _gz(motor.resolver(V, d_), KGe)
        ang_max = 0.5 * (a_ + b_)
        gz_max = _gz(motor.resolver(V, ang_max), KGe)

    # --- angulo de estabilidade nula (fim da faixa positiva)
    ang_zero = np.nan
    if gz_v[0] == 0.0 or abs(gz_v[0]) < 1e-12:
        for j in range(1, len(ang)):
            if gz_v[j - 1] > 0 and gz_v[j] <= 0:
                f = lambda p: _gz(motor.resolver(V, p), KGe)        # noqa: E731
                ang_zero = float(_secante_zero(f, float(ang[j - 1]), float(ang[j]),
                                               float(gz_v[j - 1]), float(gz_v[j])))
                break
    if not np.isfinite(ang_zero):
        avisos.append("GZ nao se anula no intervalo calculado.")

    # --- imersao da borda do conves
    ang_borda = np.nan
    borda = df["Borda do conves imersa"].to_numpy()
    if borda.any():
        j = int(np.argmax(borda))
        if j == 0:
            ang_borda = 0.0
        else:
            def fb(p):
                return motor.resolver(V, p)["folga_borda"]
            ang_borda = float(_secante_zero(fb, float(ang[j - 1]), float(ang[j]),
                                            fb(float(ang[j - 1])), fb(float(ang[j]))))

    # --- regioes de GZ positivo e negativo
    # fronteiras = angulos em que GZ muda de sinal (o primeiro e o refinado acima;
    # os demais, por interpolacao linear entre dois angulos calculados)
    regioes = []
    tolz = 1e-9
    idx = [j for j in range(len(ang)) if abs(gz_v[j]) > tolz]
    if idx:
        cruz = []
        for p_, q_ in zip(idx[:-1], idx[1:]):
            if gz_v[p_] * gz_v[q_] < 0:
                if np.isfinite(ang_zero) and not cruz and gz_v[p_] > 0:
                    cruz.append(ang_zero)
                else:
                    cruz.append(float(ang[p_] + (ang[q_] - ang[p_]) * gz_v[p_] / (gz_v[p_] - gz_v[q_])))
        limites = [0.0] + cruz + [float(ang[-1])]
        sinal = gz_v[idx[0]] > 0
        for a_, b_ in zip(limites[:-1], limites[1:]):
            regioes.append({"sinal": "positivo" if sinal else "negativo", "de": float(a_), "ate": float(b_)})
            sinal = not sinal
    if GM_num <= 0:
        avisos.append("GM inicial nulo ou negativo: a embarcacao e instavel na posicao direita "
                      "(tende a bandar ate o angulo de equilibrio por GZ = 0).")

    KB = res0["Zb"]
    resumo = {
        "delta_t": float(delta), "V_m3": float(V), "rho": float(rho),
        "KG": float(KG), "GG0": float(GG0), "KG_efetivo": KGe,
        "T_equilibrio": res0["T_LC"], "KB": KB,
        "GM_numerico": float(GM_num), "KM_numerico": float(GM_num + KGe),
        "BM_numerico": float(GM_num + KGe - KB),
        "GZ_max": float(gz_max), "ang_GZ_max": float(ang_max),
        "ang_estab_nula": float(ang_zero), "ang_borda_conves": float(ang_borda),
        "RM_max_tm": float(delta * gz_max), "RM_max_kNm": float(delta * G_ACEL * gz_max),
        "compasso_m": float(compasso), "regioes": regioes,
        "V_total_casco": motor.V_total,
        "reserva_empuxo_pct": float(100.0 * (motor.V_total - V) / V),
    }
    if (motor.V_total - V) / motor.V_total < 0.05:
        avisos.append("Reserva de empuxo menor que 5 % do volume do casco: o conves mergulha "
                      "com banda pequena e a curva perde sentido fisico.")
    return {"df": df, "resumo": resumo, "motor": motor, "avisos": avisos,
            "resultados": resultados}


# ============================================================================ #
# SOLUCAO ANALITICA DA BARCACA (Validacao 1)                                   #
# ============================================================================ #

def barcaca_gz_analitico(B, D, T, KG, phi_deg) -> dict:
    """
    GZ exato de uma secao retangular B x D, calado T, por integracao analitica
    (independente do aplicativo: nao usa recorte de poligonos).

    Com t = tan(phi), a altura molhada na posicao y e h(y) = clamp(c + t y, 0, D),
    onde c e a altura da linha d'agua em y = 0, fixada por  int h dy = B T.
      A  = int h dy      M_y = int y h dy      M_z = int h^2/2 dy
    Y_B = M_y / A,  Z_B = M_z / A  e  GZ = Y_B cos(phi) + (Z_B - KG) sen(phi).

    Tambem devolve a formula de parede vertical
        GZ = sen(phi) [GM + 1/2 BM tan^2(phi)],  BM = B^2/(12 T),
    valida enquanto a borda nao mergulha e o bojo nao emerge:
        tan(phi) <= 2 min(T, D - T) / B.
    """
    phi = np.radians(phi_deg)
    b = B / 2.0
    BM = B ** 2 / (12.0 * T)
    GM = T / 2.0 + BM - KG
    t = np.tan(phi)
    tan_lim = 2.0 * min(T, D - T) / B
    parede_valida = bool(abs(t) <= tan_lim + 1e-12)
    gz_parede = float(np.sin(phi) * (GM + 0.5 * BM * t ** 2))
    if abs(phi_deg) < 1e-12:
        return {"GZ_exato": 0.0, "GZ_parede": 0.0, "Yb": 0.0, "Zb": T / 2.0,
                "parede_valida": True, "GM": GM, "BM": BM}

    sinal = 1.0 if phi_deg > 0 else -1.0
    t = abs(t)

    def parte(c):
        y1, y2 = -c / t, (D - c) / t
        u = min(max(y1, -b), b)
        v = min(max(y2, -b), b)
        A = c * (v - u) + t * (v ** 2 - u ** 2) / 2.0 + D * (b - v)
        My = c * (v ** 2 - u ** 2) / 2.0 + t * (v ** 3 - u ** 3) / 3.0 + D * (b ** 2 - v ** 2) / 2.0
        Mz = ((c + t * v) ** 3 - (c + t * u) ** 3) / (6.0 * t) + D ** 2 * (b - v) / 2.0
        return A, My, Mz

    alvo = B * T
    lo, hi = -t * b, D + t * b
    for _ in range(300):
        c = 0.5 * (lo + hi)
        if parte(c)[0] < alvo:
            lo = c
        else:
            hi = c
    c = 0.5 * (lo + hi)
    A, My, Mz = parte(c)
    Yb, Zb = My / A, Mz / A
    u_, v_ = min(max(-c / t, -b), b), min(max((D - c) / t, -b), b)
    gz = Yb * np.cos(abs(phi)) + (Zb - KG) * np.sin(abs(phi))
    return {"GZ_exato": float(sinal * gz), "GZ_parede": float(sinal * abs(gz_parede)),
            "Yb": float(sinal * Yb), "Zb": float(Zb), "parede_valida": parede_valida,
            "GM": GM, "BM": BM,
            "passos": {"tan(phi)": float(t), "c (altura da agua em y=0) [m]": float(c),
                       "y onde h = 0 (limitado a +-B/2) [m]": float(u_),
                       "y onde h = D (limitado a +-B/2) [m]": float(v_),
                       "A = int h dy [m2]": float(A), "M_y = int y h dy [m3]": float(My),
                       "M_z = int h^2/2 dy [m3]": float(Mz), "A esperada = B T [m2]": float(alvo)}}


# ============================================================================ #
# COMPARACAO COM UMA REFERENCIA (Validacao 2)                                  #
# ============================================================================ #

def comparar_curvas(ang_ref, gz_ref, motor: MotorGZ, V, KG_efetivo,
                    tol_zero=0.005) -> pd.DataFrame:
    """
    Calcula o GZ do aplicativo exatamente nos angulos da referencia e compara.

    Diferenca absoluta  = GZ_app - GZ_ref  (m).
    Diferenca percentual = 100 * dif / |GZ_ref|, mas SOMENTE onde |GZ_ref| >= tol_zero:
    perto de zero o denominador e quase nulo e o percentual explode sem significado
    fisico, entao ali vale so a diferenca absoluta.
    """
    linhas = []
    for ph, gr in zip(ang_ref, gz_ref):
        r = motor.resolver(V, float(ph)) if abs(ph) > 1e-12 else motor.resolver(V, 0.0)
        ga = _gz(r, KG_efetivo)
        d = ga - float(gr)
        pct = 100.0 * d / abs(gr) if abs(gr) >= tol_zero else np.nan
        linhas.append({"Banda (graus)": float(ph), "GZ referencia (m)": float(gr),
                       "GZ aplicativo (m)": ga, "Diferenca absoluta (m)": d,
                       "Diferenca (%)": pct,
                       "Obs.": "|GZ_ref| < %.3f m: percentual nao informado" % tol_zero
                       if abs(gr) < tol_zero else ""})
    return pd.DataFrame(linhas)


def ler_curva_referencia(texto_ou_df) -> pd.DataFrame:
    """
    Le uma tabela de GZ de referencia (Maxsurf, livro ou artigo): duas colunas,
    banda em graus e GZ em metros. Aceita virgula ou ponto decimal, separador
    ponto e virgula, tabulacao ou espaco, e cabecalho de texto qualquer.
    """
    import io as _io
    if isinstance(texto_ou_df, pd.DataFrame):
        df = texto_ou_df.copy()
    else:
        txt = texto_ou_df.decode("utf-8-sig", errors="ignore") if isinstance(texto_ou_df, bytes) \
            else str(texto_ou_df)
        linhas = [l for l in txt.replace("\r", "").split("\n") if l.strip()]
        reg = []
        for l in linhas:
            for sep in (";", "\\t"):
                if sep in l:
                    partes = l.split(sep)
                    break
            else:
                partes = l.replace(",", ".").split() if l.count(",") > 1 else l.split()
            vals = [para_float(p) for p in partes]
            vals = [v for v in vals if np.isfinite(v)]
            if len(vals) >= 2:
                reg.append(vals[:2])
        if not reg:
            raise ValueError("Nao encontrei duas colunas numericas (banda e GZ).")
        df = pd.DataFrame(reg, columns=["Banda (graus)", "GZ (m)"])
    if df.shape[1] >= 2 and not set(["Banda (graus)", "GZ (m)"]).issubset(df.columns):
        num = [para_float(v) for v in df.iloc[:, 0]], [para_float(v) for v in df.iloc[:, 1]]
        df = pd.DataFrame({"Banda (graus)": num[0], "GZ (m)": num[1]})
    df = df.dropna().sort_values("Banda (graus)").drop_duplicates("Banda (graus)")
    return df.reset_index(drop=True)


def modelo_curva_referencia() -> str:
    """Texto do arquivo modelo para a Validacao 2 (sem numeros inventados)."""
    return ("Banda (graus);GZ (m)\n"
            "0;0\n"
            "# substitua as linhas abaixo pelos valores exportados do Maxsurf Stability\n"
            "# (ou do exemplo publicado), na mesma condicao: deslocamento, KG, trim e densidade.\n")
