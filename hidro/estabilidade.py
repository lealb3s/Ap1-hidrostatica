# -*- coding: utf-8 -*-
"""Calculo numerico da curva GZ a partir da tabela de cotas do casco.

Modelo: casco simetrico em relacao ao plano diametral, secao transversal
interpolada linearmente entre linhas d'agua e integracao longitudinal por
trapezios. Em cada banda, a linha d'agua e resolvida para conservar o volume
(deslocamento) de referencia. Trata-se de uma aproximacao numerica da geometria
importada, nao substitui um modelo 3D validado de estabilidade intacta.
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def _polygon_clip(points, level, eps=1e-12):
    """Recorta poligono 2D pelos pontos com coordenada vertical transformada <= level."""
    if len(points) < 3:
        return []
    out = []
    for i, P in enumerate(points):
        Q = points[(i + 1) % len(points)]
        fp, fq = P[2] - level, Q[2] - level
        inp, inq = fp <= eps, fq <= eps
        if inp and inq:
            out.append(Q)
        elif inp and not inq:
            den = Q[2] - P[2]
            t = 0.0 if abs(den) < eps else (level - P[2]) / den
            out.append((P[0] + t*(Q[0]-P[0]), P[1] + t*(Q[1]-P[1]), level))
        elif not inp and inq:
            den = Q[2] - P[2]
            t = 0.0 if abs(den) < eps else (level - P[2]) / den
            out.append((P[0] + t*(Q[0]-P[0]), P[1] + t*(Q[1]-P[1]), level))
            out.append(Q)
    # remove consecutive duplicates
    clean=[]
    for p in out:
        if not clean or np.linalg.norm(np.array(p)-np.array(clean[-1])) > 1e-10:
            clean.append(p)
    if len(clean)>1 and np.linalg.norm(np.array(clean[0])-np.array(clean[-1])) <= 1e-10:
        clean.pop()
    return clean


def _poly_area_centroid(poly):
    """Area e centroid (y,z) de poligono plano usando formula shoelace."""
    if len(poly) < 3: return 0.0, 0.0, 0.0
    p=np.asarray(poly, float); y=p[:,0]; z=p[:,1]
    cross=y*np.roll(z,-1)-np.roll(y,-1)*z
    signed=0.5*float(np.sum(cross))
    if abs(signed)<1e-14: return 0.0, 0.0, 0.0
    cy=float(np.sum((y+np.roll(y,-1))*cross)/(6*signed))
    cz=float(np.sum((z+np.roll(z,-1))*cross)/(6*signed))
    return abs(signed), cy, cz


def _section_polygon(z, breadth, heel):
    """Secao fechada aproximada por cotas. Retorna (y,z,y*sin+z*cos)."""
    z=np.asarray(z,float); b=np.asarray(breadth,float)
    good=np.isfinite(z)&np.isfinite(b)
    z=z[good]; b=b[good]
    order=np.argsort(z); z=z[order]; b=np.maximum(b[order],0)
    # inclui keel centre; remove pontos repetidos em z
    if len(z)<2: raise ValueError('Cada secao precisa de pelo menos duas cotas verticais.')
    zu=[]; bu=[]
    for zz,bb in zip(z,b):
        if zu and abs(zz-zu[-1])<1e-10: bu[-1]=max(bu[-1],bb)
        else: zu.append(float(zz)); bu.append(float(bb))
    z=np.asarray(zu); b=np.asarray(bu)
    if z[0] > 0:
        z=np.r_[0.,z]; b=np.r_[0.,b]
    pts=[]
    # bordo de boreste de fundo para convés
    for yy,zz in zip(b,z): pts.append((float(yy),float(zz)))
    # bordo oposto, convés para fundo
    for yy,zz in zip(b[::-1],z[::-1]): pts.append((-float(yy),float(zz)))
    s,c=np.sin(heel),np.cos(heel)
    return [(y,zz, y*s+zz*c) for y,zz in pts]


def _submerged_at(tab, heel, water_level):
    """Volume e centroides globais para uma linha d'agua transformada."""
    areas=[]; ysecs=[]; zsecs=[]
    for i in range(len(tab.x)):
        poly=_section_polygon(tab.z, tab.Y[i,:], heel)
        clipped=_polygon_clip(poly, water_level)
        a, yb, zb=_poly_area_centroid([(p[0],p[1]) for p in clipped])
        # centroides na secao ainda estao em coordenadas solidarias ao casco
        areas.append(a); ysecs.append(yb); zsecs.append(zb)
    x=np.asarray(tab.x,float); A=np.asarray(areas)
    V=float(np.trapezoid(A,x)) if hasattr(np, 'trapezoid') else float(np.trapz(A,x))
    if V <= 1e-12: return V, np.nan, np.nan, A
    # integrar os primeiros momentos seccionais ao longo de x
    My=float(np.trapezoid(A*np.asarray(ysecs),x)) if hasattr(np,'trapezoid') else float(np.trapz(A*np.asarray(ysecs),x))
    Mz=float(np.trapezoid(A*np.asarray(zsecs),x)) if hasattr(np,'trapezoid') else float(np.trapz(A*np.asarray(zsecs),x))
    yB_body, zB_body=My/V, Mz/V
    # Coordenadas globais: y' = y cos - z sin; z' = y sin + z cos
    yB_global=yB_body*np.cos(heel)-zB_body*np.sin(heel)
    zB_global=yB_body*np.sin(heel)+zB_body*np.cos(heel)
    return V, float(yB_global), float(zB_global), A


def _solve_waterline(tab, heel, target_volume, tol=1e-7, max_iter=90):
    zmax=float(np.nanmax(tab.z)); ymax=float(np.nanmax(tab.Y))
    span=max(zmax-zmin if (zmin:=float(np.nanmin(tab.z)))<zmax else zmax, ymax, 1.0)
    lo=-2*span; hi=2*span
    vlo=_submerged_at(tab,heel,lo)[0]; vhi=_submerged_at(tab,heel,hi)[0]
    for _ in range(8):
        if vlo <= target_volume <= vhi: break
        lo-=span; hi+=span
        vlo=_submerged_at(tab,heel,lo)[0]; vhi=_submerged_at(tab,heel,hi)[0]
    if not (vlo <= target_volume <= vhi):
        raise ValueError('Deslocamento alvo fora da capacidade geométrica representada pela tabela de cotas.')
    best=None
    for _ in range(max_iter):
        mid=0.5*(lo+hi); res=_submerged_at(tab,heel,mid); v=res[0]
        best=(mid,res)
        if abs(v-target_volume) <= max(tol, target_volume*1e-7): break
        if v < target_volume: lo=mid
        else: hi=mid
    return best[0], best[1]


def curva_gz(tab, calado, KG, rho=1.025, angulos=None, volume_alvo=None):
    """Calcula GZ conservando deslocamento. Unidades: m, t/m³, toneladas."""
    if angulos is None: angulos=np.arange(0,60.0001,5.)
    angulos=np.asarray(angulos,float)
    if not len(angulos) or np.any(angulos<0) or np.any(angulos>60):
        raise ValueError('Os ângulos devem estar entre 0° e 60°.')
    if np.any(np.diff(angulos)<=0): raise ValueError('Os ângulos devem ser estritamente crescentes.')
    if not np.isfinite(KG) or KG < 0: raise ValueError('KG deve ser um número finito não negativo.')
    if rho<=0: raise ValueError('A densidade deve ser positiva.')
    if not np.isfinite(tab.Y).all(): raise ValueError('Complete todas as células da tabela de cotas antes de calcular.')
    # deslocamento-alvo derivado do calado inicial, a menos que explicitamente fornecido
    V0, y0, z0, _ = _submerged_at(tab,0.,float(calado))
    if volume_alvo is not None: V0=float(volume_alvo)
    if V0<=0: raise ValueError('O volume deslocado inicial precisa ser positivo. Verifique o calado e a origem vertical da tabela.')
    # B e GM na posição direita: cálculo numérico por inclinação infinitesimal
    rows=[]
    for deg in angulos:
        heel=np.deg2rad(deg)
        wl,res=_solve_waterline(tab,heel,V0)
        V,yB,zB,A=res
        # G no sistema global, com CG sobre o plano diametral
        yG=-float(KG)*np.sin(heel)
        gz=float(yG-yB)
        rows.append({'Angulo (graus)':float(deg),'Linha d\'agua inclinada (m)':float(wl),
                     'Volume submerso (m³)':V,'Deslocamento (t)':V*float(rho),
                     'yB global (m)':yB,'zB global (m)':zB,'GZ (m)':gz,
                     'Momento endireitador (t.m)':V*float(rho)*gz})
    df=pd.DataFrame(rows)
    # GM inicial pelo limite numerico GZ/sin(theta), usando primeiro angulo > 0
    positivos=df[df['Angulo (graus)']>0]
    gm=float(positivos.iloc[0]['GZ (m)']/np.sin(np.deg2rad(positivos.iloc[0]['Angulo (graus)']))) if len(positivos) else np.nan
    imax=int(df['GZ (m)'].idxmax())
    resumo={'volume_ref_m3':V0,'deslocamento_ref_t':V0*float(rho),'GM_inicial_m':gm,
            'GZ_max_m':float(df.loc[imax,'GZ (m)']),'angulo_GZ_max_graus':float(df.loc[imax,'Angulo (graus)']),
            'sinal_estavel_inicial':bool(len(positivos) and positivos.iloc[0]['GZ (m)']>0)}
    return df,resumo
