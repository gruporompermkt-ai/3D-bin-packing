'''
Estimativa de frete a partir do resultado da cubagem, com o modelo treinado no histórico real
(ml/frete.py -> frete.joblib). Sem o arquivo do modelo, a estimativa fica indisponível e a cubagem segue normal.
'''
import datetime
import os
import re

MODELO = os.environ.get('MODELO_FRETE', '/data/modelos/frete.joblib')
MIN_PEDIDOS_UF = 3        # transportadora entra na comparação se já levou ao menos isso para a UF

# faixas de CEP por UF (Correios)
_FAIXAS_CEP = [
    (1000, 19999, 'SP'), (20000, 28999, 'RJ'), (29000, 29999, 'ES'), (30000, 39999, 'MG'),
    (40000, 48999, 'BA'), (49000, 49999, 'SE'), (50000, 56999, 'PE'), (57000, 57999, 'AL'),
    (58000, 58999, 'PB'), (59000, 59999, 'RN'), (60000, 63999, 'CE'), (64000, 64999, 'PI'),
    (65000, 65999, 'MA'), (66000, 68899, 'PA'), (68900, 68999, 'AP'), (69000, 69299, 'AM'),
    (69300, 69399, 'RR'), (69400, 69899, 'AM'), (69900, 69999, 'AC'), (70000, 72799, 'DF'),
    (72800, 72999, 'GO'), (73000, 73699, 'DF'), (73700, 76799, 'GO'), (76800, 76999, 'RO'),
    (77000, 77999, 'TO'), (78000, 78899, 'MT'), (79000, 79999, 'MS'), (80000, 87999, 'PR'),
    (88000, 89999, 'SC'), (90000, 99999, 'RS'),
]

_cache = {}


def uf_do_cep(cep):
    d = re.sub(r'\D', '', cep or '')
    if len(d) < 5:
        return None
    n = int(d[:5])
    return next((uf for a, b, uf in _FAIXAS_CEP if a <= n <= b), None)


def carregar():
    ''' modelo em cache; recarrega se o arquivo mudar (retreino) '''
    try:
        mtime = os.path.getmtime(MODELO)
    except OSError:
        return None
    if _cache.get('mtime') != mtime:
        import joblib
        _cache.update(mtime=mtime, bundle=joblib.load(MODELO))
    return _cache['bundle']


def info():
    b = carregar()
    if b is None:
        return {'disponivel': False}
    return {'disponivel': True, 'periodo': b['periodo'], 'pedidos_treino': b['pedidos_treino'], 'teste': b['teste'],
            'transportadoras': [{k: t[k] for k in ('codigo', 'nome', 'pedidos')} for t in b['transportadoras']]}


def _caracteristicas(resultado, valor_mercadoria, cep, uf, mes):
    vols = resultado['volumes']
    peso = sum(v['peso_real_kg'] for v in vols)
    m3 = sum(v['volume_m3'] for v in vols)
    cubado = m3 * 300      # o modelo foi treinado com 300 kg/m³
    return {
        'volumes': len(vols),
        'fardos': sum(v['tipo'] == 'fardo' for v in vols),
        'caixas': sum(v['tipo'] == 'caixa' for v in vols),
        'peso_kg': peso, 'm3': m3, 'peso_cubado_kg': cubado, 'peso_taxavel_kg': max(peso, cubado),
        'maior_lado_cm': max(max(v['dimensoes_cm']) for v in vols),
        'pecas': resultado['totais']['pecas'],
        'valor_mercadoria': valor_mercadoria if valor_mercadoria else float('nan'),
        'mes': mes,
        'uf': uf or '?', 'cep2': re.sub(r'\D', '', cep or '')[:2] or '?',
    }


def estimar(resultado, cep=None, uf=None, transportadora=None, valor_mercadoria=None, hoje=None):
    '''
    Frete estimado para o plano escolhido pela cubagem.
    Com transportadora: só ela. Sem: as que já levaram para a UF (mais barata primeiro).
    '''
    b = carregar()
    if b is None:
        return {'disponivel': False, 'motivo': 'modelo de frete não instalado'}
    if not resultado.get('ok') or not resultado.get('volumes'):
        return {'disponivel': False, 'motivo': 'sem volumes'}
    import numpy as np
    import pandas as pd
    uf = (uf or uf_do_cep(cep) or '').upper() or None
    if not uf:
        return {'disponivel': False, 'motivo': 'informe o CEP ou a UF de destino'}
    mes = (hoje or datetime.date.today()).month
    base = _caracteristicas(resultado, valor_mercadoria, cep, uf, mes)

    nomes = {t['codigo']: t['nome'] for t in b['transportadoras']}
    if transportadora:
        opcoes = [transportadora]
    else:
        opcoes = [t['codigo'] for t in b['transportadoras'] if t['ufs'].get(uf, 0) >= MIN_PEDIDOS_UF]
        if not opcoes:   # UF com pouco histórico: as mais usadas no geral
            opcoes = [t['codigo'] for t in b['transportadoras'][:5]]
    linhas = pd.DataFrame([dict(base, transp=c) for c in opcoes])[b['numericas'] + b['categoricas']]
    prev = b['pipeline'].predict(linhas)
    if b['alvo'] == 'log':
        prev = np.exp(prev)
    est = sorted(({'transportadora': c, 'nome': nomes.get(c, c), 'valor': round(float(v), 2),
                   'pedidos_uf': next((t['ufs'].get(uf, 0) for t in b['transportadoras'] if t['codigo'] == c), 0)}
                  for c, v in zip(opcoes, prev)), key=lambda e: e['valor'])
    return {
        'disponivel': True, 'uf': uf, 'estimativas': est,
        'sem_valor_mercadoria': not valor_mercadoria,
        'precisao': {'erro_tipico_pct': b['teste']['mape_mediano'], 'dentro_20_pct': b['teste']['dentro_20']},
        'base': {k: (round(v, 3) if isinstance(v, float) and v == v else v) for k, v in base.items()
                 if k in ('volumes', 'peso_kg', 'm3', 'peso_taxavel_kg', 'pecas')},
    }
