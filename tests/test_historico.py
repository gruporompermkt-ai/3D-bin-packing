import pytest

from app.historico import ler_obs_volume


# formatos reais encontrados no PEDIDO3.OBS
@pytest.mark.parametrize('obs, esperado', [
    ('FD: 52X42X93 CM', ('fardo', 93, 52, 42, False)),
    ('CX: 08X20X28 CM', ('caixa', 28, 20, 8, False)),
    ('FD: 103X50X56 CM ', ('fardo', 103, 56, 50, False)),
    ('FD:100X50X40 CM', ('fardo', 100, 50, 40, False)),
    ('FD: 105-62-34', ('fardo', 105, 62, 34, False)),
    ('FD:105X57X46CM', ('fardo', 105, 57, 46, False)),
    ('FD: 102 X 42 X 32 CM ', ('fardo', 102, 42, 32, False)),
    ('CX : 35 X 35 X 13 CM', ('caixa', 35, 35, 13, False)),
    ('CX35X10X35 CM', ('caixa', 35, 35, 10, False)),
    ('CX;35X10X35 CM', ('caixa', 35, 35, 10, False)),
    ('CX: 35X 6 X35 CM', ('caixa', 35, 35, 6, False)),
    ('FD38X50X36 CM', ('fardo', 50, 38, 36, False)),
    ('DENTRO DO OUTRO PEDIDO', (None, None, None, None, True)),
    ('DENTRO DO OUTRO FARDO', ('fardo', None, None, None, True)),
    ('JUNTO COM O OUTRO PEDIDO', (None, None, None, None, True)),
    ('01 FARDO', ('fardo', None, None, None, False)),
    ('EM UMA CAIXA', ('caixa', None, None, None, False)),
    ('', (None, None, None, None, False)),
    (None, (None, None, None, None, False)),
])
def test_ler_obs_volume(obs, esperado):
    r = ler_obs_volume(obs)
    assert (r['tipo'], r['comprimento'], r['largura'], r['altura'], r['junto']) == esperado
