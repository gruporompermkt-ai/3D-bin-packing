"""Reproduções dos bugs encontrados no código original (jerry800416/3D-bin-packing).

Cada teste falha no código original e passa depois da correção.
"""
import itertools

from py3dbp import Bin, Item, Packer
from py3dbp.auxiliary_methods import intersect


def cube(partno, whd, weight=1, updown=True, name="t", level=1):
    return Item(partno, name, "cube", whd, weight, level, 100, updown, "red")


def assert_valid(bin_):
    """Nenhum item fora da caixa e nenhum par sobreposto."""
    for it in bin_.items:
        w, h, d = it.getDimension()
        x, y, z = it.position
        assert x >= 0 and y >= 0 and z >= 0, it.string()
        assert x + w <= bin_.width and y + h <= bin_.height and z + d <= bin_.depth, it.string()
    for a, b in itertools.combinations(bin_.items, 2):
        assert not intersect(a, b), f"{a.string()} x {b.string()}"


def test_putitem_tenta_todas_as_rotacoes():
    """Bug 2: o `return fit` dentro do laço desistia na 1ª rotação que colidia."""
    b = Bin("b", (3, 3, 1), 100)
    obst = cube("obst", (1, 2, 1))
    obst.position = [0, 1, 0]
    b.items.append(obst)
    item = cube("item", (1, 2, 1), updown=False)  # rotação 0 colide, rotação 1 (2x1) cabe
    assert b.putItem(item, [0, 0, 0]) is True
    assert b.items[-1].getDimension() == [2, 1, 1]
    assert_valid(b)


def test_caixa_vazia_nao_quebra_o_pack():
    """Divisão por zero em gravityCenter quando nenhum item coube na caixa."""
    p = Packer()
    p.addBin(Bin("pequena", (1, 1, 1), 100))
    p.addItem(cube("grande", (5, 5, 5)))
    p.pack()
    assert p.bins[0].items == []
    assert [i.partno for i in p.unfit_items] == ["grande"]


def test_partno_repetido_nao_duplica_nem_perde_item():
    """Bug 7: remoção por partno apagava o item errado (o maior), e o menor era embalado 2x."""
    p = Packer()
    p.addBin(Bin("b1", (2, 2, 2), 100))
    p.addBin(Bin("b2", (10, 10, 10), 100))
    p.addItem(cube("X", (5, 5, 5), level=1))  # level ordena: o grande vem antes na lista
    p.addItem(cube("X", (1, 1, 1), level=2))
    p.pack(bigger_first=False, distribute_items=True)  # b1 (pequena) é preenchida primeiro
    vols = sorted(float(i.getVolume()) for b in p.bins for i in b.items)
    assert vols == [1.0, 125.0]
    assert p.unfit_items == []


def test_posicao_respeita_casas_decimais():
    """A posição era arredondada para inteiro mesmo com number_of_decimals=1 (gerava sobreposição)."""
    p = Packer()
    p.addBin(Bin("b", (10, 3, 3), 100))
    for n in range(3):
        p.addItem(cube(f"i{n}", (2.5, 3, 3)))
    p.pack(number_of_decimals=1)
    b = p.bins[0]
    assert len(b.items) == 3
    assert sorted(float(i.position[0]) for i in b.items) == [0.0, 2.5, 5.0]
    assert_valid(b)


def test_binding_padrao_nao_e_compartilhado():
    """Bug 6: argumento padrão mutável."""
    import inspect
    assert inspect.signature(Packer.pack).parameters["binding"].default is None


def test_import_sem_matplotlib(monkeypatch):
    """O núcleo não deve exigir matplotlib (só o Painter)."""
    import importlib
    import sys
    for mod in [m for m in sys.modules if m.startswith("py3dbp")]:
        monkeypatch.delitem(sys.modules, mod)
    monkeypatch.setitem(sys.modules, "matplotlib", None)
    importlib.import_module("py3dbp")
