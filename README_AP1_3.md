# AP1.3 — Estabilidade estática transversal

## O que foi acrescentado
- Nova etapa no aplicativo: **10. Estabilidade estática transversal**.
- Núcleo de cálculo independente em `hidro/estabilidade.py`.
- Reutilização da tabela de cotas já carregada no AP1.1/AP1.2.
- Cálculo por ângulo da linha d'água de equilíbrio, volume, centro de carena global, GZ e momento endireitador.
- Gráfico com linha GZ=0, regiões positivas/negativas e indicação do GZ máximo.
- Exportação de resultados em CSV e Excel.
- Testes automatizados e um relatório PDF de validação analítica simplificada.

## Como executar
1. Instale as dependências de `requirements.txt`.
2. No terminal, entre nesta pasta e execute `streamlit run app.py`.
3. Carregue e confira a tabela de cotas nas etapas iniciais.
4. Abra **10. Estabilidade estática transversal**, informe calado, KG e densidade, e calcule.
5. Para executar os testes AP1.3: `python testes_ap13_estabilidade.py`.

## Validação e pendências acadêmicas
O caso de barcaça prismática testa a conservação de volume e compara GM/GZ de pequenas bandas com as relações analíticas. O relatório é `Relatorio_validacao_AP1_3.pdf` e a tabela de resultados é `validacao_ap13_barcaça_analitica.csv`.

**A comparação externa com Maxsurf Stability ainda não está preenchida.** Para concluí-la, é necessário executar no Maxsurf o mesmo casco e condição de carga e registrar os resultados exportados; não seria correto inventar essa referência. Inclua uma tabela por ângulo com GZ do aplicativo, GZ do Maxsurf, erro absoluto e erro relativo, e explique diferenças de discretização.

## Hipóteses e limitações
- Casco simétrico em relação ao plano diametral.
- Interpolação linear entre linhas d'água e fechamento do contorno no topo representado pela tabela.
- Integração longitudinal por trapézios.
- Volume conservado por busca binária da posição da linha d'água inclinada.
- Não inclui superfícies livres, alagamento, compartimentação, aberturas nem superestruturas que não estejam representadas na tabela de cotas.
- A precisão depende da qualidade e resolução dos offsets e deve ser discutida na apresentação.
