# DATA_MAPPING — Inteligência de Fretes (Etapa 0)

Mapeamento dos dados logísticos no ERP Sisplan (Postgres 192.168.0.94, banco `15037P`, schema `sisplan`).
Levantado em 07/10/2026 com consultas somente leitura (`scripts/sisplan.sh`), a partir de:
o banco (catálogo e contagens), os logs de tela do Sisplan em `\\192.168.0.94\Sisplan\Agora`
(Relatório de Expedição TFMRELEXPPED, faturamento, relatório R10 "frete real x cotado") e o que a equipe confirmou.
Nada foi alterado no ERP.

## 1. Onde está cada informação

| Informação | Tabela.coluna (real) | Observação |
|---|---|---|
| Número do pedido | `pedido_001.numero` (= `pedido3_001.numero`, `frete_cota_001.pedido`, `notaiten_001.pedido`) | Texto de 5 dígitos ("44238"). Pedido de troca vem com `T` na frente em `pedido3_001`. |
| Cliente | `pedido_001.codcli` → `entidade_001` (`nome`, `fantasia`, `cnpj`) | `nota_001.codcli` também. |
| CEP de destino | `entidade_001.cep_ent`, senão `entidade_001.cep` | `nota_001.cli_cep` e `pedido_001.cli_cep` quase sempre vazios. |
| Cidade / UF | CEP → `cadcep_001.cep` → `cadcep_001.codmun` → `cidade.codigo` (`nome`, `cod_uf`) | |
| Região | **não existe** | `cidade.regiao` e `cadcep_001.regiao` vazios; `pedido_001.regiao_frete` vazio. Derivar da UF (regiões do IBGE). |
| CEP de origem | **não existe por embarque** | Sai sempre da fábrica: configurar uma vez. |
| Data de emissão | `pedido_001.dt_emissao` (pedido), `nota_001.dt_emissao` (nota) | |
| Data/hora da expedição | `pedido3_001.data` (dia) e `pedido3_001.hora_exp` (hora, por linha) | Fechamento do volume na expedição. |
| Saída da nota | `nota_001.dt_saida`, `nota_001.hr_saida` | 100% preenchidos. |
| Nota fiscal | `pedido3_001.notafiscal` = `nota_001.fatura` = `notaiten_001.fatura` | Fatura = nº da nota + série (ex.: `02824622` = NF 028246, série 22). |
| Valor da mercadoria | `nota_001.val_produtos` | Soma das notas do pedido. |
| Transportadora | `nota_001.transport` → `tabtran_001.codigo` (`nome`) | Ver regra 2.3. Também em `frete_cota_001.transp` e `pedido_001.tab_trans`. |
| Volumes (lista) | `pedido3_001`: uma linha por item dentro de cada volume; `caixa` = nº do volume | `caixa` é o "CX: 040708" da etiqueta. |
| Tipo e dimensões do volume | `pedido3_001.obs` (texto digitado) | Ex.: `FD: 52X42X93 CM`, `CX: 08X20X28 CM`, `FD: 105-62-34`. `caixa_001` vazia; `tcaixa`, `altura/largura/comprimento/cubagem` zerados. |
| Peso do volume | `pedido3_001.peso` (bruto, kg) e `peso_l` | Repetido em todas as linhas do volume. Inteiro na prática. |
| Qtd. de volumes | contagem de `pedido3_001.caixa` distintos | `nota_001.volumes` também (declarado na NF). |
| Itens/peças por volume | `pedido3_001.codigo, cor, tam, qtde + qtde_f` | |
| **Frete cotado** | `frete_cota_001.valor` (tela de cotação; "VALOR_COTADO" no R10) | `valor_cotado`, `valor_transp`, `valor_previsto` sempre vazios. `nota_001.val_frete` = frete destacado na NF, quase sempre 0. |
| **Frete realizado** | `nota_entra_001.valor` com `tipo = '57'` (CT-e lançado na entrada) | Ligação na regra 2.2 (mesma do relatório R10). |
| Prazo previsto | `nota_001.dt_prev_entrega` (parcial, desde 2024) | `frete_cota_001.prazo` vazio. |
| Prazo realizado / ocorrências | **não existe** | `acompanha_cte_001`, `consulta_cte_001`, `nota_cte_001` vazias. |
| Dados da carga no CT-e | `nota_entra_001.peso_carga`, `vol_carga`, `val_totcarga`, `dt_prev_entr` | Só desde 2026 (≈ 59% dos CT-e de 2026). Bom para conferir o peso. |
| Fator de cubagem / tarifa por transportadora | **não existe** | `regiao_frete_001`, `politica_frete_001`, `preco_frete_001` vazias. Configurar no sistema novo. |

## 2. Regras de ligação

### 2.1 Pedido → volumes → nota
`pedido3_001.numero = pedido_001.numero`; `pedido3_001.notafiscal = nota_001.fatura`.
Um pedido pode ter vários volumes e mais de uma nota.

### 2.2 Nota de venda → CT-e (frete realizado)
```
nota_ref_001.nota_ref = nota_001.fatura          -- nota de venda referenciada
nota_entra_001.notafiscal = nota_ref_001.nota     -- nº do CT-e
nota_entra_001.tipo = '57'                        -- documento CT-e
nota_entra_001.credor = nota_001.transport        -- CT-e emitido pela transportadora da nota
```
O relatório R10 do Sisplan não confere o emissor do CT-e. Sem essa conferência, o número do CT-e casa com documentos de outra
transportadora (9 números de CT-e repetidos entre credores). Com ela, 6.538 de 7.071 ligações (92%) confirmam;
as outras 533 vão para a fila de qualidade. 70 notas de venda têm mais de um CT-e (complemento/reentrega): somar e marcar.

### 2.3 Transportadora utilizada (prioridade)
1. `nota_entra_001.credor` do CT-e ligado (quem cobrou);
2. `nota_001.transport`;
3. `frete_cota_001.transp`;
4. `pedido_001.tab_trans`.

Nas notas de 2025–2026 com volumes, os campos concordam: nota × cotação 1.098 iguais / 10 diferentes;
nota × pedido 7.895 / 28. **7.298 de 15.620 notas não têm transportadora em nenhum campo** (questão aberta 1).

### 2.4 Expedições do dia
Pedidos com linhas em `pedido3_001` com `data = hoje` (hora em `hora_exp`). Hoje (07/10, 13h) = 12 pedidos;
dias inteiros recentes = 24 a 39 pedidos. `nota_001.dt_saida` traz todas as notas (≈ 200–470/dia, inclui outras operações),
por isso não serve sozinha para listar expedições.

## 3. Tamanho e qualidade da base (2023 – out/2026)

| Conjunto | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|
| Cotações (`frete_cota_001`, valor > 0) | 2.156 | 36 | 531 | 642 |
| CT-e lançados (`nota_entra_001` tipo 57) | 2.366 | 2.733 | 1.783 | 1.007 |
| Notas de venda com CT-e (transportadora conferida) | 1.919 | 2.319 | 1.415 | 849 |
| … com todos os volumes medidos e pesados | 1.662 | 1.968 | 1.171 | 727 |

- **Base de treino real ≈ 5.500 embarques** (CT-e + volumes completos); a versão anterior do modelo usava 1.780.
- **Auditoria cotado × realizado** só onde há cotação: ≈ 1.950 pedidos; em 88% o CT-e bate com a cotação em ±5%.
- Cotação quase parada entre jul/2024 e ago/2025 (36 em 2024).
- Dimensões: nos pedidos com CT-e, ≈ 90% das notas têm todos os volumes medidos e pesados. Na expedição inteira,
  só ≈ 45% dos volumes têm algo no `obs` (2023: 4.572 de 9.355; 2026: 2.535 de 7.402) e ≈ 33% têm peso:
  a medição é feita principalmente quando o frete é cotado/pago pela empresa.
- Datas inválidas: 3 cotações, 1 nota e 10 linhas de `pedido3_001` com ano < 2000 ou no futuro (ex.: 6202).
- Valores fora da curva: ex. pedido 42937, cotação R$ 15.319,00.
- Produtos sem medida/peso no Sisplan (`produto_001` zerado): a cubagem por produto depende da planilha
  "Cubagem - medidas dos produtos".

## 4. Formatos de texto do volume (`pedido3_001.obs`)

Medidos em volumes de 2023–2026 (volumes distintos):
`FD: 9X9X9 CM` 5.756 · `CX: 9X9X9 CM` 5.299 · com espaço no fim ≈ 1.100 · `FD:9X9X9 CM` 427 · `CX:9X9X9 CM` 404 ·
`DENTRO DO OUTRO PEDIDO` 398 · `FD: 9-9-9` 78 · `9 CAIXA` 76 · `9 X 9 X 9 CM` com espaços ≈ 150 · `CX;…`, `CX9X9X9`, `CX : …` raros.
**Peso nunca aparece no texto**: vem de `pedido3_001.peso`. Parser atual: `app/historico.py` (`ler_obs_volume`).

## 5. Questões abertas (para a equipe)

1. Notas sem transportadora em nenhum campo (≈ 47%): é cliente que retira, entrega própria, Correios? Entram no sistema?
2. Ordem das medidas no `obs`: é sempre C×L×A? O parser ordena da maior para a menor (não depende disso para cubagem).
3. CT-e de complemento/reentrega (70 notas com mais de um CT-e): somar no frete do pedido ou tratar à parte?
4. CEP de origem da fábrica (para distância/rota).
5. Fator de cubagem, peso mínimo e tarifa mínima de cada transportadora (não estão no Sisplan).
6. Índice de correção monetária: IPCA (Banco Central, série 433) como padrão?
7. Dados do cliente na tela (nome, CNPJ): quem pode ver?
