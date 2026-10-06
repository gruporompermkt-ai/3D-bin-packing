'''
Previsto x real: roda a cubagem nos volumes do histórico que levaram só produtos cadastrados
(hoje só a F2505) e compara com as medidas e o peso anotados pela expedição.

Uso:  python -m ml.comparar_cubagem
'''
import csv
import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.historico import ler_obs_volume  # noqa: E402
from py3dbp.cartonizer import Embalagem, Produto, cartonize  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORIGEM = os.path.join(RAIZ, 'dados', 'historico', 'sisplan.json')
MANGA = Embalagem('MANGA-80', 57.9, 57.9, 300, 37000, tipo='fardo', forma='manga', raio_canto=6,
                  manga_cm=80, folga_ponta_cm=5)


def _num(txt):
    return float(str(txt).replace(',', '.'))


def carregar_f2505(lateral):
    tabela = {}
    with open(os.path.join(RAIZ, 'dados', 'F2505.tsv'), encoding='utf-8') as f:
        for lin in list(csv.reader(f, delimiter='\t'))[1:]:
            tam, comp, larg, esp, peso, dobras, compr = lin[:7]
            tabela[int(tam)] = Produto('F2505', tam, _num(comp), _num(larg), _num(esp), _num(peso),
                                       dobras=int(_num(dobras)), compressao=_num(compr), compressao_lateral=lateral)
    return tabela


def produto_do_tamanho(tabela, tam):
    ''' tamanho fora da tabela (36, 56..62) usa o mais próximo '''
    t = int(tam)
    return tabela[min(tabela, key=lambda k: abs(k - t))]


def volumes_comparaveis(caminho=ORIGEM, produtos=('F2505',)):
    d = json.load(open(caminho, encoding='utf-8'))
    it = pd.DataFrame(d['itens'])
    it['qtde'] = it['qtde'].astype(float)
    it = it[it['qtde'] > 0]
    vol = pd.DataFrame(d['volumes'])
    so = it.groupby(['pedido', 'volume'])['produto'].agg(lambda s: set(s) <= set(produtos))
    alvo = so[so].reset_index()[['pedido', 'volume']].merge(vol, on=['pedido', 'volume'])
    alvo = pd.concat([alvo, alvo['obs'].map(ler_obs_volume).apply(pd.Series)], axis=1)
    alvo = alvo[alvo['comprimento'].notna()]
    return alvo, it


def comparar(lateral=1.0, iteracoes=8):
    tabela = carregar_f2505(lateral)
    alvo, it = volumes_comparaveis()
    linhas_saida = []
    for _, v in alvo.iterrows():
        itens = it[(it['pedido'] == v['pedido']) & (it['volume'] == v['volume'])]
        linhas = [(produto_do_tamanho(tabela, r['tam']), int(r['qtde'])) for _, r in itens.iterrows()]
        real = sorted([v['comprimento'], v['largura'], v['altura']], reverse=True)
        if v['tipo'] == 'fardo':
            r = cartonize(linhas, [MANGA], iteracoes=iteracoes, volumes_desejados=1)
        else:  # caixa: a caixa real usada, pergunta se coube e quão cheia ficou
            r = cartonize(linhas, [Embalagem('REAL', *real, 30000)], iteracoes=iteracoes)
        lin = dict(pedido=v['pedido'], volume=v['volume'], tipo=v['tipo'], pecas=int(sum(q for _, q in linhas)),
                   real_cm='x'.join('{:g}'.format(x) for x in real), peso_real_kg=float(v['peso']))
        if not r.get('ok'):
            lin.update(previsto_cm='não coube', volumes_previstos=None)
        else:
            vols = r['volumes']
            dims = sorted(vols[0]['dimensoes_cm'], reverse=True)
            lin.update(volumes_previstos=len(vols), previsto_cm='x'.join('{:g}'.format(round(x)) for x in dims),
                       peso_prev_kg=round(sum(x['peso_real_kg'] for x in vols), 1),
                       m3_real=round(real[0] * real[1] * real[2] / 1e6, 4),
                       m3_prev=round(sum(x['volume_m3'] for x in vols), 4),
                       ocupacao=vols[0].get('ocupacao_pct'))
        linhas_saida.append(lin)
    return pd.DataFrame(linhas_saida)


if __name__ == '__main__':
    for lat in (1.0, 0.92):
        df = comparar(lat)
        print('\n== compressão lateral', lat)
        print(df.to_string(index=False))
        f = df[(df['tipo'] == 'fardo') & df['m3_prev'].notna()]
        if len(f):
            print('fardos: volume previsto / real = {:.2f} (mediana)'.format((f['m3_prev'] / f['m3_real']).median()))
