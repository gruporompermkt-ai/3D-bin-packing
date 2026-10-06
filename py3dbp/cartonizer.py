'''
Escolha de embalagens para um pedido (cubagem).

Unidades: centímetros e gramas. A embalagem é descrita pelas medidas INTERNAS
(comprimento x largura x altura); a altura é o eixo vertical.

Embalagens:
  caixa                 medidas fixas.
  fardo                 paredes flexíveis: as medidas finais são as do conteúdo, até as máximas do
                        cadastro. Forma:
                          flexivel    (padrão) testa retangular e cilíndrico e fica com o mais compacto;
                          retangular  conteúdo em bloco (envelope comprimento x largura x altura);
                          cilindrico  conteúdo dentro de um círculo (diâmetro <= menor lado da base);
                          arredondado retângulo com cantos arredondados (raio_canto, em cm);
                          molde       contorno qualquer (pontos de 0 a 1), ex.: traçado de uma foto.
                        Arredondado e molde viram uma grade de células de 1 cm (ver moldes.py).

Vestuário curvável: quando a peça reta não cabe num vão, pode ser curvada a 90 graus (formato L,
deitada) para ocupar um canto. Um arco é aproximado pelo L.

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

from . import moldes
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
    curvavel: bool = True           # vestuário: pode ser curvado em L para ocupar um canto

    @property
    def sku(self):
        return '{}/{}'.format(self.codigo, self.tamanho)


@dataclass
class Embalagem:
    codigo: str
    comprimento: float          # cm, medidas internas (fardo: máximas)
    largura: float
    altura: float
    peso_max_g: float           # peso bruto máximo (conteúdo + tara)
    tara_g: float = 0.0
    custo: Optional[float] = None
    tipo: str = 'caixa'         # 'caixa' ou 'fardo'
    forma: str = 'flexivel'     # fardo: 'flexivel', 'retangular', 'cilindrico', 'arredondado' ou 'molde'
    raio_canto: float = 0.0     # fardo arredondado: raio dos cantos (cm)
    molde: Optional[list] = None    # fardo molde: [[x, y], ...] de 0 a 1

    def __post_init__(self):
        if self.tipo == 'fardo' and self.forma == 'cilindrico' and not self.largura:
            self.largura = self.comprimento

    @property
    def formas(self):
        ''' formatos que o conteúdo pode assumir dentro desta embalagem '''
        if self.tipo != 'fardo':
            return ['caixa']
        if self.forma == 'flexivel':
            return ['retangular', 'cilindrico']
        return [self.forma]

    @property
    def diametro_max(self):
        return min(self.comprimento, self.largura or self.comprimento)

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
    formato: str = 'caixa'                      # 'caixa', 'retangular', 'cilindrico', 'arredondado', 'molde'

    @property
    def cilindrico(self):
        return self.formato == 'cilindrico'

    def _extensao(self, chave, tam):
        return max(b[chave] + b[tam] for b in self.layout)

    @property
    def altura_final(self):
        ''' caixa: altura interna; fardo: topo do conteúdo arredondado para cima (cm inteiro) '''
        e = self.embalagem
        if e.tipo != 'fardo' or not self.layout:
            return e.altura
        return min(e.altura, math.ceil(round(self._extensao('z', 'a'), 6)))

    @property
    def diametro_final(self):
        ''' fardo cilíndrico: menor círculo (centrado) que envolve o conteúdo, cm inteiro para cima '''
        e = self.embalagem
        if not self.layout:
            return e.diametro_max
        r = self.dims_empacotamento[0] / 2
        dist = 0.0
        for b in self.layout:
            fx = max(abs(b['x'] - r), abs(b['x'] + b['c'] - r))
            fy = max(abs(b['y'] - r), abs(b['y'] + b['l'] - r))
            dist = max(dist, math.hypot(fx, fy))
        return min(e.diametro_max, math.ceil(round(2 * dist, 6)))

    @property
    def dimensoes_finais(self):
        e = self.embalagem
        if e.tipo != 'fardo':
            return [e.comprimento, e.largura, e.altura]
        if self.cilindrico:
            d = self.diametro_final
            return [d, d, self.altura_final]
        if self.formato in ('arredondado', 'molde'):
            # o contorno é o da base em que as peças foram encaixadas (os cantos/curvas dependem dela);
            # a busca do fardo testa bases menores para encolhê-lo
            c, l = self.dims_empacotamento[:2]
            return [math.ceil(round(c, 6)), math.ceil(round(l, 6)), self.altura_final]
        if not self.layout:
            return [e.comprimento, e.largura, e.altura]
        # paredes flexíveis: o fardo fica do tamanho do conteúdo
        return [min(e.comprimento, math.ceil(round(self._extensao('x', 'c'), 6))),
                min(e.largura, math.ceil(round(self._extensao('y', 'l'), 6))),
                self.altura_final]

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
            # quantity > 1 garante que até uma peça só seja tratada como pilha (dobra/curva/compressão)
            items.append(Item('{}#{}'.format(p.sku, n), p.sku, 'cube', whd, p.peso_g, 2, 100, bool(p.orientacao_livre),
                              '#4472C4', fold_count=p.dobras, compress_ratio=p.compressao, quantity=int(qtd), sku=p,
                              bendable=bool(p.curvavel)))
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


def _pack_strategy(embalagem, dims, linhas, estrategia, formato, compactar=True):
    nome, ordem, dobrar_primeiro, maiores_primeiro = estrategia
    packer = Packer()
    capacidade = embalagem.peso_max_g - embalagem.tara_g
    if formato == 'cilindrico':
        d = min(dims[0], dims[1])
        dims = (d, d, dims[2])
    if formato in ('arredondado', 'molde'):
        b = Bin(embalagem.codigo, dims, max(capacidade, 0), shape='mask',
                mask=_mascara(embalagem, formato, dims[0], dims[1]), mask_cell=moldes.CELULA_CM)
    else:
        b = Bin(embalagem.codigo, dims, max(capacidade, 0),
                shape='cylinder' if formato == 'cilindrico' else 'box')
    b.stack_rotations = ordem
    b.fold_first = dobrar_primeiro
    packer.addBin(b)
    for it in _items_for(linhas):
        packer.addItem(it)
    packer.pack(bigger_first=maiores_primeiro, distribute_items=True, fix_point=True, check_stable=True,
                support_surface_ratio=0.75, number_of_decimals=NUMBER_OF_DECIMALS)
    sobra = _remaining(packer.unfit_items)
    vol = _volume_de(b.items, embalagem, dims, nome, formato)
    if embalagem.tipo == 'fardo' and compactar:
        # no fardo as medidas acompanham o conteúdo: reacomoda as pilhas do topo para encolhê-lo.
        # Fica a versão compactada só se ela for melhor já com as medidas finais arredondadas.
        b.compactTop()
        compacto = _volume_de(b.items, embalagem, dims, nome + ' + compactação do topo', formato)
        if _score(compacto) < _score(vol):
            vol = compacto
    return vol, sobra


def _mascara(embalagem, formato, comprimento, largura):
    if formato == 'arredondado':
        return moldes.mascara_arredondada(comprimento, largura, embalagem.raio_canto)
    return moldes.mascara_poligono(comprimento, largura, embalagem.molde)


def _contorno(embalagem, formato, comprimento, largura):
    ''' polígono (cm) da seção do fardo nas medidas finais, para o 3D '''
    if formato == 'arredondado':
        return moldes.contorno_arredondado(comprimento, largura, embalagem.raio_canto)
    if formato == 'molde':
        return moldes.contorno_poligono(comprimento, largura, embalagem.molde)
    return None


def _volume_de(items, embalagem, dims, nome, formato):
    vol = Volume(embalagem, dims_empacotamento=tuple(dims), estrategia=nome, formato=formato)
    agrupado = {}
    for it in items:
        p = it.sku
        forma = it.foldDescription() if it.is_stack else 'rígido'
        if it.bend:
            forma = 'curvada em L'
        elif it.is_stack and Bin.STACK_AXIS[it.rotation_type] != 2:
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
                           'camadas': it.layers or it.quantity, 'parte_l': it.bend,
                           'eixo': EIXOS[Bin.STACK_AXIS[it.rotation_type]] if it.is_stack else None,
                           'x': x, 'y': y, 'z': z, 'c': c, 'l': l, 'a': a})
    vol.layout.sort(key=lambda q: (q['z'], q['y'], q['x']))
    for (sku, forma), qtd in agrupado.items():
        codigo, tamanho = sku.split('/', 1)
        vol.itens.append({'sku': sku, 'codigo': codigo, 'tamanho': tamanho, 'qtd': qtd, 'forma': forma})
    return vol


def _score(vol):
    '''
    menor é melhor: mais peças, menor envelope cobrado, conteúdo mais baixo.
    (o volume das peças não entra: ele só varia pelo arredondamento entre peça aberta e dobrada)
    '''
    topo = max((q['z'] + q['a'] for q in vol.layout), default=0)
    return (-vol.pecas, vol.envelope_cm3, topo)


def pack_one(embalagem, linhas, iteracoes=ITERACOES_PADRAO, dims=None, formatos=None, compactar=True):
    '''
    Enche UMA embalagem com o que couber das linhas, testando `iteracoes` estratégias em cada
    formato possível (fardo flexível: retangular e cilíndrico).
    Retorna (Volume, linhas_que_sobraram). Volume vazio = nada coube.
    '''
    dims = dims or (embalagem.comprimento, embalagem.largura, embalagem.altura)
    melhor = None
    for formato in formatos or embalagem.formas:
        for est in estrategias(iteracoes):
            vol, sobra = _pack_strategy(embalagem, dims, linhas, est, formato, compactar)
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


def _cabe(fardo, dims, conteudo, iteracoes, formato, compactar=True):
    vol, sobra = pack_one(fardo, conteudo, iteracoes, dims, [formato], compactar)
    return vol if (vol.itens and not sobra) else None


def _menor_altura(fardo, base, conteudo, lo, hi, iteracoes, formato, candidatos):
    '''
    busca binária (cm inteiro) da menor altura entre lo e hi que comporta todo o conteúdo.
    Toda montagem que coube vai para `candidatos` como (envelope, formato, dims, volume): com
    paredes flexíveis a mais baixa nem sempre é a menor (pode sair mais larga).
    Montagens rápidas (sem compactação do topo): a compactação não muda o que cabe.
    '''
    if lo > hi:
        return

    def testa(h):
        dims = (base[0], base[1], h)
        vol = _cabe(fardo, dims, conteudo, iteracoes, formato, compactar=False)
        if vol:
            candidatos.append((vol.envelope_cm3, formato, dims, vol))
        return vol

    topo = hi
    if not testa(hi):
        return
    while lo < hi:
        meio = (lo + hi) // 2
        if testa(meio):
            hi = meio
        else:
            lo = meio + 1
    # alturas logo acima da mínima costumam dar montagens mais estreitas
    for h in range(hi + 1, min(hi + 2, topo) + 1):
        testa(h)


def _volume_conteudo(conteudo):
    ''' volume das peças já comprimidas: limite inferior para o volume de qualquer fardo '''
    return sum(p.comprimento * p.largura * p.espessura * (p.compressao if p.empilhavel else 1) * q
               for p, q in conteudo)


def _fardo_compacto(fardo, conteudo, atual, iteracoes):
    '''
    O empacotador enche uma coluna até o topo antes de abrir outra; no último fardo (parcial)
    procura o fardo mais compacto (menor envelope) em que tudo ainda cabe:
      retangular: menor altura com a base do cadastro;
      cilíndrico (flexível): diâmetros decrescentes x menor altura para cada um.
    '''
    melhor = atual
    # a busca testa muitas alturas: usa poucas estratégias e nenhuma compactação nela; as melhores
    # combinações são remontadas no fim com todas as iterações e a compactação do topo
    it_busca = min(iteracoes, 3)
    C, L = fardo.comprimento, fardo.largura
    vol_min = _volume_conteudo(conteudo)
    candidatos = []
    for formato in fardo.formas:
        if formato == 'cilindrico':
            dmax = fardo.diametro_max
            bases = [(d, d) for d in sorted({max(1, math.ceil(dmax * f)) for f in (1, .8, .6)}, reverse=True)]
        else:
            # paredes flexíveis: bases menores que a máxima também valem. No arredondado/molde o
            # fardo fica com o contorno da base inteira, então vale testar mais tamanhos
            fatores = [(1, 1), (.8, .8), (1, .6), (.6, 1), (.6, .6)]
            if formato in ('arredondado', 'molde'):
                fatores += [(.9, .9), (.7, .7), (.9, .7), (.7, .9)]
            bases = sorted({(max(1, math.ceil(C * fx)), max(1, math.ceil(L * fy))) for fx, fy in fatores},
                           key=lambda b: -b[0] * b[1])
        for base in bases:
            area = base[0] * base[1]
            area_util = math.pi * (base[0] / 2) ** 2 if formato == 'cilindrico' else area
            # poda: abaixo de lo o conteúdo não cabe (volume das peças / área da base). Não há limite
            # superior seguro: com paredes flexíveis o fardo final pode ser mais estreito que a base
            lo = max(1, math.ceil(vol_min / area_util))
            hi = int(math.ceil(fardo.altura))
            _menor_altura(fardo, base, conteudo, lo, hi, it_busca, formato, candidatos)

    # remonta as 3 melhores combinações (base, altura) com todas as iterações e a compactação
    vistos = set()
    for _, formato, dims, vol in sorted(candidatos, key=lambda c: c[0]):
        if (formato, dims) in vistos:
            continue
        vistos.add((formato, dims))
        for candidato in (vol, _cabe(fardo, dims, conteudo, iteracoes, formato)):
            if candidato and candidato.envelope_cm3 < melhor.envelope_cm3:
                melhor = candidato
        if len(vistos) == 3:
            break
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
    contorno = _contorno(e, v.formato, dims[0], dims[1])
    if v.cilindrico:
        volume_real_m3 = math.pi * (dims[0] / 2) ** 2 * dims[2] / 1_000_000
    elif contorno:
        volume_real_m3 = moldes.area_poligono(contorno) * dims[2] / 1_000_000
    else:
        volume_real_m3 = volume_m3
    peso_real_kg = (v.peso_itens_g + e.tara_g) / 1000
    peso_cubado_kg = volume_m3 * fator_cubagem
    layout = v.layout
    if v.cilindrico:
        # recentra o conteúdo no cilindro final (x, y de 0 até o diâmetro final)
        desloc = (v.dims_empacotamento[0] - dims[0]) / 2
        layout = [dict(q, x=round(q['x'] - desloc, 2), y=round(q['y'] - desloc, 2)) for q in layout]
    return {
        'embalagem': e.codigo,
        'tipo': e.tipo,
        'forma': v.formato,
        'dimensoes_cm': dims,
        'max_cm': [e.comprimento, e.largura, e.altura] if e.tipo == 'fardo' else None,
        'altura_max_cm': e.altura if e.tipo == 'fardo' else None,
        'diametro_max_cm': e.diametro_max if v.cilindrico else None,
        'contorno_cm': contorno,
        'raio_canto_cm': e.raio_canto if v.formato == 'arredondado' else None,
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
