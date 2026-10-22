# -*- coding: utf-8 -*-
"""AP1.3 — curva de estabilidade estática transversal GZ.

O casco é reconstruído a partir da tabela de cotas (meias-bocas por baliza e WL).
Para cada banda, a superfície livre é z*cos(phi)-y*sin(phi)=c. O volume e os
momentos do volume submerso são integrados numericamente em células da malha
(y,z) e ao longo de x; c é ajustado por bisseção para conservar o deslocamento.
"""
import io
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from types import SimpleNamespace


def _interpoladores(tab, T, ny=91, nz=81, nx=41):
    """Malha 3D aproximada por seções transversais e quadratura de células."""
    x = np.linspace(float(tab.x[0]), float(tab.x[-1]), nx)
    z0 = float(tab.z[0]); z1 = float(tab.z[-1])
    if len(tab.x) < 2 or len(tab.z) < 2 or z1 <= z0:
        raise ValueError('A geometria precisa ter ao menos duas balizas e duas linhas d’água ordenadas.')
    if np.any(np.diff(tab.x) <= 0) or np.any(np.diff(tab.z) <= 0):
        raise ValueError('Ordene as balizas e as linhas d’água em ordem crescente antes de calcular GZ.')
    if not np.isfinite(tab.Y).all():
        raise ValueError('A tabela de cotas contém células vazias. Complete e valide a geometria antes de calcular GZ.')
    z_nodes = np.linspace(z0, z1, nz)
    ymax = float(np.max(tab.Y))
    if not np.isfinite(ymax) or ymax <= 0:
        raise ValueError('A tabela não contém meias-bocas positivas válidas.')
    y = np.linspace(-ymax, ymax, ny)
    # usar centros de células reduz os saltos da função indicadora
    dy = float(y[1]-y[0]); dz = float(z_nodes[1]-z_nodes[0])
    yc = (y[:-1]+y[1:])/2; zc=(z_nodes[:-1]+z_nodes[1:])/2
    # A largura é avaliada nos centros das células, igual às coordenadas y e z.
    breadth = np.empty((nx, len(zc)))
    for j, xx in enumerate(x):
        sec = np.array([np.interp(xx, tab.x, tab.Y[:, k]) for k in range(tab.n_wl)])
        breadth[j,:] = np.interp(zc, tab.z, sec, left=sec[0], right=sec[-1])
    return x, yc, zc, breadth, dy*dz


def _curva_numerica(tab, T, KG, rho, angulos, ny=91, nz=81, nx=41, volume_alvo=None):
    x, y, z, b, dA = _interpoladores(tab,T,ny,nz,nx)
    # Pesos de integração longitudinal pela regra do trapézio. np.gradient(x)
    # atribui peso completo às extremidades e superestima o comprimento em 1
    # intervalo (erro que também contaminava o volume deslocado da AP1.3).
    dx = np.empty_like(x)
    dx[0] = (x[1] - x[0]) / 2.0
    dx[-1] = (x[-1] - x[-2]) / 2.0
    dx[1:-1] = (x[2:] - x[:-2]) / 2.0
    Y2=y[None,:,None]; Z2=z[None,None,:]
    dentro=np.abs(Y2) <= b[:,None,:]
    # coordenadas do centro de cada célula, no referencial solidário ao casco
    resultados=[]
    # volume máximo para estabelecer intervalo robusto de bisseção
    vol_max=float(np.sum(dentro*dA*dx[:,None,None]))
    # O volume-alvo é argumento explícito para permitir testar o cálculo fora da
    # interface e evitar que uma validação anterior contamine o cálculo seguinte.
    Vtarget = float(volume_alvo) if volume_alvo is not None else 0.0
    if Vtarget <= 0:
        # volume submerso de referência no calado informado, usando a mesma malha
        zbase=float(tab.z[0]); c0=(zbase+float(T))
        wet0=dentro & (Z2 <= c0)
        Vtarget=float(np.sum(wet0*dA*dx[:,None,None]))
    if Vtarget >= vol_max: raise ValueError('O deslocamento pedido excede o volume representado pela geometria e calado. Aumente o calado ou confira os dados.')
    for deg in angulos:
        th=np.deg2rad(float(deg)); q=Z2*np.cos(th)-Y2*np.sin(th)
        def integrals(c):
            wet=dentro & (q <= c)
            w=wet*dA*dx[:,None,None]
            return float(w.sum()), float((w*Y2).sum()), float((w*Z2).sum())
        lo=float(np.min(q)); hi=float(np.max(q))
        for _ in range(32):
            mid=(lo+hi)/2
            if integrals(mid)[0] < Vtarget: lo=mid
            else: hi=mid
        V, My, Mz=integrals((lo+hi)/2)
        yb=My/V if V else np.nan; kb=(Mz/V-float(tab.z[0])) if V else np.nan
        gz=yb*np.cos(th)+(kb-KG)*np.sin(th)
        # ao ângulo zero, a convenção geométrica dá GZ=0 (remove erro de malha)
        if abs(float(deg))<1e-10: gz=0.0
        resultados.append({'Ângulo de banda (°)':float(deg),'Volume deslocado (m³)':V,
          'YB (m)':yb,'KB (m)':kb,'GZ (m)':gz,
          'Momento de endireitamento (kN·m)':V*rho*9.80665*gz})
    df = pd.DataFrame(resultados)
    if not df.empty:
        yb0 = float(df.iloc[0]['YB (m)'])
        kb0 = float(df.iloc[0]['KB (m)'])
        df['Alteração YB (m)'] = df['YB (m)'] - yb0
        df['Alteração KB (m)'] = df['KB (m)'] - kb0
        # Organiza as colunas de modo que as alterações dos centros fiquem ao
        # lado dos valores absolutos, facilitando a leitura da AP1.3.
        df = df[['Ângulo de banda (°)', 'Volume deslocado (m³)', 'YB (m)',
                 'Alteração YB (m)', 'KB (m)', 'Alteração KB (m)', 'GZ (m)',
                 'Momento de endireitamento (kN·m)']]
    return df, Vtarget


def _validacao_barcaca():
    st.markdown('#### Validação 1 — barcaça prismática (referência analítica)')
    st.write('Para uma caixa prismática de paredes verticais, a fórmula de casco de paredes laterais (wall-sided) é usada como referência antes da imersão do convés: '
             '`GZ = sin(φ) [GM + 0,5·BM·tan²(φ)]`, com `BM = B²/(12T)`, `KB=T/2` e `GM=KB+BM−KG`.')
    c1,c2,c3,c4=st.columns(4)
    L=c1.number_input('Comprimento L (m)',min_value=1.0,value=10.0,step=1.0,key='vL')
    B=c2.number_input('Boca B (m)',min_value=0.5,value=4.0,step=0.5,key='vB')
    T=c3.number_input('Calado T (m)',min_value=0.2,value=1.5,step=0.1,key='vT')
    KG=c4.number_input('KG (m)',min_value=0.0,value=0.8,step=0.1,key='vKG')
    angles=np.arange(0,61,5,dtype=float); BM=B**2/(12*T); GM=T/2+BM-KG
    ref=np.sin(np.deg2rad(angles))*(GM+0.5*BM*np.tan(np.deg2rad(angles))**2)
    ref[0]=0
    st.caption(f'Volume = {L*B*T:.3f} m³; deslocamento em água de 1,025 t/m³ = {L*B*T*1.025:.3f} t; BM = {BM:.4f} m; GM = {GM:.4f} m. A fórmula é válida enquanto não houver imersão do convés/boorda.')
    if st.button('Executar comparação analítica da barcaça',key='gz_run_validation1'):
        # casco prismático com paredes verticais e altura acima do calado para permitir banda
        depth=max(3.0*T, T+2.0)
        fake=SimpleNamespace(x=np.array([0.,L/2,L]),z=np.array([0.,depth]),
            Y=np.full((3,2),B/2,dtype=float),n_wl=2,n_est=3)
        app_df,_=_curva_numerica(fake,T,KG,1.025,angles,ny=121,nz=121,nx=61,volume_alvo=None)
        comp=pd.DataFrame({'Ângulo (°)':angles,'GZ do aplicativo (m)':app_df['GZ (m)'].to_numpy(),'GZ analítico (m)':ref})
        comp['Diferença absoluta (m)']=(comp['GZ do aplicativo (m)']-comp['GZ analítico (m)']).abs()
        comp['Diferença percentual (%)']=np.where(np.abs(ref)>1e-6,comp['Diferença absoluta (m)']/np.abs(ref)*100,np.nan)
        st.dataframe(comp,hide_index=True,use_container_width=True)
        fig=go.Figure(); fig.add_scatter(x=angles,y=comp['GZ do aplicativo (m)'],mode='lines+markers',name='Aplicativo (malha numérica)'); fig.add_scatter(x=angles,y=ref,mode='lines+markers',name='Referência analítica'); fig.update_layout(xaxis_title='Ângulo (°)',yaxis_title='GZ (m)'); st.plotly_chart(fig,use_container_width=True)
        st.caption('A diferença resulta da discretização espacial e das hipóteses do modelo. Registre no relatório a resolução da malha e a faixa em que a fórmula analítica de paredes laterais é válida.')


def render():
    st.title('AP1.3 — Curva de estabilidade estática transversal (GZ)')
    st.write('A rotina recalcula o centro de carena para cada banda a partir da geometria submersa reconstruída da tabela de cotas, conservando o volume deslocado. Não usa `GZ = GM·sen(θ)` como curva completa.')
    tab=st.session_state.get('tab')
    if tab is None:
        st.warning('Carregue primeiro uma tabela de cotas na etapa **2. Tabela de cotas** e confira a geometria.')
        _validacao_barcaca(); return
    opt=st.session_state.get('opt',{})
    p=st.session_state.get('principais',{})
    maxT=min(float(tab.z[-1]-tab.z[0]),float(st.session_state.get('T_sel',1.0)))
    if maxT<=0: maxT=float(tab.z[-1]-tab.z[0])
    with st.expander('Dados de entrada',expanded=True):
        a,b,c,d=st.columns(4)
        T=a.number_input('Calado T (m)',min_value=0.05,max_value=float(tab.z[-1]-tab.z[0]),value=float(max(0.05,min(maxT,float(tab.z[-1]-tab.z[0])))),step=0.05)
        rho=b.number_input('Densidade da água (t/m³)',min_value=0.800,max_value=1.200,value=float(opt.get('rho',1.025)),step=0.005,format='%.3f')
        KG0=float(opt.get('KG',0.0) or 0.0)
        KG=c.number_input('KG (m, acima da linha de base)',min_value=0.0,max_value=float(tab.z[-1]-tab.z[0])+float(tab.z[0]),value=float(max(0,KG0)),step=0.05)
        modo=d.selectbox('Como definir o deslocamento',['Volume do casco até o calado','Informar deslocamento (t)'])
        desloc=d.number_input('Deslocamento (t)',min_value=0.01,value=float(max(0.01, float(opt.get('rho',1.025))*max(0.1,float(st.session_state.get('T_sel',1))*float(p.get('B',1))*float(p.get('LPP',1))))),step=0.1) if modo.startswith('Informar') else None
        c5,c6=st.columns(2)
        passo=c5.selectbox('Incremento angular',['5°','2,5°','1°'],index=0)
        nX=c6.selectbox('Resolução longitudinal',['31 estações','41 estações','61 estações'],index=1)
    ang=np.arange(0,60.0001,float(passo.replace(',','.')))
    if st.button('Calcular curva GZ',type='primary',use_container_width=True):
        try:
            # estimativa de volume em calado reto via hidrostatica existente
            vtarget=(float(desloc)/rho) if desloc is not None else 0.0
            if vtarget<=0 and desloc is not None: raise ValueError('Não foi possível determinar o volume deslocado. Confira o calado e a tabela.')
            df,vt=_curva_numerica(tab,T,KG,rho,ang,nx=int(nX.split()[0]),volume_alvo=vtarget or None)
            st.session_state['gz_df']=df; st.session_state['gz_inputs']={'T':T,'KG':KG,'rho':rho,'V':vt,'ang':ang.tolist(),'nx':int(nX.split()[0])}
        except Exception as e: st.error(f'Falha no cálculo: {e}')
    df=st.session_state.get('gz_df')
    if isinstance(df,pd.DataFrame) and not df.empty:
        inputs=st.session_state.get('gz_inputs',{})
        imax=int(df['GZ (m)'].idxmax()); maxgz=float(df.loc[imax,'GZ (m)']); maxang=float(df.loc[imax,'Ângulo de banda (°)'])
        st.subheader('Resultados principais')
        m1,m2,m3,m4=st.columns(4)
        m1.metric('Volume usado',f"{inputs.get('V',0):.3f} m³")
        gm_est = (float(df.iloc[1]['GZ (m)']) / np.sin(np.deg2rad(float(df.iloc[1]['Ângulo de banda (°)'])))
                   if len(df) > 1 and float(df.iloc[1]['Ângulo de banda (°)']) != 0 else float('nan'))
        m2.metric('GM inicial estimado', f'{gm_est:.3f} m',
                  help='Estimativa por GZ/sen(ângulo) no primeiro ângulo diferente de zero; confirme com KM−KG para pequenos ângulos.')
        m3.metric('GZ máximo amostrado',f'{maxgz:.4f} m')
        m4.metric('Ângulo do máximo',f'{maxang:.1f}°')
        fig=go.Figure(); fig.add_trace(go.Scatter(x=df['Ângulo de banda (°)'],y=df['GZ (m)'],mode='lines+markers',name='Curva GZ'))
        fig.add_hline(y=0,line_dash='dash',line_color='gray'); fig.add_trace(go.Scatter(x=[maxang],y=[maxgz],mode='markers+text',text=[f'Máx. {maxgz:.3f} m'],textposition='top center',name='GZ máximo'))
        fig.update_layout(xaxis_title='Ângulo de banda (°)',yaxis_title='Braço GZ (m)',hovermode='x unified',legend_orientation='h')
        st.plotly_chart(fig,use_container_width=True)
        st.caption('Valores positivos/negativos são apresentados em relação à convenção de banda adotada. O máximo é o maior valor entre os ângulos amostrados.')
        st.dataframe(df,use_container_width=True,hide_index=True)
        csv=df.to_csv(index=False).encode('utf-8-sig')
        out=io.BytesIO();
        with pd.ExcelWriter(out,engine='openpyxl') as w:
            df.to_excel(w,index=False,sheet_name='Curva GZ')
            pd.DataFrame([{'Calado (m)':inputs.get('T'),'KG (m)':inputs.get('KG'),'Densidade (t/m³)':inputs.get('rho'),'Volume-alvo (m³)':inputs.get('V'),'Método':'Integração numérica de células e bisseção da linha d’água'}]).to_excel(w,index=False,sheet_name='Entradas')
        cc1,cc2=st.columns(2)
        cc1.download_button('Exportar CSV',csv,file_name='curva_GZ_AP1.3.csv',mime='text/csv',use_container_width=True)
        cc2.download_button('Exportar Excel',out.getvalue(),file_name='curva_GZ_AP1.3.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',use_container_width=True)
    st.divider(); _validacao_barcaca()
    st.markdown('#### Validação 2 — comparação com referência externa')
    st.info('Para a comparação exigida com Maxsurf Stability ou uma referência publicada, use a mesma geometria, densidade, calado/deslocamento e KG. Exporte a curva e compare os valores por ângulo; o aplicativo não declara uma comparação externa como concluída sem importar os dados de referência.')
    ref_file=st.file_uploader('Opcional: importar CSV/XLSX de referência (colunas de ângulo e GZ)',type=['csv','xlsx'],key='gz_reference')
    if ref_file is not None and isinstance(st.session_state.get('gz_df'),pd.DataFrame):
        try:
            ref=pd.read_csv(ref_file,sep=None,engine='python') if ref_file.name.lower().endswith('.csv') else pd.read_excel(ref_file)
            st.write('Selecione as colunas correspondentes:')
            c1,c2=st.columns(2); ca=c1.selectbox('Coluna do ângulo',ref.columns,key='gz_ref_ang'); cg=c2.selectbox('Coluna GZ',ref.columns,key='gz_ref_gz')
            ours=st.session_state['gz_df']; merged=pd.merge(ours,ref,left_on='Ângulo de banda (°)',right_on=ca,how='inner')
            if len(merged):
                merged['Diferença absoluta (m)']=(merged['GZ (m)']-pd.to_numeric(merged[cg],errors='coerce')).abs()
                den=pd.to_numeric(merged[cg],errors='coerce').abs(); merged['Diferença percentual (%)']=np.where(den>1e-6,merged['Diferença absoluta (m)']/den*100,np.nan)
                st.dataframe(merged,use_container_width=True,hide_index=True)
                fig=go.Figure(); fig.add_scatter(x=merged['Ângulo de banda (°)'],y=merged['GZ (m)'],mode='lines+markers',name='Aplicativo'); fig.add_scatter(x=merged[ca],y=merged[cg],mode='lines+markers',name='Referência'); fig.update_layout(xaxis_title='Ângulo (°)',yaxis_title='GZ (m)'); st.plotly_chart(fig,use_container_width=True)
            else: st.warning('Nenhum ângulo coincidente. Confira as unidades e os intervalos angulares.')
        except Exception as e: st.error(f'Não foi possível ler a referência: {e}')
