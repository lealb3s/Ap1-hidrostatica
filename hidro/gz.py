# -*- coding: utf-8 -*-
"""AP1.3: estabilidade intacta transversal por integracao de secoes imersas.

Sistema: x longitudinal, y positivo para boreste, z acima da linha de base.
Banda positiva = boreste desce. Linha d'agua: z*cos(theta)-y*sin(theta)=h.
Nao modela trim, superficies livres, downflooding nem movimentos longitudinais.
"""
from dataclasses import dataclass
import numpy as np
import pandas as pd


def _clip(poly, a, b, c, tol=1e-11):
    """Recorta poligono convexo ou simples contra a*y+b*z<=c (Sutherland-Hodgman)."""
    if len(poly)==0: return np.empty((0,2))
    out=[]
    for P,Q in zip(poly, np.roll(poly,-1,axis=0)):
        fp=a*P[0]+b*P[1]-c; fq=a*Q[0]+b*Q[1]-c
        pin=fp<=tol; qin=fq<=tol
        if pin and qin: out.append(Q)
        elif pin != qin:
            den=fp-fq
            if abs(den)>1e-15:
                I=P+fp/den*(Q-P)
                out.append(I)
            if qin: out.append(Q)
    return np.array(out,dtype=float).reshape(-1,2)


def _moments(poly):
    """Area e primeiros momentos seccionais de poligono (y,z)."""
    if len(poly)<3: return 0.,0.,0.
    y=poly[:,0]; z=poly[:,1]; yn=np.roll(y,-1); zn=np.roll(z,-1)
    cross=y*zn-yn*z
    A=float(np.sum(cross)/2)
    if abs(A)<1e-13: return 0.,0.,0.
    My=float(np.sum((y+yn)*cross)/6)
    Mz=float(np.sum((z+zn)*cross)/6)
    sign=np.sign(A)
    return A*sign,My*sign,Mz*sign


def _sections(x,z,Y):
    x=np.asarray(x,float); z=np.asarray(z,float); Y=np.asarray(Y,float)
    if Y.shape!=(len(x),len(z)): raise ValueError('Formato Y diferente de (balizas, linhas de agua).')
    if len(x)<2 or len(z)<2 or np.any(np.diff(x)<=0) or np.any(np.diff(z)<=0):
        raise ValueError('x e z devem estar estritamente crescentes e ter pelo menos 2 pontos.')
    if not np.isfinite(Y).all() or (Y<0).any():
        raise ValueError('Preencha as meias-bocas ausentes e remova valores negativos.')
    if np.max(Y)<=0: raise ValueError('Casco com meias-bocas nulas.')
    secs=[]
    for yi in Y:
        # Borda de boreste da quilha ao conves e bombordo de volta a quilha.
        right=np.column_stack([yi,z]); left=np.column_stack([-yi[::-1],z[::-1]])
        poly=np.vstack([right,left]); secs.append(poly)
    return x,z,secs


def _hydro(x, sections, theta, h):
    s=np.sin(theta); c=np.cos(theta)
    areas=[]; mys=[]; mzs=[]
    for sec in sections:
        a,my,mz=_moments(_clip(sec,-s,c,h))
        areas.append(a); mys.append(my); mzs.append(mz)
    V=float(np.trapezoid(areas,x)) if hasattr(np,'trapezoid') else float(np.trapz(areas,x))
    f=np.trapezoid if hasattr(np,'trapezoid') else np.trapz
    return V,float(f(mys,x)),float(f(mzs,x))


def _solve(x, sections, theta, Vtarget, lo, hi, maxiter=65):
    total=_hydro(x,sections,theta,hi)[0]
    if Vtarget>total*(1+1e-9): raise ValueError('Deslocamento maior que capacidade volumetrica do casco informado.')
    for _ in range(maxiter):
        mid=(lo+hi)/2
        v=_hydro(x,sections,theta,mid)[0]
        if v<Vtarget: lo=mid
        else: hi=mid
    h=(lo+hi)/2
    v,my,mz=_hydro(x,sections,theta,h)
    if v<=1e-12: raise ValueError('Volume submerso nulo.')
    return h,v,my/v,mz/v


def calcular(x,z,Y,calado,kg,rho=1.025,angulos=None,deslocamento_t=None,tcg=0.):
    """Retorna dados para cada banda, mantendo volume constante (equilibrio vertical).

    Massa em toneladas; densidade em t/m3; dimensoes em metros; momentos em t.m.
    A superficie de flutuacao e plana, sem trim e sem perda de estabilidade por inundacao.
    """
    x,z,secs=_sections(x,z,Y)
    if angulos is None: angulos=np.arange(0.,65.,5.)
    angulos=np.asarray(angulos,float)
    if len(angulos)==0 or (angulos<0).any() or (angulos>=90).any():
        raise ValueError('Angulos devem estar entre 0 e menos de 90 graus.')
    if not 0<=calado<=z.max(): raise ValueError('Calado fora da altura da tabela.')
    if rho<=0 or not np.isfinite([kg,tcg,rho]).all(): raise ValueError('Parametros invalidos.')
    L=max(np.abs(np.asarray([np.max(np.abs(s[:,0])) for s in secs])).max(),abs(z).max())
    lo=-3*L-abs(z).max(); hi=3*L+abs(z).max()
    V0=_hydro(x,secs,0.,calado)[0]
    Vt=V0 if deslocamento_t is None else float(deslocamento_t)/rho
    if Vt<=0: raise ValueError('Volume precisa ser positivo.')
    if Vt>=_hydro(x,secs,0.,hi)[0]-1e-10:
        raise ValueError('Embarcacao completamente submersa: nao ha linha d agua livre.')
    rows=[]
    for deg in angulos:
        theta=np.radians(deg)
        h,V,yB,zB=_solve(x,secs,theta,Vt,lo,hi)
        gz=(yB-tcg)*np.cos(theta)+(zB-kg)*np.sin(theta)
        rows.append({'Angulo (graus)':float(deg),'Plano d agua h (m)':h,
                     'Volume (m3)':V,'Deslocamento (t)':rho*V,
                     'yB (m)':yB,'KB inclinado (m)':zB,
                     'GZ (m)':gz,'Momento (t.m)':rho*V*gz,
                     'KG (m)':kg,'TCG (m)':tcg,'Densidade (t/m3)':rho})
    return pd.DataFrame(rows),V0


def gm_inicial(x,z,Y,calado,kg):
    """GM de pequena banda na linha d'agua direita: KB + I_T/V - KG."""
    x=np.asarray(x,float); z=np.asarray(z,float); Y=np.asarray(Y,float)
    x,z,secs=_sections(x,z,Y)
    V,M_y,M_z=_hydro(x,secs,0.,calado)
    if V<=0: return np.nan
    # Interpolacao das meias-bocas na linha d agua de cada baliza.
    half=np.array([np.interp(calado,z,yi) for yi in Y])
    f=np.trapezoid if hasattr(np,'trapezoid') else np.trapz
    IT=float(f(2*half**3/3,x))
    return M_z/V+IT/V-kg


def barcaca(L=12.,B=4.,D=5.,n_x=13,n_z=21):
    x=np.linspace(0,L,n_x); z=np.linspace(0,D,n_z)
    return x,z,np.full((n_x,n_z),B/2)


def gz_analitico_barcaca(B,T,KG,angulos):
    """Exato para secoes retangulares SEM emersao de fundo/imersao de conves.
    Requer 0 < T-(B/2)tan(theta) e T+(B/2)tan(theta) < D.
    """
    th=np.radians(np.asarray(angulos,float)); tan=np.tan(th)
    yb=B**2*tan/(12*T)
    zb=T/2+B**2*tan**2/(24*T)
    return yb*np.cos(th)+(zb-KG)*np.sin(th)


def validar_barcaca():
    L,B,D,T,KG=12.,4.,5.,2.,1.6
    a=np.array([0.,5.,10.,15.,20.])
    x,z,Y=barcaca(L,B,D)
    df,_=calcular(x,z,Y,T,KG,1.,a)
    ref=gz_analitico_barcaca(B,T,KG,a)
    df['GZ analitico (m)']=ref
    df['Erro absoluto (m)']=np.abs(df['GZ (m)']-ref)
    df['Erro percentual (%)']=np.where(np.abs(ref)>1e-5,100*df['Erro absoluto (m)']/np.maximum(np.abs(ref),1e-5),np.nan)
    return df


def comparar(df, referencia):
    """Referencia externa: colunas angulo e gz; interpolacao apenas no intervalo disponivel."""
    ref=referencia.copy()
    if not {'Angulo (graus)','GZ referencia (m)'}.issubset(ref.columns):
        raise ValueError('Referencia exige colunas Angulo (graus) e GZ referencia (m).')
    ref=ref[['Angulo (graus)','GZ referencia (m)']].dropna().sort_values('Angulo (graus)')
    if len(ref)<2 or ref['Angulo (graus)'].duplicated().any():
        raise ValueError('Informe pelo menos 2 angulos distintos na referencia.')
    a=df['Angulo (graus)'].to_numpy(); r=ref['Angulo (graus)'].to_numpy()
    out=df.loc[(a>=r.min())&(a<=r.max()),['Angulo (graus)','GZ (m)']].copy()
    if out.empty: raise ValueError('Nao ha angulos comuns para comparacao.')
    out['GZ referencia (m)']=np.interp(out['Angulo (graus)'],r,ref['GZ referencia (m)'])
    out['Diferenca absoluta (m)']=abs(out['GZ (m)']-out['GZ referencia (m)'])
    out['Diferenca percentual (%)']=np.where(abs(out['GZ referencia (m)'])>=1e-5,
      100*out['Diferenca absoluta (m)']/np.maximum(abs(out['GZ referencia (m)']),1e-5),np.nan)
    return out
