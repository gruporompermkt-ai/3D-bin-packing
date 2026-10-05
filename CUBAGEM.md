# Cubagem de vestuário (fork do py3dbp)

Fork de [jerry800416/3D-bin-packing](https://github.com/jerry800416/3D-bin-packing) (MIT) com:

- correções de bugs do original (lista abaixo, cada uma com teste em `tests/test_bugs.py`);
- **dobra** e **compressão** de peças de vestuário;
- escolha de embalagens para um pedido (`py3dbp/cartonizer.py`);
- API + tela web de cadastro e cálculo (`app/`), rodando em Docker no servidor 192.168.0.95.

Endereço: **http://192.168.0.95:8086/** (API em `/api/...`, documentação automática em `/docs`).

## Modelo da peça

| Campo | Significado |
|---|---|
| comprimento, largura, espessura (cm) | peça como sai da produção (já dobrada/embalada) |
| peso (g) | peso de uma peça |
| dobras | quantas vezes ainda pode ser dobrada **ao meio**, no comprimento **ou** na largura. Cada dobra corta essa medida pela metade e dobra a espessura |
| compressão | 0 a 1. **1 = incomprimível**; 0,95 = dentro da pilha a espessura cai para 95%. Só a espessura comprime |
| tipo | *vestuário* (empilha deitado) ou *rígido* (gira em qualquer eixo, um a um) |

Peças iguais viram **pilhas** (colunas) deitadas: altura da coluna = qtd × espessura × compressão
(× 2 por dobra). O algoritmo só dobra quando a peça aberta não cabe (tenta primeiro sem dobra,
depois dobra no comprimento, depois na largura). Rígidos entram primeiro (embaixo) e o vestuário
preenche o resto.

## Escolha da embalagem

Para cada embalagem ativa do catálogo, o pedido é distribuído em quantas unidades dela forem
necessárias e o último volume é trocado pela menor embalagem que comporta o que sobrou. Ganha o
plano de **menor custo** (se todas as embalagens têm custo) ou de **menor peso taxável**; no empate,
o de menos volumes.

`peso taxável = max(peso real + tara, C × L × A / 1.000.000 × fator)`. O fator padrão é 300 kg/m³
(variável `FATOR_CUBAGEM`) e pode ser informado por pedido.

## Bugs corrigidos do original

| Bug | Efeito no original |
|---|---|
| `putItem` desistia na 1ª rotação que colidia | rotações válidas nunca eram testadas |
| posição arredondada para inteiro ignorando `number_of_decimals` | itens sobrepostos com medidas decimais |
| `fix_point` empurrava o item sem checar colisão de novo | sobreposição (ex.: `example2`) |
| remoção dos itens embalados por `partno` | com `partno` repetido, item embalado 2x e outro perdido |
| `gravityCenter` dividia por zero com caixa vazia | `pack()` quebrava se um item não coubesse em nenhuma caixa |
| `gravityCenter` usava `x` no lugar de `y` | ramo inalcançável na prática; reescrito por área |
| `binding=[]` como padrão mutável | latente |
| `matplotlib` importado no núcleo | dependência pesada na API |
| `set(range(...))` nas checagens | lento e errado com decimais; trocado por intervalos |
| `api.py` usava `eval()` no corpo da requisição | execução de código remoto; trocado por `json.loads` |

Comparação com o original nos `example*.py` (`tests/baseline/`): nenhum exemplo perde volume
ocupado, `example2` e `example4` ganham, e a sobreposição do `example2` some. A **quantidade** de itens
pode mudar porque a heurística passou a girar itens que antes não girava; por isso o teste de
regressão compara volume.

## Rodar local

```bash
python -m venv venv && venv/Scripts/pip install -r requirements-dev.txt
venv/Scripts/python -m pytest -q
venv/Scripts/uvicorn app.main:app --reload --port 8086
```

## Deploy no .95

Pasta `/opt/cubagem` (clone deste repositório, branch `cubagem-vestuario`). Atualizar:
`./scripts/deploy.sh` (git pull + docker build com testes + compose up). Banco SQLite em
`/opt/cubagem/data/cubagem.db`.

## Cadastro

Planilha de exemplo em `dados/F2505.tsv`: abra a tela, aba **Produtos → Importar da planilha**,
informe o código e cole as linhas do Excel (vírgula decimal aceita; cabeçalho ignorado).

## Pendências

- fardo com altura variável (tipo `fardo` já existe no cadastro, mas é tratado como caixa);
- calibração do índice de compressão com volumes reais;
- leitura de pedidos/produtos do Sisplan.
