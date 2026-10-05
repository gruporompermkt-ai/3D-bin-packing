'''
Escolha de embalagens para um pedido (cubagem).

Unidades: centímetros e gramas. A embalagem é descrita pelas medidas INTERNAS
(comprimento x largura x altura); a altura é o eixo vertical, onde as pilhas crescem.

Para cada tipo de embalagem do catálogo, o pedido é distribuído em quantas unidades dela
forem necessárias; o último volume ainda é trocado pela menor embalagem que comporta o que
sobrou. Ganha o plano de menor custo (quando todas as embalagens têm custo) ou de menor peso
taxável, e no empate o de menos volumes.
'''
import copy
import math
from dataclasses import dataclass, field
from typing import List, Optional

from .main import Bin, Item, Packer

NUMBER_OF_DECIMALS = 1   # 0,1 cm e 0,1 g
MAX_VOLUMES = 500


@dataclass
class Produto:
    codigo: str
    tamanho: str
    comprimento: float          # cm, peça já dobrada/embalada como sai da produção
    largura: float              # cm
    espessura: float            # cm
    peso_g: float
    dobras: int = 0             # quantas vezes ainda pode ser dobrada ao meio (comprimento ou largura)
    compressao: float = 1.0     # 1 = incomprimível; 0,95 = a espessura cai para 95% dentro da pilha
    empilhavel: bool = True     # False = item rígido (gira em qualquer eixo, um a um)

    @property
    def sku(self):
        return '{}/{}'.format(self.codigo, self.tamanho)


@dataclass
class Embalagem:
    codigo: str
    comprimento: float          # cm, medidas internas
    largura: float
    altura: float
    peso_max_g: float           # peso bruto máximo (conteúdo + tara)
    tara_g: float = 0.0
    custo: Optional[float] = None
    tipo: str = 'caixa'         # 'caixa' ou 'fardo' (fardo: base fixa, altura = conteúdo, até `altura`)

    @property
    def volume_cm3(self):
        return self.comprimento * self.largura * self.altura


@dataclass
class Volume:
    embalagem: Embalagem
    itens: list = field(default_factory=list)   # [{'sku','codigo','tamanho','qtd','forma'}]
    peso_itens_g: float = 0.0
    volume_itens_cm3: float = 0.0
    # posição de cada pilha/item, na ordem de montagem (de baixo para cima)
    layout: list = field(default_factory=list)

    @property
    def altura_final(self):
        ''' caixa: altura interna; fardo: topo do conteúdo arredondado para cima (cm inteiro) '''
        e = self.embalagem
        if e.tipo != 'fardo' or not self.layout:
            return e.altura
        topo = max(b['z'] + b['a'] for b in self.layout)
        return min(e.altura, math.ceil(round(topo, 6)))


def _items_for(linhas):
    ''' linhas: [(Produto, quantidade)] -> Items do py3dbp. Rígidos têm prioridade 1 (entram antes,
    embaixo) e as pilhas de vestuário prioridade 2 (preenchem o resto). '''
    items = []
    for n, (p, qtd) in enumerate(linhas):
        if qtd <= 0:
            continue
        whd = (p.comprimento, p.largura, p.espessura)
        if p.empilhavel:
            items.append(Item('{}#{}'.format(p.sku, n), p.sku, 'cube', whd, p.peso_g, 2, 100, False, '#4472C4',
                              fold_count=p.dobras, compress_ratio=p.compressao, quantity=int(qtd), sku=p))
        else:
            for k in range(int(qtd)):
                items.append(Item('{}#{}.{}'.format(p.sku, n, k), p.sku, 'cube', whd, p.peso_g, 1, 100, True,
                                  '#ED7D31', sku=p))
    return items


def _remaining(items):
    ''' quantidade que sobrou por produto, preservando a ordem das linhas '''
    sobra = {}
    for it in items:
        if it.quantity > 0:
            p = it.sku
            sobra[p.sku] = (p, sobra.get(p.sku, (p, 0))[1] + it.quantity)
    return list(sobra.values())


def pack_one(embalagem, linhas):
    '''
    Enche UMA embalagem com o que couber das linhas.
    Retorna (Volume, linhas_que_sobraram, bin). Volume vazio = nada coube.
    '''
    packer = Packer()
    capacidade = embalagem.peso_max_g - embalagem.tara_g
    b = Bin(embalagem.codigo, (embalagem.comprimento, embalagem.largura, embalagem.altura), max(capacidade, 0))
    packer.addBin(b)
    for it in _items_for(linhas):
        packer.addItem(it)
    packer.pack(bigger_first=True, distribute_items=True, fix_point=True, check_stable=True,
                support_surface_ratio=0.75, number_of_decimals=NUMBER_OF_DECIMALS)

    vol = Volume(embalagem)
    agrupado = {}
    for it in b.items:
        p = it.sku
        forma = it.foldDescription() if it.is_stack else 'rígido'
        chave = (p.sku, forma)
        agrupado[chave] = agrupado.get(chave, 0) + it.quantity
        vol.peso_itens_g += float(it.weight)
        vol.volume_itens_cm3 += float(it.getVolume())
        x, y, z = (float(v) for v in it.position)
        c, l, a = (float(v) for v in it.getDimension())
        # x = comprimento, y = largura, z = altura (vertical)
        vol.layout.append({'sku': p.sku, 'qtd': it.quantity, 'forma': forma,
                           'x': x, 'y': y, 'z': z, 'c': c, 'l': l, 'a': a})
    vol.layout.sort(key=lambda b: (b['z'], b['y'], b['x']))
    for (sku, forma), qtd in agrupado.items():
        codigo, tamanho = sku.split('/', 1)
        vol.itens.append({'sku': sku, 'codigo': codigo, 'tamanho': tamanho, 'qtd': qtd, 'forma': forma})
    return vol, _remaining(packer.unfit_items), b


def _plan_with(embalagem, linhas, catalogo):
    volumes = []
    resto = [(p, q) for p, q in linhas if q > 0]
    while resto:
        if len(volumes) >= MAX_VOLUMES:
            return None
        vol, resto, _ = pack_one(embalagem, resto)
        if not vol.itens:
            return None     # algum item não cabe nem na embalagem vazia
        volumes.append(vol)
    if not volumes:
        return []

    ultimo = volumes[-1]
    conteudo = [(_find(linhas, i['sku']), i['qtd']) for i in _merge(ultimo.itens)]
    if embalagem.tipo == 'fardo':
        # o empacotador enche uma coluna até o topo antes de abrir outra; no último fardo (parcial)
        # procura a menor altura em que tudo ainda cabe, espalhando as peças pela base
        volumes[-1] = _fardo_mais_baixo(embalagem, conteudo, ultimo)
        return volumes

    # caixa: troca o último volume (normalmente parcial) pela menor embalagem que comporta tudo dele
    for menor in sorted(catalogo, key=lambda e: e.volume_cm3):
        if menor.volume_cm3 >= embalagem.volume_cm3:
            break
        vol, sobra, _ = pack_one(menor, conteudo)
        if not sobra:
            volumes[-1] = vol
            break
    return volumes


def _fardo_mais_baixo(fardo, conteudo, atual):
    ''' busca binária (cm inteiro) da menor altura máxima que comporta todo o conteúdo '''
    melhor = atual
    lo, hi = 1, int(math.ceil(atual.altura_final))
    while lo < hi:
        meio = (lo + hi) // 2
        teste = copy.copy(fardo)
        teste.altura = meio
        vol, sobra, _ = pack_one(teste, conteudo)
        if not sobra and vol.itens:
            vol.embalagem = fardo          # mantém a altura máxima do cadastro no resultado
            melhor, hi = vol, meio
        else:
            lo = meio + 1
    return melhor


def _merge(itens):
    ''' soma quantidades do mesmo sku com formas diferentes '''
    tot = {}
    for i in itens:
        tot[i['sku']] = tot.get(i['sku'], 0) + i['qtd']
    return [{'sku': s, 'qtd': q} for s, q in tot.items()]


def _find(linhas, sku):
    for p, _ in linhas:
        if p.sku == sku:
            return p
    raise KeyError(sku)


def resumo_volume(v, fator_cubagem):
    e = v.embalagem
    altura = v.altura_final
    volume_m3 = e.comprimento * e.largura * altura / 1_000_000
    peso_real_kg = (v.peso_itens_g + e.tara_g) / 1000
    peso_cubado_kg = volume_m3 * fator_cubagem
    return {
        'embalagem': e.codigo,
        'tipo': e.tipo,
        'dimensoes_cm': [e.comprimento, e.largura, altura],
        'altura_max_cm': e.altura if e.tipo == 'fardo' else None,
        'volume_m3': round(volume_m3, 4),
        'ocupacao_pct': round(v.volume_itens_cm3 / (volume_m3 * 1_000_000) * 100, 1) if volume_m3 else 0,
        'peso_real_kg': round(peso_real_kg, 3),
        'peso_cubado_kg': round(peso_cubado_kg, 3),
        'peso_taxavel_kg': round(max(peso_real_kg, peso_cubado_kg), 3),
        'custo': e.custo,
        'itens': v.itens,
        'layout': v.layout,
    }


def cartonize(linhas: List[tuple], catalogo: List[Embalagem], fator_cubagem: float = 300.0):
    '''
    linhas: [(Produto, quantidade)]
    fator_cubagem: kg por m³ da transportadora (ex.: 300 rodoviário)
    '''
    linhas = [(p, int(q)) for p, q in linhas if q > 0]
    if not catalogo:
        raise ValueError('nenhuma embalagem cadastrada')
    planos = []
    for emb in catalogo:
        volumes = _plan_with(emb, copy.deepcopy(linhas), catalogo)
        if volumes is None:
            continue
        resumo = [resumo_volume(v, fator_cubagem) for v in volumes]
        custos = [r['custo'] for r in resumo]
        planos.append({
            'volumes': resumo,
            'custo_total': round(sum(custos), 2) if custos and None not in custos else None,
            'peso_taxavel_kg': round(sum(r['peso_taxavel_kg'] for r in resumo), 3),
            'peso_real_kg': round(sum(r['peso_real_kg'] for r in resumo), 3),
        })
    if not planos:
        return {'ok': False, 'motivo': 'algum item não cabe em nenhuma embalagem do catálogo', 'volumes': []}

    usa_custo = all(p['custo_total'] is not None for p in planos)
    planos.sort(key=lambda p: ((p['custo_total'] if usa_custo else p['peso_taxavel_kg']), len(p['volumes'])))
    melhor = planos[0]
    return {
        'ok': True,
        'criterio': 'menor custo' if usa_custo else 'menor peso taxável',
        'fator_cubagem': fator_cubagem,
        'volumes': melhor['volumes'],
        'totais': {
            'volumes': len(melhor['volumes']),
            'peso_real_kg': melhor['peso_real_kg'],
            'peso_taxavel_kg': melhor['peso_taxavel_kg'],
            'custo_total': melhor['custo_total'],
            'pecas': sum(i['qtd'] for v in melhor['volumes'] for i in v['itens']),
        },
        'alternativas': [
            {'embalagem_base': p['volumes'][0]['embalagem'] if p['volumes'] else None, 'volumes': len(p['volumes']),
             'peso_taxavel_kg': p['peso_taxavel_kg'], 'custo_total': p['custo_total']}
            for p in planos[1:]
        ],
    }
