# Aplicativo de Cálculo Hidrostático — AP1.1

Aplicativo que transforma uma **tabela de cotas** em **propriedades hidrostáticas**,
**Hydrostatic Table** e **Hydrostatic Curves**, com auditoria completa de cada etapa.

Filosofia adotada: **DETECTAR → EXPLICAR → AVISAR → APRESENTAR AS CONSEQUÊNCIAS → O USUÁRIO DECIDE.**
Nada é corrigido em silêncio, o arquivo importado nunca é modificado e toda decisão fica
registrada no histórico e no relatório.

---

## 1. Requisitos

- **Python 3.10 ou superior** (testado em 3.12)
- Bibliotecas listadas em `requirements.txt`:
  `streamlit`, `numpy`, `pandas`, `matplotlib`, `openpyxl` e `xlrd` (este último só é
  necessário para abrir arquivos `.xls` antigos)

Nenhuma biblioteca entrega propriedades hidrostáticas prontas. As regras de integração
(Trapézio, Simpson 1/3 e Simpson 3/8) e todo o algoritmo hidrostático estão implementados
diretamente no código, na seção `S5` e `S6` do `app.py`.

## 2. Instalação

```bash
pip install -r requirements.txt
```

## 3. Execução

```bash
streamlit run app.py
```

O navegador abre automaticamente em `http://localhost:8501`.

Para conferir o núcleo de cálculo sem abrir a interface:

```bash
python testes.py
```

Os testes comparam o aplicativo com **duas soluções analíticas exatas** (barcaça
paralelepipédica e casco em V prismático), verificam a exatidão das regras de integração,
a leitura de sete formatos diferentes de tabela de cotas e o comportamento das curvas.

## 4. Estrutura do código

O aplicativo é um **arquivo único** (`app.py`), dividido em seções marcadas com `S`:

| Seção | Conteúdo |
|-------|----------|
| `S0`  | Imports, constantes e lista das propriedades |
| `S1`  | Utilitários: leitura de números, unidades, histórico e auditoria |
| `S2`  | Leitura de arquivos e **detecção automática do layout** da tabela de cotas |
| `S3`  | Modelo canônico da tabela e **diagnóstico geométrico** |
| `S4`  | Interpolação linear auditável |
| `S5`  | **Integração numérica**: Trapézio, Simpson 1/3, Simpson 3/8 e auditoria por trecho |
| `S6`  | Núcleo hidrostático: áreas, plano d'água, volumes, centros, metacentro, coeficientes e WSA |
| `S7`  | Hydrostatic Table, consulta numérica e validações |
| `S8`  | Gráficos: plano de linhas, seções, curvas e 3D |
| `S9`  | Relatório HTML e exportações |
| `S10` | Interface Streamlit (Módulos 1 a 7) |

## 5. Módulos do aplicativo

1. **Módulo 1 — Projeto e dados**: dados principais, densidade, referências, unidades,
   importação ou digitação da tabela de cotas e seleção dos cálculos.
2. **Módulo 2 — Geometria e validação**: tabela de trabalho editável, verificação
   automática, plano de linhas e casco 3D.
3. **Módulo 3 — Interpolação e integração**: preenchimento de lacunas com registro de
   método, pontos usados e valor obtido; escolha e auditoria das regras de integração.
4. **Módulo 4 — Cálculo hidrostático**: propriedades para um calado escolhido no slider,
   com a função obrigatória **MOSTRAR CÁLCULO** (dados, fórmula, valores intermediários,
   resultado e unidade).
5. **Módulo 5 — Hydrostatic Table**: varredura de T_min a T_max com passo ΔT, exportável
   para Excel.
6. **Módulo 6 — Hydrostatic Curves**: as 15 curvas obrigatórias, diagrama combinado e
   consulta numérica de qualquer ponto.
7. **Módulo 7 — Validação e auditoria**: validação analítica, consistência interna,
   comparação com o Maxsurf e histórico completo.
8. **Relatório final**: documento HTML único com todo o procedimento.

## 6. Formatos de tabela de cotas aceitos

Extensões: `.xlsx`, `.xlsm`, `.xls`, `.csv`, `.txt`, `.tsv`.

Layouts reconhecidos automaticamente:

- **Linhas d'água nas colunas** e balizas nas linhas, com ou sem linha de alturas `z`
- **Linhas d'água nas linhas** (tabela transposta)
- Altura embutida no rótulo da coluna (`WL 2.5`)
- **Formato longo** com três colunas: `x`, `z`, `y`
- Matriz sem cabeçalho de texto
- Vírgula ou ponto decimal, separador `;` `,` tabulação ou `|`

Se a detecção automática errar, **tudo pode ser corrigido na própria interface**
(orientação, coluna de X, linha de alturas `z`, primeira e última linha e coluna, unidade).
Nenhuma alteração no código-fonte é necessária para processar um casco desconhecido.

Há quatro arquivos de teste em `exemplos/`, o mesmo casco gravado em três layouts
diferentes mais a barcaça de validação analítica.

## 7. Convenções adotadas

- Cálculos internos sempre em **SI (metros)**; a conversão de unidade é explícita e registrada.
- O calado `T` é medido a partir da **primeira linha d'água da tabela** (`z_base`). Se ela
  não estiver em `z = 0`, o aplicativo avisa.
- `I_l` é calculado em relação ao **eixo transversal que passa pelo LCF** (teorema dos
  eixos paralelos), que é a definição correta para `BM_l`. Há a opção pela meia-nau apenas
  para comparação.
- A origem longitudinal de apresentação de LCB e LCF é escolhida pelo usuário
  (como no arquivo, perpendicular de ré ou meia-nau); o cálculo interno usa sempre o `x`
  da tabela.
- Quando não existe coluna X no arquivo, as posições são geradas com
  `h = LPP / (n_estações − 1)`.
- **WSA** pelo método do semi-perímetro molhado: `s_i = y(z_base) + Σ √(Δy² + Δz²)` e
  `WSA = 2 ∫ s dx`. Não inclui popa espelhada, apêndices, leme nem hélice.
- **ERRO** impede o cálculo; **AVISO** permite continuar mediante confirmação explícita,
  que fica registrada no histórico.

## 8. Validação

**Validação 1 — solução analítica.** Barcaça 40 × 10 × 5 m, T = 2 m:
`∇ = LBT`, `KB = T/2`, `LCB = LCF = L/2`, `A_WP = LB`, `BM_t = B²/12T`,
`C_B = C_WP = C_M = C_P = 1`, `WSA = LB + 2LT`.
Erro máximo obtido: **2,8 × 10⁻¹⁴ %**.

Um segundo casco analítico (prisma triangular) confirma `KB = 2T/3`, `C_M = 0,5`
e o valor exato de `I_t`.

**Validação 2 — consistência interna.** Volume longitudinal × vertical, `KM = KB + BM`,
`C_B = C_M·C_P`, `Δ = ρ∇` e a contagem de dados interpolados, tudo no Módulo 7.

**Validação 3 — Maxsurf.** No Módulo 7 informe os valores obtidos no Maxsurf em três
condições (calado baixo, intermediário e de projeto); o aplicativo calcula os próprios
valores nos mesmos calados e monta a tabela de erros percentuais.

## 9. Limitações conhecidas

- A geometria é reconstruída por interpolação linear entre pontos discretos: quanto menos
  estações e linhas d'água, maior o erro de discretização.
- As regras de Simpson exigem passo constante; em trechos irregulares o aplicativo usa o
  Trapézio e isso aparece na auditoria.
- O volume abaixo da primeira linha d'água e acima da última depende da hipótese escolhida
  no Módulo 3.
- O modelo 3D é ilustrativo e **não substitui software de modelagem naval**.
