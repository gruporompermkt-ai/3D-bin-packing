'''
Escolha de embalagens para um pedido (cubagem).

Unidades: centímetros e gramas. A embalagem é descrita pelas medidas INTERNAS
(comprimento x largura x altura); a altura é o eixo vertical.

Embalagens:
  caixa                 medidas fixas.
  fardo retangular      base comprimento x largura fixa; altura final = conteúdo (até a altura máxima).
  fardo cilíndrico      flexível: comprimento = diâmetro máximo; diâmetro e altura finais = conteúdo.

Cada volume é montado com várias estratégias (iterações: ordem das orientações das pilhas,
dobrar antes ou depois, ordem dos itens e variações aleatórias) e fica a mais densa.

Para cada tipo de embalagem do catálogo, o pedido é distribuído em quantas unidades dela
forem necessárias. O último volume (parcial) é trocado pela menor caixa que comporta o que
sobrou, ou, no fardo, encolhido até a menor altura/diâmetro em que tudo ainda cabe. Ganha o
plano de menor custo (quando todas as embalagens têm custo) ou de menor peso taxável, e no
empate o de menos volumes.
'''
import copy
import math
import random
from dataclasses import dataclass, field
from typing import List, Optional

from .constants import RotationType
from .main import Bin, Item, Packer

NUMBER_OF_DECIMALS = 1   # 0,1 cm e 0,1 g
MAX_VOLUMES = 500
ITERACOES_PADRAO = 8
EIXOS = 'xyz'


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
    orientacao_livre: bool = True   # vestuário: True = pode ficar em pé (de lado); False = só deitada

    @property
    def sku(self):
        return '{}/{}'.format(self.codigo, self.tamanho)


@dataclass
class Embalagem:
    codigo: str
    comprimento: float          # cm, medidas internas (fardo cilíndrico: diâmetro máximo)
    largura: float              # fardo cilíndrico: ignorada (= diâmetro)
    altura: float               # fardo: altura máxima
    peso_max_g: float           # peso bruto máximo (conteúdo + tara)
    tara_g: float = 0.0
    custo: Optional[float] = None
    tipo: str = 'caixa'         # 'caixa' ou 'fardo'
    forma: str = 'retangular'   # fardo: 'retangular' ou 'cilindrico'

    def __post_init__(self):
        if self.cilindrico:
            self.largura = self.comprimento

    @property
    def cilindrico(self):
        return self.tipo == 'fardo' and self.forma == 'cilindrico'

    @property
    def volume_cm3(self):
        return self.comprimento * self.largura * self.altura


@dataclass
class Volume:
    embalagem: Embalagem
    dims_empacotamento: tuple = None            # bin usado (pode ser menor que a embalagem na busca do fardo)
    itens: list = field(default_factory=list)   # [{'sku','codigo','tamanho','qtd','forma'}]
    peso_itens_g: float = 0.0
    volume_itens_cm3: float = 0.0
    pecas: int = 0
    # posição de cada pilha/item, na ordem de montagem (de baixo para cima)
    layout: list = field(default_factory=list)
    estrategia: str = ''

    @property
    def altura_final(self):
        ''' caixa: altura interna; fardo: topo do conteúdo arredondado para cima (cm inteiro) '''
        e = self.embalagem
        if e.tipo != 'fardo' or not self.layout:
            return e.altura
        topo = max(b['z'] + b['a'] for b in self.layout)
        return min(e.altura, math.ceil(round(topo, 6)))

    @property
    def diametro_final(self):
        ''' fardo cilíndrico: menor círculo (centrado) que envolve o conteúdo, cm inteiro para cima '''
        e = self.embalagem
        if not e.cilindrico or not self.layout:
            return e.comprimento
        r = self.dims_empacotamento[0] / 2
        dist = 0.0
        for b in self.layout:
            fx = max(abs(b['x'] - r), abs(b['x'] + b['c'] - r))
            fy = max(abs(b['y'] - r), abs(b['y'] + b['l'] - r))
            dist = max(dist, math.hypot(fx, fy))
        return min(e.comprimento, math.ceil(round(2 * dist, 6)))

    @property
    def dimensoes_finais(self):
        e = self.embalagem
        if e.cilindrico:
            d = self.diametro_final
            return [d, d, self.altura_final]
        return [e.comprimento, e.largura, self.altura_final]

    @property
    def envelope_cm3(self):
        ''' volume que a transportadora cobra (caixa ou o "caixote" em volta do fardo) '''
        c, l, a = self.dimensoes_finais
        return c * l * a


def _items_for(linhas):
    ''' linhas: [(Produto, quantidade)] -> Items do py3dbp. Rígidos têm prioridade 1 (entram antes,
    embaixo) e as pilhas de vestuário prioridade 2 (preenchem o resto). '''
    items = []
    for n, (p, qtd) in enumerate(linhas):
        if qtd <= 0:
            continue
        whd = (p.comprimento, p.largura, p.espessura)
        if p.empilhavel:
            items.append(Item('{}#{}'.format(p.sku, n), p.sku, 'cube', whd, p.peso_g, 2, 100, bool(p.orientacao_livre),
                              '#4472C4', fold_count=p.dobras, compress_ratio=p.compressao, quantity=int(qtd), sku=p))
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


# ------------------------------------------------------------------ estratégias
DEITADA = [RotationType.RT_WHD, RotationType.RT_HWD]
EM_PE_X = [RotationType.RT_DHW, RotationType.RT_DWH]
EM_PE_Y = [RotationType.RT_HDW, RotationType.RT_WDH]
ESTRATEGIAS_FIXAS = [
    # (nome, ordem das orientações das pilhas, dobrar primeiro, maiores primeiro)
    ('deitada primeiro', DEITADA + EM_PE_Y + EM_PE_X, False, True),
    ('em pé primeiro', EM_PE_X + EM_PE_Y + DEITADA, False, True),
    ('em pé (outro lado) primeiro', EM_PE_Y + EM_PE_X + DEITADA, False, True),
    ('deitada, menores primeiro', DEITADA + EM_PE_Y + EM_PE_X, False, False),
    ('dobrada primeiro', DEITADA + EM_PE_Y + EM_PE_X, True, True),
]


def estrategias(n):
    ''' as fixas primeiro; o resto são variações aleatórias (semente fixa: o resultado é reprodutível) '''
    out = ESTRATEGIAS_FIXAS[:max(1, n)]
    rnd = random.Random(1234)
    for i in range(len(out), n):
        ordem = list(RotationType.ALL)
        rnd.shuffle(ordem)
        out.append(('aleatória {}'.format(i - len(ESTRATEGIAS_FIXAS) + 1), ordem, rnd.random() < 0.3, rnd.random() < 0.7))
    return out


def _pack_strategy(embalagem, dims, linhas, estrategia):
    nome, ordem, dobrar_primeiro, maiores_primeiro = estrategia
    packer = Packer()
    capacidade = embalagem.peso_max_g - embalagem.tara_g
    b = Bin(embalagem.codigo, dims, max(capacidade, 0),
            shape='cylinder' if embalagem.cilindrico else 'box')
    b.stack_rotations = ordem
    b.fold_first = dobrar_primeiro
    packer.addBin(b)
    for it in _items_for(linhas):
        packer.addItem(it)
    packer.pack(bigger_first=maiores_primeiro, distribute_items=True, fix_point=True, check_stable=True,
                support_surface_ratio=0.75, number_of_decimals=NUMBER_OF_DECIMALS)

    vol = Volume(embalagem, dims_empacotamento=tuple(dims), estrategia=nome)
    agrupado = {}
    for it in b.items:
        p = it.sku
        forma = it.foldDescription() if it.is_stack else 'rígido'
        if it.is_stack and Bin.STACK_AXIS[it.rotation_type] != 2:
            forma += ', em pé'
        chave = (p.sku, forma)
        agrupado[chave] = agrupado.get(chave, 0) + it.quantity
        vol.peso_itens_g += float(it.weight)
        vol.volume_itens_cm3 += float(it.getVolume())
        vol.pecas += it.quantity
        x, y, z = (float(v) for v in it.position)
        c, l, a = (float(v) for v in it.getDimension())
        # x = comprimento, y = largura, z = altura (vertical); eixo = para onde a pilha cresce
        vol.layout.append({'sku': p.sku, 'qtd': it.quantity, 'forma': forma,
                           'eixo': EIXOS[Bin.STACK_AXIS[it.rotation_type]] if it.is_stack else None,
                           'x': x, 'y': y, 'z': z, 'c': c, 'l': l, 'a': a})
    vol.layout.sort(key=lambda q: (q['z'], q['y'], q['x']))
    for (sku, forma), qtd in agrupado.items():
        codigo, tamanho = sku.split('/', 1)
        vol.itens.append({'sku': sku, 'codigo': codigo, 'tamanho': tamanho, 'qtd': qtd, 'forma': forma})
    return vol, _remaining(packer.unfit_items)


def _score(vol):
    ''' menor é melhor: mais peças, mais volume, menor envelope cobrado, conteúdo mais baixo '''
    topo = max((q['z'] + q['a'] for q in vol.layout), default=0)
    return (-vol.pecas, -round(vol.volume_itens_cm3, 1), vol.envelope_cm3, topo)


def pack_one(embalagem, linhas, iteracoes=ITERACOES_PADRAO, dims=None):
    '''
    Enche UMA embalagem com o que couber das linhas, testando `iteracoes` estratégias.
    Retorna (Volume, linhas_que_sobraram). Volume vazio = nada coube.
    '''
    dims = dims or (embalagem.comprimento, embalagem.largura, embalagem.altura)
    melhor = None
    for est in estrategias(iteracoes):
        vol, sobra = _pack_strategy(embalagem, dims, linhas, est)
        if melhor is None or _score(vol) < _score(melhor[0]):
            melhor = (vol, sobra)
    return melhor


def _plan_with(embalagem, linhas, catalogo, iteracoes):
    volumes = []
    resto = [(p, q) for p, q in linhas if q > 0]
    while resto:
        if len(volumes) >= MAX_VOLUMES:
            return None
        vol, resto = pack_one(embalagem, resto, iteracoes)
        if not vol.itens:
            return None     # algum item não cabe nem na embalagem vazia
        volumes.append(vol)
    if not volumes:
        return []

    ultimo = volumes[-1]
    conteudo = [(_find(linhas, i['sku']), i['qtd']) for i in _merge(ultimo.itens)]
    if embalagem.tipo == 'fardo':
        volumes[-1] = _fardo_compacto(embalagem, conteudo, ultimo, iteracoes)
        return volumes

    # caixa: troca o último volume (normalmente parcial) pela menor embalagem que comporta tudo dele
    for menor in sorted(catalogo, key=lambda e: e.volume_cm3):
        if menor.volume_cm3 >= embalagem.volume_cm3 or menor.tipo != 'caixa':
            continue
        vol, sobra = pack_one(menor, conteudo, iteracoes)
        if not sobra:
            volumes[-1] = vol
            break
    return volumes


def _cabe(fardo, dims, conteudo, iteracoes):
    vol, sobra = pack_one(fardo, conteudo, iteracoes, dims)
    return vol if (vol.itens and not sobra) else None


def _menor_altura(fardo, base, conteudo, hi, iteracoes):
    ''' busca binária (cm inteiro) da menor altura máxima que comporta todo o conteúdo '''
    melhor = None
    lo = 1
    while lo < hi:
        meio = (lo + hi) // 2
        vol = _cabe(fardo, (base[0], base[1], meio), conteudo, iteracoes)
        if vol:
            melhor, hi = vol, meio
        else:
            lo = meio + 1
    if melhor is None:
        melhor = _cabe(fardo, (base[0], base[1], hi), conteudo, iteracoes)
    return melhor


def _fardo_compacto(fardo, conteudo, atual, iteracoes):
    '''
    O empacotador enche uma coluna até o topo antes de abrir outra; no último fardo (parcial)
    procura o fardo mais compacto (menor envelope) em que tudo ainda cabe:
      retangular: menor altura com a base do cadastro;
      cilíndrico (flexível): diâmetros decrescentes x menor altura para cada um.
    '''
    melhor = atual
    hi = int(math.ceil(atual.altura_final))
    # a busca testa muitas alturas: usa poucas estratégias nela e todas só na montagem final
    it_busca = min(iteracoes, 3)
    if fardo.cilindrico:
        dmax = fardo.comprimento
        diametros = sorted({max(1, math.ceil(dmax * f)) for f in (1, .85, .7, .55)}, reverse=True)
    else:
        diametros = [None]
    escolhido = None
    for d in diametros:
        base = (d, d) if d else (fardo.comprimento, fardo.largura)
        vol = _menor_altura(fardo, base, conteudo, hi, it_busca)
        if vol is None:
            if d:
                break       # diâmetro menor não comporta: os seguintes também não
            continue
        if escolhido is None or vol.envelope_cm3 < escolhido[1].envelope_cm3:
            escolhido = (base, vol)
    if escolhido:
        base, vol = escolhido
        altura = int(math.ceil(vol.altura_final))
        final = _cabe(fardo, vol.dims_empacotamento[:2] + (altura,), conteudo, iteracoes) or vol
        for candidato in (final, vol):
            if candidato.envelope_cm3 < melhor.envelope_cm3:
                melhor = candidato
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
    dims = v.dimensoes_finais
    volume_m3 = dims[0] * dims[1] * dims[2] / 1_000_000          # envelope (caixote em volta do fardo)
    if e.cilindrico:
        volume_real_m3 = math.pi * (dims[0] / 2) ** 2 * dims[2] / 1_000_000
    else:
        volume_real_m3 = volume_m3
    peso_real_kg = (v.peso_itens_g + e.tara_g) / 1000
    peso_cubado_kg = volume_m3 * fator_cubagem
    layout = v.layout
    if e.cilindrico:
        # recentra o conteúdo no cilindro final (x, y de 0 até o diâmetro final)
        desloc = (v.dims_empacotamento[0] - dims[0]) / 2
        layout = [dict(q, x=round(q['x'] - desloc, 2), y=round(q['y'] - desloc, 2)) for q in layout]
    return {
        'embalagem': e.codigo,
        'tipo': e.tipo,
        'forma': e.forma if e.tipo == 'fardo' else 'caixa',
        'dimensoes_cm': dims,
        'altura_max_cm': e.altura if e.tipo == 'fardo' else None,
        'diametro_max_cm': e.comprimento if e.cilindrico else None,
        'volume_m3': round(volume_m3, 4),
        'volume_real_m3': round(volume_real_m3, 4),
        'ocupacao_pct': round(v.volume_itens_cm3 / (volume_real_m3 * 1_000_000) * 100, 1) if volume_real_m3 else 0,
        'peso_real_kg': round(peso_real_kg, 3),
        'peso_cubado_kg': round(peso_cubado_kg, 3),
        'peso_taxavel_kg': round(max(peso_real_kg, peso_cubado_kg), 3),
        'custo': e.custo,
        'estrategia': v.estrategia,
        'itens': v.itens,
        'layout': layout,
    }


def cartonize(linhas: List[tuple], catalogo: List[Embalagem], fator_cubagem: float = 300.0,
              iteracoes: int = ITERACOES_PADRAO):
    '''
    linhas: [(Produto, quantidade)]
    fator_cubagem: kg por m³ da transportadora (ex.: 300 rodoviário)
    iteracoes: estratégias testadas por volume (mais = mais denso e mais lento)
    '''
    linhas = [(p, int(q)) for p, q in linhas if q > 0]
    if not catalogo:
        raise ValueError('nenhuma embalagem cadastrada')
    planos = []
    for emb in catalogo:
        volumes = _plan_with(emb, copy.deepcopy(linhas), catalogo, iteracoes)
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
        'iteracoes': iteracoes,
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
