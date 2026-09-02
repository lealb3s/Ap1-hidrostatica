# Aplicativo de Calculo Hidrostatico - AP1.1

Transforma uma **tabela de cotas** em **propriedades hidrostaticas**, **Hydrostatic Table**
e **Hydrostatic Curves**, mostrando cada conta pelo caminho.

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
  graficos.py               plano de linhas, casco 3D, curvas
  relatorio.py              relatorio HTML e exportacao para Excel

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
  p8_relatorio.py           relatorio final

exemplos/                   tabelas de cotas de teste, o mesmo casco em tres formatos
testes_nucleo.py            validacao analitica e testes do nucleo
requirements.txt            dependencias
```

**Onde mexer em cada coisa:**

| Quero mudar | Arquivo |
|---|---|
| uma formula hidrostatica | `hidro/hidrostatica.py` |
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
