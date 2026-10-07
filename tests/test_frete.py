import joblib
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import db, frete
from app.main import app
from ml.frete import CATEGORICAS, NUMERICAS, modelo_boosting

PLANILHA = "38\t34,33\t24,67\t2,20\t508,33\t1\t0,7\t0,92\n"


@pytest.mark.parametrize('cep, uf', [('01310-100', 'SP'), ('65130000', 'MA'), ('70040-010', 'DF'),
                                     ('73700000', 'GO'), ('69900-000', 'AC'), ('90000000', 'RS'), ('123', None),
                                     (None, None)])
def test_uf_do_cep(cep, uf):
    assert frete.uf_do_cep(cep) == uf


@pytest.fixture()
def modelo(tmp_path, monkeypatch):
    ''' modelo sintético: frete = 5 R$/kg (SP) ou 10 R$/kg (MA) + 1% da mercadoria '''
    rng = np.random.default_rng(0)
    n = 400
    df = pd.DataFrame({c: rng.uniform(1, 50, n) for c in NUMERICAS})
    df['uf'] = rng.choice(['SP', 'MA'], n)
    df['transp'] = rng.choice(['A', 'B'], n)
    df['cep2'] = np.where(df['uf'] == 'SP', '01', '65')
    y = df['peso_kg'] * np.where(df['uf'] == 'SP', 5, 10) * np.where(df['transp'] == 'B', 1.5, 1) \
        + df['valor_mercadoria'] * 0.01 + 10
    pipe = modelo_boosting().fit(df[NUMERICAS + CATEGORICAS], np.log(y))
    caminho = tmp_path / 'frete.joblib'
    joblib.dump(dict(pipeline=pipe, alvo='log', numericas=NUMERICAS, categoricas=CATEGORICAS, fator_cubagem=300,
                     teste={'mape_mediano': 8.0, 'dentro_20': 80.0}, periodo=['2023-01-01', '2026-10-01'],
                     pedidos_treino=n,
                     transportadoras=[dict(codigo='A', nome='TRANSP A', pedidos=200, ufs={'SP': 100, 'MA': 100}),
                                      dict(codigo='B', nome='TRANSP B', pedidos=200, ufs={'SP': 100})]),
                caminho)
    monkeypatch.setattr(frete, 'MODELO', str(caminho))
    frete._cache.clear()
    return caminho


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, 'DB_PATH', str(tmp_path / 't.db'))
    with TestClient(app) as c:
        c.post('/api/produtos/importar', json={'codigo': 'F2505', 'texto': PLANILHA})
        c.put('/api/embalagens/CX', json={'tipo': 'caixa', 'comprimento': 60, 'largura': 40, 'altura': 40,
                                          'peso_max_g': 30000})
        yield c


PEDIDO = {'itens': [{'codigo': 'F2505', 'tamanho': '38', 'quantidade': 20}], 'iteracoes': 2}


def test_sem_modelo_a_cubagem_segue(client, monkeypatch, tmp_path):
    monkeypatch.setattr(frete, 'MODELO', str(tmp_path / 'nao_existe.joblib'))
    frete._cache.clear()
    assert client.get('/api/frete').json() == {'disponivel': False}
    r = client.post('/api/cubagem', json=dict(PEDIDO, cep='01310100')).json()
    assert r['ok'] and r['frete']['disponivel'] is False


def test_sem_destino_nao_estima(client, modelo):
    r = client.post('/api/cubagem', json=PEDIDO).json()
    assert r['ok'] and 'frete' not in r


def test_compara_transportadoras_da_uf(client, modelo):
    info = client.get('/api/frete').json()
    assert info['disponivel'] and [t['codigo'] for t in info['transportadoras']] == ['A', 'B']
    r = client.post('/api/cubagem', json=dict(PEDIDO, cep='01310-100', valor_mercadoria=2000)).json()
    f = r['frete']
    assert f['disponivel'] and f['uf'] == 'SP'
    assert [e['transportadora'] for e in f['estimativas']] == ['A', 'B']      # A é mais barata
    assert f['estimativas'][0]['valor'] < f['estimativas'][1]['valor']
    assert f['base']['volumes'] == r['totais']['volumes'] and f['base']['pecas'] == 20
    # MA: só a A atende
    r = client.post('/api/cubagem', json=dict(PEDIDO, uf='MA', valor_mercadoria=2000)).json()
    assert [e['transportadora'] for e in r['frete']['estimativas']] == ['A']


def test_transportadora_escolhida(client, modelo):
    r = client.post('/api/cubagem', json=dict(PEDIDO, cep='01310100', transportadora='B')).json()
    f = r['frete']
    assert [e['transportadora'] for e in f['estimativas']] == ['B'] and f['sem_valor_mercadoria']
