# -*- coding: utf-8 -*-
"""Interface AP1.3: calculo real da geometria submersa sob banda."""
import io
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import streamlit as st
from hidro import gz as GZ
from .comum import principais,opcoes


def _plot(df,ref=None):
    fig,ax=plt.subplots(figsize=(9,4.6))
    xx=df['Angulo (graus)'].to_numpy(); yy=df['GZ (m)'].to_numpy()
    ax.plot(xx,yy,'o-',label='GZ calculado')
    ax.fill_between(xx,yy,0,where=yy>=0,alpha=.16,color='green')
    ax.fill_between(xx,yy,0,where=yy<0,alpha=.16,color='red')
    im=int(np.argmax(yy)); ax.scatter([xx[im]],[yy[im]],s=90,marker='*',label=f'Max {yy[im]:.4f} m a {xx[im]:.1f}°')
    if ref is not None: ax.plot(ref['Angulo (graus)'],ref['GZ referencia (m)'],'s--',label='Referencia')
    ax.axhline(0,color='black',linewidth=.7); ax.set(xlabel='Angulo de banda (graus)',ylabel='GZ (m)',title='Curva de estabilidade estatica transversal')
    ax.grid(alpha=.25); ax.legend(); fig.tight_layout(); return fig


def render():
    st.title('AP1.3 — Curva de estabilidade estatica transversal GZ')
    st.write('Calcula a intersecao de cada secao transversal com o plano d agua inclinado, integra o volume e o centro de carena e resolve a imersao para manter o deslocamento constante.')
    tab=st.session_state.get('tab'); p=principais(); opt=opcoes()
    modo=st.radio('Geometria', ['Tabela de cotas AP1.1','Barcaca retangular de demonstracao'],horizontal=True)
    if modo.startswith('Tabela'):
        if tab is None:
            st.warning('Carregue e preencha uma tabela de cotas na etapa 2 ou selecione a barcaca de demonstracao.')
            return
        x,z,Y=tab.x,tab.z,tab.Y
        st.caption(f'{len(x)} balizas, {len(z)} linhas d agua. Modelo simetrico em torno do plano diametral.')
    else:
        a,b,c=st.columns(3)
        L=a.number_input('Comprimento L (m)',min_value=.1,value=12.)
        B=b.number_input('Boca B (m)',min_value=.1,value=4.)
        D=c.number_input('Pontal D (m)',min_value=.1,value=5.)
        x,z,Y=GZ.barcaca(L,B,D)
    c1,c2,c3=st.columns(3)
    t_default=min(max(float(st.session_state.get('T_sel') or p.get('Td') or z[-1]/2),.001),float(z[-1])*.99)
    T=c1.number_input('Calado de referencia (m)',min_value=.001,max_value=float(z[-1])*.999,value=t_default,format='%.4f')
    kg_default=max(0.,float(opt.get('KG',0) or 0))
    soma=st.session_state.get('soma')
    if isinstance(soma,dict) and np.isfinite(soma.get('KG',np.nan)):
        kg_default=float(soma['KG'])
    KG=c2.number_input('KG (m)',min_value=0.,value=kg_default,format='%.4f')
    rho=c3.number_input('Densidade (t/m3)',min_value=.1,max_value=2.,value=float(opt.get('rho',1.025)),format='%.4f')
    a,b,c=st.columns(3)
    fim=a.slider('Angulo maximo (graus)',60,85,60,5)
    passo=b.select_slider('Incremento angular (graus)',options=[1,2,5],value=5)
    TCG=c.number_input('TCG (m) (boreste positivo)',value=0.,format='%.4f')
    try:
        base,_=GZ.calcular(x,z,Y,T,KG,rho,np.array([0.]))
        desl_0=float(base['Deslocamento (t)'].iloc[0])
        st.caption(f'Deslocamento correspondente ao calado de referencia: {desl_0:.5f} t')
        usar_massa=st.checkbox('Informar deslocamento diferente do calculado a partir do calado')
        desloc=st.number_input('Deslocamento desejado (t)',min_value=.000001,value=desl_0,format='%.5f') if usar_massa else None
        ang=np.arange(0.,fim+1e-8,float(passo))
        if ang[-1]!=fim: ang=np.r_[ang,float(fim)]
        df,V0=GZ.calcular(x,z,Y,T,KG,rho,ang,desloc,TCG)
        gm=GZ.gm_inicial(x,z,Y,T,KG) if desloc is None and abs(TCG)<1e-12 else np.nan
    except Exception as e:
        st.error(f'Nao foi possivel calcular GZ: {e}')
        return
    st.session_state['gz_resultado']=df
    im=df['GZ (m)'].idxmax()
    c1,c2,c3,c4=st.columns(4)
    c1.metric('GZ maximo (m)',f"{df.loc[im,'GZ (m)']:.5f}")
    c2.metric('Angulo GZ max (°)',f"{df.loc[im,'Angulo (graus)']:.1f}")
    c3.metric('GM inicial (m)',f'{gm:.5f}' if np.isfinite(gm) else 'Nao aplicavel')
    c4.metric('Deslocamento (t)',f"{df['Deslocamento (t)'].iloc[0]:.4f}")
    fig=_plot(df); st.pyplot(fig); plt.close(fig)
    st.dataframe(df,hide_index=True,use_container_width=True)
    st.download_button('Baixar CSV da curva',df.to_csv(index=False).encode('utf-8-sig'),'AP13_curva_GZ.csv','text/csv')
    bio=io.BytesIO()
    with pd.ExcelWriter(bio,engine='openpyxl') as wr:
        df.to_excel(wr,sheet_name='GZ calculado',index=False)
        pd.DataFrame([{'Geometria':modo,'Calado m':T,'KG m':KG,'TCG m':TCG,'Rho t/m3':rho,'Deslocamento t':df['Deslocamento (t)'].iloc[0]}]).to_excel(wr,sheet_name='Parametros',index=False)
    st.download_button('Baixar Excel com parametros',bio.getvalue(),'AP13_curva_GZ.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    st.subheader('Validacao 1 — barcaca retangular e solucao analitica')
    val=GZ.validar_barcaca(); st.dataframe(val[['Angulo (graus)','GZ (m)','GZ analitico (m)','Erro absoluto (m)','Erro percentual (%)']],hide_index=True,use_container_width=True)
    st.caption('Barcaca L=12 m, B=4 m, D=5 m, T=2 m, KG=1,6 m; angulos 0°, 5°, 10°, 15°, 20°. Percentual indefinido quando GZ de referencia e quase zero.')
    st.download_button('Baixar validacao 1',val.to_csv(index=False).encode('utf-8-sig'),'AP13_validacao_1.csv','text/csv')
    st.subheader('Validacao 2 — importar resultados externos (Maxsurf ou referencia publicada)')
    st.write('Exporte do software de referencia um CSV com colunas **Angulo (graus)** e **GZ referencia (m)**, usando o mesmo casco, massa, KG, TCG e densidade. A comparacao fica pendente ate voce fornecer esses valores.')
    upload=st.file_uploader('CSV da referencia externa',type=['csv'],key='ref_gz')
    if upload is not None:
        try:
            try: ref=pd.read_csv(upload,sep=None,engine='python')
            except Exception: upload.seek(0);ref=pd.read_csv(upload,sep=';')
            comparado=GZ.comparar(df,ref)
            st.dataframe(comparado,hide_index=True,use_container_width=True)
            fig2=_plot(df,comparado);st.pyplot(fig2);plt.close(fig2)
            st.download_button('Baixar comparacao',comparado.to_csv(index=False).encode('utf-8-sig'),'AP13_validacao_2.csv','text/csv')
        except Exception as e: st.error(f'Arquivo de referencia invalido: {e}')
    st.info('Limitacoes: casco simetrico representado por tabela de meias-bocas; secao linear entre cotas; sem trim, adernamento dinamico, superfice livre, alagamento progressivo ou aberturas de downflooding. GZ nao substitui avaliacao regulamentar completa.')
