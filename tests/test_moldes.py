"""Modos de fardo em grade de células: retângulo arredondado e molde (contorno de uma foto)."""
import itertools
import math

import numpy as np
import pytest

from py3dbp import Bin
from py3dbp import moldes
from py3dbp.cartonizer import Embalagem, Produto, cartonize

F1078_P = Produto("F1078", "P", 16, 16, 7, 260, 0, 0.6)
# octógono (cantos chanfrados) como se fosse o contorno de uma foto
OCTOGONO = [[.3, 0], [.7, 0], [1, .3], [1, .7], [.7, 1], [.3, 1], [0, .7], [0, .3]]


def test_mascara_arredondada_tira_os_cantos():
    m = moldes.mascara_arredondada(40, 30, 10)
    assert m.shape == (40, 30)
    assert not m[0, 0] and not m[39, 29] and not m[0, 29] and not m[39, 0]   # cantos
    assert m[20, 15] and m[0, 15] and m[20, 0]                               # meio das bordas
    area = 40 * 30 - (4 - math.pi) * 10 ** 2
    assert abs(m.sum() - area) / area < 0.03


def test_mascara_sem_raio_e_retangulo():
    assert moldes.mascara_arredondada(10, 8, 0).all()


def test_mascara_de_poligono():
    m = moldes.mascara_poligono(40, 40, OCTOGONO)
    assert not m[0, 0] and m[20, 20] and m[0, 20]
    area = moldes.area_poligono(moldes.contorno_poligono(40, 40, OCTOGONO))
    assert abs(m.sum() - area) / area < 0.05


def test_validar_molde():
    for ruim in ([], [[0, 0], [1, 1]], [[0, 0], [2, 0], [1, 1]], [[0, 0], [.5, .5], [1, 1]]):
        with pytest.raises(ValueError):
            moldes.validar_molde(ruim)
    moldes.validar_molde(OCTOGONO)


def test_bin_mascara_rejeita_canto_aceita_meio():
    b = Bin("m", (40, 30, 50), 100000, shape="mask", mask=moldes.mascara_arredondada(40, 30, 10))
    b.formatNumbers(1)
    assert b._inside([0, 0, 0], [10, 10, 5]) is False        # canto arredondado
    assert b._inside([10, 5, 0], [20, 20, 5]) is True
    assert b._inside([35, 10, 0], [10, 5, 5]) is False       # passa da borda
    assert len(b.seedPivots()) > 0


def _celulas_ok(layout, mascara):
    for q in layout:
        i0, j0 = int(math.floor(q["x"] + 1e-6)), int(math.floor(q["y"] + 1e-6))
        i1, j1 = int(math.ceil(q["x"] + q["c"] - 1e-6)), int(math.ceil(q["y"] + q["l"] - 1e-6))
        assert mascara[i0:i1, j0:j1].all(), q


@pytest.mark.parametrize("forma,extra", [("arredondado", {"raio_canto": 8}), ("molde", {"molde": OCTOGONO})])
def test_cartonize_respeita_o_molde(forma, extra):
    fd = Embalagem("FD", 40, 40, 80, 30000, tipo="fardo", forma=forma, **extra)
    r = cartonize([(F1078_P, 20)], [fd], iteracoes=3)
    v = r["volumes"][0]
    assert r["ok"] and r["totais"]["pecas"] == 20 and v["forma"] == forma
    c, l, a = v["dimensoes_cm"]
    assert c <= 40 and l <= 40 and a <= 80
    assert v["contorno_cm"] and v["volume_real_m3"] < v["volume_m3"]
    # cada pilha fica dentro do contorno desenhado (células do molde nas medidas finais)
    if forma == "arredondado":
        m = moldes.mascara_arredondada(c, l, 8)
    else:
        m = moldes.mascara_poligono(c, l, OCTOGONO)
    _celulas_ok(v["layout"], m)
    for x, y in itertools.combinations(v["layout"], 2):
        assert not all(min(x[k] + x[d], y[k] + y[d]) - max(x[k], y[k]) > 1e-6
                       for k, d in (("x", "c"), ("y", "l"), ("z", "a")))


def test_arredondado_cabe_menos_que_retangulo_e_mais_que_cilindro():
    """o retângulo arredondado fica entre o cilindro (canto máximo) e o retângulo (sem canto)"""
    from py3dbp.cartonizer import pack_one
    pedido = [(F1078_P, 200)]
    pecas = {}
    for forma, extra in (("retangular", {}), ("arredondado", {"raio_canto": 10}), ("cilindrico", {})):
        fd = Embalagem("FD", 40, 40, 30, 300000, tipo="fardo", forma=forma, **extra)
        vol, _ = pack_one(fd, pedido, iteracoes=2)
        pecas[forma] = vol.pecas
    assert pecas["cilindrico"] <= pecas["arredondado"] <= pecas["retangular"]
