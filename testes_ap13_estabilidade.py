"""Testes independentes do núcleo AP1.3 (não exigem Streamlit)."""
from types import SimpleNamespace
import numpy as np
from hidro.estabilidade import curva_gz


def barcaca_prismatica():
    """Barcaça retangular L=10 m, B=4 m, altura=2 m, 11 estações."""
    x = np.linspace(0.0, 10.0, 11)
    z = np.array([0.0, 2.0])
    Y = np.tile(np.array([2.0, 2.0]), (len(x), 1))
    return SimpleNamespace(x=x, z=z, Y=Y)


def test_volume_conservado_ao_adornar():
    tab = barcaca_prismatica()
    df, resumo = curva_gz(tab, 1.0, 0.8, 1.025, np.arange(0.0, 31.0, 5.0))
    assert abs(resumo["volume_ref_m3"] - 40.0) < 1e-6
    assert np.max(np.abs(df["Volume submerso (m³)"].to_numpy() - 40.0)) < 1e-4


def test_gm_inicial_comparado_com_analitico():
    tab = barcaca_prismatica()
    _, resumo = curva_gz(tab, 1.0, 0.8, 1.025, np.arange(0.0, 6.0, 1.0))
    volume = 10.0 * 4.0 * 1.0
    kb = 1.0 / 2.0
    it = 10.0 * 4.0**3 / 12.0
    bm = it / volume
    gm_analitico = kb + bm - 0.8
    erro_relativo = abs(resumo["GM_inicial_m"] - gm_analitico) / abs(gm_analitico)
    assert erro_relativo < 0.01


def test_gz_pequenos_angulos_comparado_com_gm_seno():
    """Compara 0°–5° (seis ângulos) com a aproximação de pequena banda."""
    tab = barcaca_prismatica()
    df, _ = curva_gz(tab, 1.0, 0.8, 1.025, np.arange(0.0, 6.0, 1.0))
    gm = 0.5 + (10.0 * 4.0**3 / 12.0) / 40.0 - 0.8
    for _, row in df.iterrows():
        ang = np.deg2rad(row["Angulo (graus)"])
        esperado = gm * np.sin(ang)
        obtido = float(row["GZ (m)"])
        if row["Angulo (graus)"] == 0:
            assert abs(obtido) < 1e-8
        else:
            erro_relativo = abs(obtido - esperado) / abs(esperado)
            assert erro_relativo < 0.01


def test_sinal_restaurador_para_cg_baixo():
    tab = barcaca_prismatica()
    df, _ = curva_gz(tab, 1.0, 0.8, 1.025, np.arange(0.0, 16.0, 5.0))
    positivos = df.loc[df["Angulo (graus)"] > 0, "GZ (m)"]
    assert (positivos > 0).all()


def test_rejeita_angulo_fora_da_faixa():
    tab = barcaca_prismatica()
    try:
        curva_gz(tab, 1.0, 0.8, 1.025, np.array([0.0, 65.0]))
    except ValueError:
        return
    raise AssertionError("Deveria rejeitar ângulo acima de 60°")


if __name__ == "__main__":
    tests = [
        test_volume_conservado_ao_adornar,
        test_gm_inicial_comparado_com_analitico,
        test_gz_pequenos_angulos_comparado_com_gm_seno,
        test_sinal_restaurador_para_cg_baixo,
        test_rejeita_angulo_fora_da_faixa,
    ]
    for test in tests:
        test()
        print(f"OK: {test.__name__}")
    print(f"{len(tests)} testes AP1.3 passaram.")
