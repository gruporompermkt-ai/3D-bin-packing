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
| curvar em L | vestuário: pode ser curvado a 90° para ocupar um canto (ver abaixo) |

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
só deitada, base fixa, 1 tentativa = 30 × 40 × 76 cm (47,5%, 27,4 kg cubados); orientação livre,
8 iterações e paredes flexíveis = **29 × 38 × 47 cm (83,7%, 15,5 kg cubados)**.

## Fardo (paredes flexíveis)

O fardo não tem caixa rígida: as paredes se ajustam ao conteúdo. No cadastro informe as medidas
**máximas** (comprimento × largura × altura); as medidas finais de cada fardo são as do próprio
conteúdo (arredondadas para cima em cm inteiro) e são elas que entram no volume, no peso cubado e na
tela. Forma:

- **flexível** (padrão): testa o bloco retangular e o cilindro (diâmetro até o menor lado da base)
  e fica com o que der o menor volume cobrado;
- **retangular**: só o bloco;
- **cilíndrico**: só o cilindro; o peso cubado usa o "caixote" Ø × Ø × altura (como as
  transportadoras costumam cobrar), a ocupação usa o volume real do cilindro.

Os fardos cheios vão até as medidas máximas ou até o peso máximo. No último fardo, que fica parcial,
o sistema procura o fardo mais compacto em que tudo ainda cabe: bases menores (100%, 80% e 60% de
cada lado; no cilindro 100%, 85%, 70% e 55% do diâmetro) e, para cada uma, a menor altura. Bases
que não têm como vencer o melhor resultado já encontrado são descartadas sem montar.

## Peça curvada em L

Vestuário marcado como **Curvar em L** (padrão: sim) pode ser curvado a 90°, deitado, para ocupar um
canto: quando nenhuma forma reta (aberta, dobrada, deitada ou em pé) cabe num vão, a peça vira um L
com braços `a` e `b`, em que `a + b = comprimento + largura` (a área da peça é mantida). As quatro
posições do canto são testadas. Na tela a forma aparece como "curvada em L" e o 3D mostra os dois
braços. Uma peça em arco (acompanhando uma parede curva) é aproximada por esse L.

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

## Calibração com o histórico real (07/10/2026)

`python -m ml.comparar_cubagem` compara a cubagem com os volumes reais do Sisplan (medidas digitadas no
PEDIDO3.OBS). Nos 20 volumes que levaram só F2505 (11 fardos, 9 caixas), compressão de espessura 0,95
deixava o fardo 1,32x maior que o real; **0,7 com compressão lateral 0,92** bateu (mediana 1,00) e todas
as caixas reais couberam. O cadastro da F2505 no servidor foi atualizado para esses valores
(`dados/F2505.tsv` guarda a medição original, com 0,95).

Modelo de frete: `python -m ml.frete` (frete real do CT-e, 80% treino / 20% teste). Requer `requirements-ml.txt`.
