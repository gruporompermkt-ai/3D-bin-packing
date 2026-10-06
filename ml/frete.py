'''
Modelo de frete treinado no histórico real do Sisplan (dados/historico/sisplan.json).

Uma linha por pedido: frete REAL pago (valor do CT-e lançado na entrada, NOTA_ENTRA_001 tipo 57, ligado à
nota de venda pela NOTA_REF_001, como o relatório R10 do Sisplan) x o que foi enviado (volumes do PEDIDO3 com
medidas lidas do OBS e peso), destino, transportadora e valor da mercadoria.
A cotação (FRETE_COTA_001.VALOR) fica só como comparação.
Treino supervisionado: 80% dos pedidos para treino, 20% separados para teste (sorteio fixo, seed 42).

Uso:  python -m ml.frete            (treina, avalia e grava dados/modelos/frete.joblib + relatório)
'''
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.historico import ler_obs_volume  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORIGEM = os.path.join(RAIZ, 'dados', 'historico', 'sisplan.json')
CTE = os.path.join(RAIZ, 'dados', 'historico', 'cte.json')
SAIDA = os.path.join(RAIZ, 'dados', 'modelos')
FATOR_CUBAGEM = 300          # kg/m³ (rodoviário)
SEED = 42

NUMERICAS = ['volumes', 'fardos', 'caixas', 'peso_kg', 'm3', 'peso_cubado_kg', 'peso_taxavel_kg',
             'maior_lado_cm', 'pecas', 'valor_mercadoria', 'mes']
CATEGORICAS = ['uf', 'transp', 'cep2']


def montar_base(caminho=ORIGEM, caminho_cte=CTE):
    d = json.load(open(caminho, encoding='utf-8'))
    fretes = pd.DataFrame(d['fretes'])
    vol = pd.DataFrame(d['volumes'])
    notas = pd.DataFrame(d['notas'])

    # frete: um pedido pode ter mais de um lançamento -> soma
    fretes['frete'] = fretes['frete'].astype(float)
    fretes['data'] = pd.to_datetime(fretes['data'], utc=True)
    f = fretes.groupby('pedido').agg(frete=('frete', 'sum'), data=('data', 'min'), transp=('transp', 'first'),
                                     transportadora=('transportadora', 'first'), uf=('uf', 'first'),
                                     cidade=('cidade', 'first'), cep=('cep', 'first'),
                                     lancamentos=('frete', 'size')).reset_index()

    # volumes: medidas do obs
    lido = vol['obs'].map(ler_obs_volume).apply(pd.Series)
    vol = pd.concat([vol, lido], axis=1)
    for c in ('peso', 'pecas'):
        vol[c] = vol[c].astype(float)
    vol['m3'] = vol['comprimento'] * vol['largura'] * vol['altura'] / 1e6
    vol['tem_medida'] = vol['comprimento'].notna()
    vol['fisico'] = ~vol['junto']          # "dentro do outro pedido" não é volume próprio
    vol['maior'] = vol[['comprimento', 'largura', 'altura']].max(axis=1)
    v = vol.groupby('pedido').agg(
        volumes=('fisico', 'sum'),
        fardos=('tipo', lambda s: int((s == 'fardo').sum())),
        caixas=('tipo', lambda s: int((s == 'caixa').sum())),
        peso_kg=('peso', 'sum'), m3=('m3', 'sum'), maior_lado_cm=('maior', 'max'), pecas=('pecas', 'sum'),
        sem_medida=('tem_medida', lambda s: int((~s & vol.loc[s.index, 'fisico']).sum())),
        sem_peso=('peso', lambda s: int(((s <= 0) & vol.loc[s.index, 'fisico']).sum())),
    ).reset_index()

    # valor da mercadoria: notas distintas do pedido
    notas['val_produtos'] = notas['val_produtos'].astype(float)
    nf = vol[['pedido', 'fatura']].drop_duplicates().merge(notas[['fatura', 'val_produtos']], on='fatura', how='left')
    nf = nf.groupby('pedido')['val_produtos'].sum().rename('valor_mercadoria').reset_index()

    cte = pd.DataFrame(json.load(open(caminho_cte, encoding='utf-8')))
    cte['frete_real'] = cte['frete_real'].astype(float)
    cte = cte.drop_duplicates(['pedido', 'cte']).groupby('pedido')['frete_real'].sum().reset_index()

    base = f.merge(v, on='pedido', how='inner').merge(nf, on='pedido', how='left')
    base = base.rename(columns={'frete': 'cotacao'}).merge(cte, on='pedido', how='left')
    base['peso_cubado_kg'] = base['m3'] * FATOR_CUBAGEM
    base['peso_taxavel_kg'] = base[['peso_kg', 'peso_cubado_kg']].max(axis=1)
    base['mes'] = base['data'].dt.month
    base['ano'] = base['data'].dt.year
    base['cep2'] = base['cep'].fillna('').str.replace(r'\D', '', regex=True).str[:2]
    for c in CATEGORICAS:
        base[c] = base[c].fillna('?').astype(str)
    return base


def filtrar(base):
    ''' só pedidos completos: todo volume físico com medida e peso; descarta erros grosseiros '''
    ok = (base['volumes'] > 0) & (base['sem_medida'] == 0) & (base['sem_peso'] == 0) & (base['frete_real'] > 0)
    b = base[ok].copy()
    b['frete'] = b['frete_real']
    # CT-e casado errado (nº de nota repetido de outro fornecedor) ou digitação: muito longe da cotação
    # ou R$/kg taxável fora de 1%..99%
    razao = b['frete'] / b['cotacao']
    rkg = b['frete'] / b['peso_taxavel_kg']
    lo, hi = rkg.quantile(0.01), rkg.quantile(0.99)
    b['outlier'] = (rkg < lo) | (rkg > hi) | (razao < 0.33) | (razao > 3)
    return b, ok.sum()


def metricas(real, prev):
    erro = np.abs(prev - real)
    rel = erro / real
    return dict(n=len(real), mae=round(float(erro.mean()), 2), erro_mediano=round(float(np.median(erro)), 2),
                mape_mediano=round(float(np.median(rel)) * 100, 1),
                dentro_10=round(float((rel <= 0.10).mean()) * 100, 1),
                dentro_20=round(float((rel <= 0.20).mean()) * 100, 1),
                r2_log=round(float(1 - np.sum((np.log(prev) - np.log(real)) ** 2)
                                   / np.sum((np.log(real) - np.log(real).mean()) ** 2)), 3))


class ReferenciaKg:
    ''' linha de base: mediana de R$/kg taxável por UF (como uma tabela de frete simples) '''

    def fit(self, X, y):
        rkg = y / X['peso_taxavel_kg']
        self.por_uf = rkg.groupby(X['uf']).median()
        self.geral = float(rkg.median())
        return self

    def predict(self, X):
        return X['peso_taxavel_kg'] * X['uf'].map(self.por_uf).fillna(self.geral)


def modelo_boosting():
    from sklearn.compose import ColumnTransformer
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OrdinalEncoder
    prep = ColumnTransformer([
        ('cat', OrdinalEncoder(handle_unknown='use_encoded_value', unknown_value=-1, encoded_missing_value=-1),
         CATEGORICAS),
        ('num', 'passthrough', NUMERICAS)])
    n_cat = len(CATEGORICAS)
    reg = HistGradientBoostingRegressor(loss='absolute_error', learning_rate=0.05, max_iter=600,
                                        max_leaf_nodes=15, min_samples_leaf=15, l2_regularization=1.0,
                                        categorical_features=list(range(n_cat)), random_state=SEED)
    return Pipeline([('prep', prep), ('reg', reg)])


class Log:
    ''' treina em log(frete): erro relativo, não deixa os pedidos grandes dominarem '''

    def __init__(self, m):
        self.m = m

    def fit(self, X, y):
        self.m.fit(X, np.log(y))
        return self

    def predict(self, X):
        return np.exp(self.m.predict(X))


def treinar(caminho=ORIGEM, saida=SAIDA):
    from sklearn.model_selection import train_test_split
    import joblib

    base = montar_base(caminho)
    b, completos = filtrar(base)
    usados = b[~b['outlier']]
    X, y = usados[NUMERICAS + CATEGORICAS + ['cotacao']], usados['frete']
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=SEED)

    modelos = {'referencia_kg_uf': ReferenciaKg(), 'boosting': Log(modelo_boosting())}
    res = {'cotacao_digitada': dict(treino=metricas(y_tr.values, X_tr['cotacao'].values),
                                    teste=metricas(y_te.values, X_te['cotacao'].values))}
    X_tr, X_te, X = (d.drop(columns='cotacao') for d in (X_tr, X_te, X))
    for nome, m in modelos.items():
        m.fit(X_tr, y_tr)
        res[nome] = dict(treino=metricas(y_tr.values, np.asarray(m.predict(X_tr))),
                         teste=metricas(y_te.values, np.asarray(m.predict(X_te))))

    # importância por permutação no teste (quanto o erro piora sem a variável)
    from sklearn.inspection import permutation_importance
    imp = permutation_importance(modelos['boosting'].m, X_te, np.log(y_te), n_repeats=10, random_state=SEED,
                                 scoring='neg_mean_absolute_error')
    importancia = sorted(zip(X.columns, imp.importances_mean), key=lambda t: -t[1])

    os.makedirs(saida, exist_ok=True)
    final = Log(modelo_boosting()).fit(X, y)       # modelo de uso: refeito com 100% dos dados
    joblib.dump(dict(modelo=final, numericas=NUMERICAS, categoricas=CATEGORICAS, fator_cubagem=FATOR_CUBAGEM),
                os.path.join(saida, 'frete.joblib'))

    prev = modelos['boosting'].predict(X_te)
    exemplos = usados.loc[X_te.index, ['pedido', 'uf', 'transportadora', 'volumes', 'peso_kg',
                                       'peso_cubado_kg', 'cotacao', 'frete']].assign(previsto=np.round(prev, 2))
    rel = dict(
        pedidos=int(len(base)), com_cte=int((base['frete_real'] > 0).sum()), completos=int(completos), outliers=int(b['outlier'].sum()),
        usados=int(len(usados)), treino=int(len(X_tr)), teste=int(len(X_te)),
        periodo=[str(usados['data'].min().date()), str(usados['data'].max().date())],
        resultados=res, importancia=[(n, round(float(v), 4)) for n, v in importancia],
        exemplos_teste=exemplos.head(15).to_dict('records'),
    )
    json.dump(rel, open(os.path.join(saida, 'relatorio_frete.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1, default=str)
    return rel


if __name__ == '__main__':
    r = treinar()
    print(json.dumps({k: v for k, v in r.items() if k != 'exemplos_teste'}, ensure_ascii=False, indent=1,
                     default=str))
    print(pd.DataFrame(r['exemplos_teste']).to_string(index=False))
