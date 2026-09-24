# Aplicativo de Calculo Hidrostatico - AP1.1 + AP1.2

Transforma uma **tabela de cotas** em **propriedades hidrostaticas**, **Hydrostatic Table**
e **Hydrostatic Curves**, mostrando cada conta pelo caminho (AP1.1), e a partir dessa mesma
Hydrostatic Table resolve o **equilibrio longitudinal** de uma condicao de carga: calado
medio, momento de trim, compasso e os calados de popa e proa (AP1.2).

O AP1.2 e uma **extensao** do AP1.1, nao um programa separado. `LCB`, `LCF`, `MTC`, `KM` e
o calado **nunca sao digitados nem fixados no codigo**: todos saem da Hydrostatic Table
calculada pelo proprio aplicativo, por interpolacao. Resultados de software externo entram
somente na tela de validacao, para comparacao.

Filosofia: **DETECTAR -> EXPLICAR -> AVISAR -> APRESENTAR AS CONSEQUENCIAS -> O USUARIO DECIDE.**
Nada e corrigido em silencio, o arquivo importado nunca e alterado e toda decisao fica
registrada no historico e no relatorio.

## Instalacao e execucao

```bash
pip install -r requirements.txt
streamlit run app.py
```

Conferir o nucleo de calculo sem abrir a interface:

```bash
python testes_nucleo.py
```

## Organizacao dos arquivos

O programa esta dividido em modulos pequenos: para mexer numa formula, abra o arquivo
correspondente e nada mais precisa mudar.

```
app.py                      ponto de entrada: monta a pagina e chama a tela

hidro/                      CALCULO
  base.py                   constantes, leitura de numeros, unidades, historico
  leitura.py                abre o arquivo e descobre o layout da tabela de cotas
  tabela.py                 modelo da tabela, diagnostico geometrico, interpolacao
  integracao.py             Trapezio, Simpson 1/3 e Simpson 3/8 com auditoria
  hidrostatica.py           areas, volumes, centros, metacentro, coeficientes, WSA
  carga.py                  condicao de carga, superficie livre, MTC, trim, Ta e Tf
  graficos.py               plano de linhas, casco 3D, curvas, lamina d'agua inclinada
  relatorio.py              relatorio HTML e exportacao para Excel
  pdf.py                    relatorio final em PDF

interface/                  TELAS (uma por etapa)
  comum.py                  estado, barra lateral, widgets protegidos
  inicio.py                 abertura: formatos aceitos e roteiro
  p1_dados.py               1. dados do navio
  p2_cotas.py               2. tabela de cotas
  p3_geometria.py           3. conferir a geometria
  p4_metodos.py             4. metodos de calculo
  p5_calado.py              5. resultados no calado
  p6_curvas.py              6. tabela e curvas
  p7_validacao.py           7. validacao
  p9_carga.py               8. condicao de carga (AP1.2)
  p10_equilibrio.py         9. equilibrio e trim (AP1.2)
  p8_relatorio.py           relatorio final

exemplos/                   tabelas de cotas de teste, o mesmo casco em tres formatos
condicoes_de_carga/         seis condicoes de carga prontas para o AP1.2
testes_nucleo.py            validacao analitica e testes do nucleo
requirements.txt            dependencias
```

**Onde mexer em cada coisa:**

| Quero mudar | Arquivo |
|---|---|
| uma formula hidrostatica | `hidro/hidrostatica.py` |
| o trim, o MTC ou a superficie livre | `hidro/carga.py` |
| as regras de integracao | `hidro/integracao.py` |
| como um arquivo e lido | `hidro/leitura.py` |
| o aspecto de um grafico | `hidro/graficos.py` |
| o conteudo do relatorio | `hidro/relatorio.py` |
| o texto ou o layout de uma tela | o arquivo da tela em `interface/` |

## Formatos de tabela de cotas aceitos

Extensoes `.xlsx`, `.xlsm`, `.xls`, `.csv`, `.txt`, `.tsv`. Layouts reconhecidos:

- linhas d'agua nas colunas, balizas nas linhas (com ou sem linha de alturas z)
- linhas d'agua nas linhas, balizas nas colunas (transposta)
- altura embutida no rotulo da coluna, como `WL 2.5`
- tres colunas simples: `x`, `z`, `y`
- matriz sem cabecalho de texto
- virgula ou ponto decimal; separador `;` `,` tabulacao ou `|`

Se a leitura automatica errar, **tudo pode ser corrigido na etapa 2**: orientacao, primeira
e ultima linha e coluna, coluna do X, linha das alturas z, e as proprias alturas podem ser
digitadas na mao. Nenhuma alteracao no codigo-fonte e necessaria para processar uma
embarcacao desconhecida.

## Condicao de carga e equilibrio (AP1.2)

### A planilha de condicao de carga

Um arquivo `.xlsx` ou `.csv` com uma linha por item e, no minimo, as colunas
**Item**, **Peso (t)**, **LCG (m)** e **VCG (m)**. Colunas de momento (`W x LCG`),
uma linha de **TOTAL** e notas de rodape sao reconhecidas e **descartadas**, para que o
peso nao seja somado duas vezes; a tela lista o que foi ignorado. Colunas opcionais
`i (m4)` e `rho (t/m3)` alimentam a correcao de superficie livre.

A pasta `condicoes_de_carga/` traz seis condicoes prontas (leve, partida 100%, chegada 10%,
tanques 50%, carga a re e operacional equilibrada) para o casco Damen do exemplo. O arquivo
`_NAO_CARREGAR_resultados_esperados.xlsx` e apenas a **tabela de conferencia** com os
resultados de todas elas: nao e uma condicao de carga e o aplicativo o recusa se for
carregado por engano.

### A cadeia de calculo

1. Somatorio: `Delta = soma(w_i)`, `LCG = soma(w_i x_i)/Delta`, `KG = soma(w_i z_i)/Delta`.
2. Superficie livre: `GG_0 = soma(rho_i i_i)/Delta` e `KG_corrigido = KG + GG_0`.
3. Calado medio `T_0`: interpolado na Hydrostatic Table resolvendo `rho x Vol(T) = Delta`,
   com refinamento opcional por bisseccao no proprio casco.
4. `LCB`, `LCF`, `BM_l` e `KM_t` interpolados na mesma tabela, em `T_0`.
5. `MTC = Delta x BM_l / (100 L)` (aproximado) ou `Delta x GM_l / (100 L)` (exato).
6. Momento de trim e compasso: `M_trim = Delta (LCG - LCB)` e `t = M_trim / MTC`.
7. Calados nas perpendiculares, por **rotacao em torno do LCF** (nao da meia-nau):
   `T_a = T_0 - (LCF - x_AP)/L x t` e `T_f = T_0 + (x_FP - LCF)/L x t`.

### Convencao de sinais

`x` cresce da popa (AP) para a proa (FP), a mesma referencia da tabela de cotas.
`M_trim` positivo significa **LCG a vante do LCB**, ou seja **trim pela proa**, com
`T_f > T_a`. A convencao aparece escrita na tela de resultados e no relatorio.

A tela 9 desenha o perfil do casco com a **lamina d'agua inclinada** tracada entre
`(AP, T_a)` e `(FP, T_f)`, marcando LCB, LCF e LCG.

## Convencoes adotadas

- Calculos internos sempre em metros; a conversao de unidade e explicita e registrada.
- O calado `T` e medido a partir da primeira linha d'agua da tabela.
- `I_l` em relacao ao eixo transversal que passa pelo LCF (teorema dos eixos paralelos),
  que e a definicao correta para `BM_l`.
- A origem longitudinal de apresentacao de LCB e LCF e escolhida na etapa 1; o calculo
  interno usa sempre o `x` do arquivo.
- Sem coluna X no arquivo, as posicoes vem de `h = LPP / (n_balizas - 1)`.
- `WSA` pelo semi-perimetro molhado: `s_i = y(z_base) + soma de raiz(dy^2 + dz^2)`,
  `WSA = 2 * integral de s dx`. Nao inclui popa espelhada, apendices, leme nem helice.

## Validacao

`testes_nucleo.py` compara o aplicativo com **duas solucoes analiticas exatas**:

- barcaca paralelepipedica 40 x 10 x 5 m, T = 2 m: `Vol = LBT`, `KB = T/2`,
  `LCB = LCF = L/2`, `A_WP = LB`, `BM_t = B^2/12T`, `C_B = C_WP = C_M = C_P = 1`,
  `WSA = LB + 2LT`. Erro maximo obtido: **2,8e-14 %**.
- prisma triangular: confirma `KB = 2T/3`, `C_M = 0,5` e o valor exato de `I_t`.

Tambem verifica a exatidao das tres regras de integracao, a leitura de sete formatos de
arquivo e o comportamento das curvas.

Para o AP1.2, os testes confirmam na barcaca analitica que: LCG na meia-nau da compasso
nulo; deslocar o LCG para vante e para re da compassos iguais e opostos; `T_f - T_a` e
exatamente o compasso; o calado medio em `LCF` se mantem igual a `T_0`; e o `MTC` confere
com `rho B L^2 / 1200`. A leitura da condicao de carga e testada contra linha de TOTAL,
coluna de momento, nota de rodape e tabela de resultados carregada por engano.

Dentro do aplicativo, a etapa 7 traz a consistencia interna (`Vol` pelos dois caminhos,
`KM = KB + BM`, `C_B = C_M x C_P`, `Delta = rho x Vol`) e a comparacao com um software de
referencia.

## Limitacoes conhecidas

- A geometria e reconstruida por interpolacao linear entre pontos discretos.
- Simpson exige passo constante; em trechos irregulares o aplicativo usa o Trapezio e
  registra isso na auditoria. O mesmo vale para o ultimo trecho quando o calado cai entre
  duas linhas d'agua.
- O volume abaixo da primeira linha d'agua e acima da ultima depende da hipotese escolhida.
- O modelo 3D e ilustrativo e nao substitui software de modelagem naval.
- O equilibrio do AP1.2 e **longitudinal**: resolve o trim, nao a banda. Supoe pequenos
  angulos, `MTC` constante entre `T_a` e `T_f` e carena nao muito diferente da direita.
  Para compassos grandes o resultado deve ser conferido com equilibrio iterativo.
- A verificacao interna `E_vol` fica na ordem de `1e-14` porque os dois caminhos de volume
  sao a mesma soma dupla em ordem trocada: ela valida a **implementacao**, nao a
  discretizacao da malha. A comparacao com a solucao analitica e com o software de
  referencia e que mede o erro de discretizacao.
