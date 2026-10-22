# Alterações pontuais — AP1.3

## Arquivos modificados
- `app.py`: adiciona a tela de estabilidade transversal à navegação e à lista de módulos esperados.
- `hidro/__init__.py`: registra o módulo de estabilidade para carregamento pelo pacote existente.
- `requirements.txt`: limita Matplotlib à série principal 3.x, mantendo a dependência explícita para implantação.
- `README.md`: acrescenta instruções e limitações do AP1.3.

## Arquivos novos
- `hidro/estabilidade.py`: cálculo geométrico da curva GZ, com conservação do volume por busca da linha d'água.
- `interface/p11_estabilidade.py`: tela Streamlit do AP1.3, gráfico e exportação CSV/Excel.
- `testes_ap13_estabilidade.py`: cinco testes do núcleo de estabilidade.
- `README_AP1_3.md`: instruções específicas da etapa.
- `Relatorio_validacao_AP1_3.pdf`: relatório do caso analítico e das limitações.
- `validacao_ap13_barcaça_analitica.csv`: curva numérica de 0° a 30° para o caso de barcaça.
- `validacao_ap13_comparacao_analitica.csv`: comparação com GM·sen(θ) entre 0° e 5°.

## Verificações executadas
- Sintaxe Python: 28 arquivos analisados com `ast.parse`.
- Compilação: `app.py`, `hidro/estabilidade.py` e `interface/p11_estabilidade.py`.
- Testes AP1.3: 5 passaram.
- O teste geral `testes_nucleo.py` não pôde ser executado neste ambiente porque o pacote `streamlit` não está instalado no ambiente de verificação; o arquivo de dependências do projeto inclui Streamlit.

## Pendência
A comparação com Maxsurf Stability não foi fabricada nem marcada como concluída. Deve ser feita no software usando a mesma geometria, condição de carga, deslocamento, KG, densidade e ângulos.

## Implantação no Streamlit Cloud
O `requirements.txt` precisa estar no diretório de implantação junto ao `app.py`. Após enviar as alterações ao repositório, use a opção de reiniciar/reimplantar o app para forçar a instalação das dependências. Se o repositório tiver `app.py` na raiz, o `requirements.txt` também deve estar na raiz, não apenas em uma subpasta.
