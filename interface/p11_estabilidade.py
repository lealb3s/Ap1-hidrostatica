# -*- coding: utf-8 -*-
"""Interface AP1.3 - estabilidade estatica transversal."""
import io
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import hidro.estabilidade as E
from . import comum


def render():
    st.title('10. Estabilidade estática transversal — AP1.3')
    st.caption('Curva GZ por recálculo geométrico do volume submerso em cada ângulo de banda.')
    if not comum.exige_completa(): return
    tab=st.session_state.tab
    opt=st.session_state.get('opt',{})
    p=st.session_state.get('principais',{})
    c1,c2,c3=st.columns(3)
    with c1:
        maxcal=float(np.nanmax(tab.z)-np.nanmin(tab.z))
        calado=st.number_input('Calado inicial (m)', min_value=0.01, max_value=max(0.02,maxcal), value=float(min(max(st.session_state.get('T_sel',1.0),0.01),max(0.02,maxcal))), step=0.05, key='gz_calado')
    with c2:
        kg0=opt.get('KG',0.0)
        kg0=float(kg0) if kg0 is not None and np.isfinite(kg0) else 0.0
        kg=st.number_input('KG — altura do centro de gravidade (m)',min_value=0.0,value=max(0.0,kg0),step=0.05,key='gz_kg')
    with c3:
        rho0=float(opt.get('rho',1.025) or 1.025)
        rho=st.number_input('Densidade (t/m³)',min_value=0.1,max_value=2.0,value=rho0,step=0.005,format='%.3f',key='gz_rho')
    c4,c5=st.columns(2)
    with c4:
        angmax=st.select_slider('Ângulo máximo de banda',options=[10,15,20,25,30,35,40,45,50,55,60],value=60,key='gz_angmax')
    with c5:
        passo=st.select_slider('Incremento angular (graus)',options=[1,2,2.5,5],value=5,key='gz_passo')
    st.info('Convenção: tabela de cotas em metros, meias-bocas positivas, casco simétrico e centro de gravidade sobre o plano diametral. O cálculo conserva o volume inicial ao inclinar o casco.')
    if st.button('Calcular curva GZ',type='primary',**comum.W()):
        try:
            angulos=np.arange(0,float(angmax)+1e-8,float(passo))
            df,res=E.curva_gz(tab,float(calado),float(kg),float(rho),angulos)
            st.session_state['gz_df']=df; st.session_state['gz_resumo']=res
            st.session_state['gz_config']={'calado':calado,'KG':kg,'rho':rho,'angmax':angmax,'passo':passo,'arquivo':st.session_state.get('arquivo_nome','tabela carregada')}
        except Exception as exc:
            st.error(f'Não foi possível calcular a curva: {type(exc).__name__}: {exc}')
            st.caption('Confira a origem vertical e a faixa de alturas da tabela de cotas, além do calado informado.')
    df=st.session_state.get('gz_df')
    res=st.session_state.get('gz_resumo')
    if df is None or res is None:
        st.markdown('**Fluxo de uso:** carregue a tabela de cotas nas etapas anteriores, confira se as meias-bocas estão completas e informe o KG da condição de carga.')
        return
    m1,m2,m3,m4=st.columns(4)
    m1.metric('Volume de referência',f"{res['volume_ref_m3']:.3f} m³")
    m2.metric('Deslocamento',f"{res['deslocamento_ref_t']:.3f} t")
    m3.metric('GM inicial estimado',f"{res['GM_inicial_m']:.3f} m")
    m4.metric('GZ máximo',f"{res['GZ_max_m']:.3f} m",f"em {res['angulo_GZ_max_graus']:.1f}°")
    fig=go.Figure()
    fig.add_hrect(y0=0,y1=max(float(df['GZ (m)'].max()),0.01),fillcolor='green',opacity=.06,line_width=0)
    fig.add_hrect(y0=min(float(df['GZ (m)'].min()),-0.01),y1=0,fillcolor='red',opacity=.06,line_width=0)
    fig.add_hline(y=0,line_color='gray',line_dash='dash')
    fig.add_trace(go.Scatter(x=df['Angulo (graus)'],y=df['GZ (m)'],mode='lines+markers',name='GZ',line=dict(width=3)))
    imax=int(df['GZ (m)'].idxmax())
    fig.add_trace(go.Scatter(x=[df.loc[imax,'Angulo (graus)']],y=[df.loc[imax,'GZ (m)']],mode='markers+text',text=['GZ máximo'],textposition='top center',name='Máximo',marker=dict(size=10)))
    fig.update_layout(title='Curva de estabilidade estática transversal',xaxis_title='Ângulo de banda (graus)',yaxis_title='Braço de endireitamento GZ (m)',height=520,legend=dict(orientation='h'))
    st.plotly_chart(fig,**comum.W())
    st.caption('Região GZ > 0: braço restaurador segundo a convenção adotada. Região GZ < 0: braço desestabilizante. GM é estimado numericamente pelo primeiro ângulo positivo e deve ser interpretado como aproximação de pequena banda.')
    st.subheader('Tabela de resultados')
    st.dataframe(df,hide_index=True,**comum.W())
    csv=df.to_csv(index=False).encode('utf-8-sig')
    out=io.BytesIO()
    with pd.ExcelWriter(out,engine='openpyxl') as writer:
        df.to_excel(writer,index=False,sheet_name='Curva_GZ')
        pd.DataFrame([res]).to_excel(writer,index=False,sheet_name='Resumo')
        pd.DataFrame([st.session_state.get('gz_config',{})]).to_excel(writer,index=False,sheet_name='Entradas')
    c1,c2=st.columns(2)
    with c1: st.download_button('Exportar resultados CSV',data=csv,file_name='curva_GZ_AP1_3.csv',mime='text/csv',**comum.W())
    with c2: st.download_button('Exportar resultados Excel',data=out.getvalue(),file_name='curva_GZ_AP1_3.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',**comum.W())
    st.subheader('Notas metodológicas e limitações')
    st.markdown('''
- A tabela de cotas é interpretada como seções transversais simétricas; entre linhas d’água, as meias-bocas são interpoladas linearmente.
- A área de cada seção é recortada pela linha d’água inclinada e integrada ao longo de X pelo método dos trapézios.
- Para cada ângulo, a linha d’água é ajustada iterativamente até recuperar o volume de referência.
- O centro de carena é recalculado a cada ângulo; não se usa apenas a expressão simplificada `GZ = GM·sen(θ)`.
- A qualidade depende da resolução da tabela, do fechamento do casco na quilha e no convés e da ausência de geometrias não representadas (aberturas, superestruturas, tanques livres etc.). Para entrega acadêmica, documente a comparação com cálculo analítico e/ou Maxsurf Stability.
''')
