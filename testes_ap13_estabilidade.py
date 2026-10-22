"""Testes independentes do núcleo AP1.3 (não exigem interface Streamlit)."""
import unittest
from types import SimpleNamespace
import numpy as np
from hidro.estabilidade import curva_gz

class TesteEstabilidadeAP13(unittest.TestCase):
    def setUp(self):
        # Barcaça prismática: L=10 m, B=4 m, calado=1 m; seções retangulares.
        self.x=np.linspace(0.,10.,11)
        self.z=np.array([0.,2.])
        self.Y=np.tile(np.array([2.,2.]),(len(self.x),1))
        self.tab=SimpleNamespace(x=self.x,z=self.z,Y=self.Y)

    def test_volume_conservado_ao_adornar(self):
        df,res=curva_gz(self.tab,1.0,0.8,1.025,np.arange(0.,31.,5.))
        self.assertAlmostEqual(res['volume_ref_m3'],40.0,places=4)
        self.assertLess(float(np.max(np.abs(df['Volume submerso (m³)']-40.0))),1e-4)

    def test_gm_inicial_comparado_a_formula_analitica(self):
        df,res=curva_gz(self.tab,1.0,0.8,1.025,np.array([0.,1.,2.,3.,5.]))
        # Barcaça retangular: KB=T/2; BM=I_T/V = L*B^3/(12*V).
        kb=0.5
        bm=10.0*4.0**3/(12.0*40.0)
        gm_analitico=kb+bm-0.8
        erro_rel=abs(res['GM_inicial_m']-gm_analitico)/abs(gm_analitico)
        self.assertLess(erro_rel,0.03)

    def test_gz_pos_tende_a_restaurar_para_cg_baixo(self):
        df,res=curva_gz(self.tab,1.0,0.8,1.025,np.arange(0.,16.,5.))
        self.assertTrue((df.loc[df['Angulo (graus)']>0,'GZ (m)']>0).all())

if __name__=='__main__': unittest.main(verbosity=2)
