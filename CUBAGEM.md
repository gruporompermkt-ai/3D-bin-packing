# Cubagem de vestuário (fork do py3dbp)

Fork de [jerry800416/3D-bin-packing](https://github.com/jerry800416/3D-bin-packing) (MIT) com:

- correções de bugs do original (lista abaixo, cada uma com teste em `tests/test_bugs.py`);
- **dobra** e **compressão** de peças de vestuário;
- escolha de embalagens para um pedido (`py3dbp/cartonizer.py`), em **caixas** ou **fardos**;
- simulação 3D da montagem de cada volume na tela (three.js, sem depender de internet);
- API + tela web de cadastro e cálculo (`app/`), rodando em Docker no servidor 192.168.0.95.

Endereço: **http://192.168.0.95:8086/** (API em `/api/...`, documentação automática em `/docs`).

## Modelo da peça

| Campo | Significado |
|---|---|
| comprimento, largura, espessura (cm) | peça como sai da produção (já dobrada/embalada) |
| peso (g) | peso de uma peça |
| dobras | quantas vezes ainda pode ser dobrada **ao meio**, no comprimento **ou** na largura. Cada dobra corta essa medida pela metade e dobra a espessura |
| compressão | 0 a 1. **1 = incomprimível**; 0,95 = dentro da pilha a espessura cai para 95%. Só a espessura comprime |
| tipo | *vestuário* (empilha) ou *rígido* (gira em qualquer eixo, um a um) |
| orientação | vestuário: *livre* (deitada ou em pé, de lado, em qualquer direção) ou *só deitada* |

Peças iguais viram **pilhas**: deitadas (a pilha cresce para cima) ou, com orientação livre, em pé
(as peças ficam lado a lado, como fichas num arquivo, e a pilha cresce para o lado). Tamanho da pilha
= qtd × espessura × compressão (× 2 por dobra). O algoritmo só dobra quando a peça aberta não cabe (tenta primeiro sem dobra,
depois dobra no comprimento, depois na largura). Rígidos entram primeiro (embaixo) e o vestuário
preenche o resto.

## Escolha da embalagem

Para cada embalagem ativa do catálogo, o pedido é distribuído em quantas unidades dela forem
necessárias e o último volume é trocado pela menor embalagem que comporta o que sobrou. Ganha o
plano de **menor custo** (se todas as embalagens têm custo) ou de **menor peso taxável**; no empate,
o de menos volumes.

`peso taxável = max(peso real + tara, C × L × A / 1.000.000 × fator)`. O fator padrão é 300 kg/m³
(variável `FATOR_CUBAGEM`) e pode ser informado por pedido.

## Iterações (densidade)

Cada volume é montado várias vezes com estratégias diferentes: deitada primeiro, em pé primeiro (nos
dois sentidos), menores primeiro, dobrada primeiro e variações aleatórias de orientação (com semente
fixa, então o mesmo pedido dá sempre o mesmo resultado). Fica a montagem com mais peças, depois mais
volume e depois o menor volume cobrado. O padrão é 8 iterações; na tela dá para subir até 40 (mais
denso, mais lento). A estratégia vencedora aparece em cada volume.

Exemplo real (fardo 002, 30 × 40, F2505/38 ×10 + F1078/P ×15 + F1078/PP ×10):
só deitada, 1 tentativa = 76 cm (47,5%); orientação livre + 8 iterações = **47 cm (77%)**, peso
cubado de 27,4 para 16,9 kg.

## Fardo

Cadastre a embalagem com tipo **fardo** e escolha a forma:

- **retangular**: comprimento × largura são a base e a altura é a **máxima**;
- **cilíndrico (flexível)**: comprimento = **diâmetro máximo** (a largura é ignorada) e a altura máxima.
  As peças precisam caber dentro do círculo. O diâmetro final é o menor círculo, centrado, que envolve o
  conteúdo, e a altura final é o topo do conteúdo. O peso cubado usa o "caixote" Ø × Ø × altura, que é
  como as transportadoras costumam cobrar cilindros; a ocupação usa o volume real do cilindro.

Os fardos cheios vão até a altura máxima ou até o peso máximo. No último fardo, que fica parcial,
o sistema procura o fardo mais compacto em que todo o conteúdo ainda cabe: a menor altura e, no
cilíndrico, também diâmetros menores (100%, 85%, 70% e 55% do máximo). As medidas finais,
arredondadas para cima em cm inteiro, entram no volume, no peso cubado e na tela.

## Simulação 3D

Na aba Cubagem, cada volume tem **Ver 3D**: arraste para girar, use a roda do mouse para zoom e o
botão direito para mover. Cada peça da pilha aparece como uma camada (deitada ou em pé), com uma cor
por produto/tamanho. O fardo cilíndrico é desenhado como um cilindro translúcido.
A barra (◀ ▶ / ▶ montar) mostra a montagem pilha a pilha, de baixo para cima, com a posição de cada
pilha em cm a partir do canto (comprimento / largura / altura). A API devolve isso em
`volumes[].layout`.

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

- calibração do índice de compressão com volumes reais;
- leitura de pedidos/produtos do Sisplan.
