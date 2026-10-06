import pytest

from app.historico import ler_desc_caixa


@pytest.mark.parametrize('desc, esperado', [
    ('CAIXA 60X40X40 1,2KG', (60, 40, 40, 1200)),
    ('CX 40 x 60 x 30cm - 850g', (60, 40, 30, 850)),
    ('CAIXA 600X400X300MM 1.5 kg', (60, 40, 30, 1500)),
    ('CAIXA 52,5x35x20', (52.5, 35, 20, None)),
    ('FARDO', (None, None, None, None)),
    ('', (None, None, None, None)),
    (None, (None, None, None, None)),
])
def test_ler_desc_caixa(desc, esperado):
    r = ler_desc_caixa(desc)
    assert (r['comprimento'], r['largura'], r['altura'], r['peso_g']) == esperado
