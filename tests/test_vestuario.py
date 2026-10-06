"""Dobra e compressão de vestuário. Peça de referência: F2505 tamanho 38
(34,33 x 24,67 x 2,20 cm, 508,33 g, 1 dobra, compressão 0,95)."""
import itertools

import pytest

from py3dbp import Bin, Item, Packer
from py3dbp.auxiliary_methods import intersect
from py3dbp.cartonizer import Embalagem, Produto, cartonize, pack_one

F2505_38 = Produto("F2505", "38", 34.33, 24.67, 2.20, 508.33, dobras=1, compressao=0.95)


def pilha(qtd, compressao=0.95, dobras=1, peso=508.33):
    return Item("F2505/38", "F2505/38", "cube", (34.33, 24.67, 2.20), peso, 2, 100, False, "blue",
                fold_count=dobras, compress_ratio=compressao, quantity=qtd)


def empacota(caixa, *itens, peso_max=100000):
    p = Packer()
    b = Bin("cx", caixa, peso_max)
    p.addBin(b)
    for it in itens:
        p.addItem(it)
    p.pack(bigger_first=True, number_of_decimals=1)
    return p, b


def pecas(b):
    return sum(i.quantity for i in b.items)


def sem_sobreposicao(b):
    for it in b.items:
        w, h, d = it.getDimension()
        x, y, z = it.position
        assert x + w <= b.width and y + h <= b.height and z + d <= b.depth, it.string()
    for a, c in itertools.combinations(b.items, 2):
        assert not intersect(a, c), f"{a.string()} x {c.string()}"


def test_formas_da_peca():
    estados = pilha(1).foldStates()
    assert len(estados) == 3                          # sem dobra, dobra no comprimento, dobra na largura
    w, h, t, a, b = estados[0]
    assert (w, h, a, b) == (34.33, 24.67, 0, 0) and t == pytest.approx(2.09)
    w, h, t, a, b = estados[1]
    assert (w, h, a, b) == (34.33 / 2, 24.67, 1, 0) and t == pytest.approx(4.18)
    w, h, t, a, b = estados[2]
    assert (w, h, a, b) == (34.33, 24.67 / 2, 0, 1) and t == pytest.approx(4.18)


def test_duas_dobras_combina_comprimento_e_largura():
    estados = [(a, b) for *_, a, b in pilha(1, dobras=2).foldStates()]
    assert estados == [(0, 0), (1, 0), (0, 1), (2, 0), (1, 1), (0, 2)]


def test_compressao_invalida():
    for r in (0, -0.1, 1.01):
        with pytest.raises(ValueError):
            pilha(1, compressao=r)


def test_pilha_sem_dobra_quando_cabe_aberta():
    _, b = empacota((40, 30, 25), pilha(10))
    assert pecas(b) == 10
    assert all(i.fold_state == 0 for i in b.items)
    assert float(b.items[0].depth) == pytest.approx(20.9)  # 10 x 2,20 x 0,95
    sem_sobreposicao(b)


def test_compressao_aumenta_pecas_por_coluna():
    # 24 cm de altura: 24 / 2,20 = 10,9 -> 10 peças;  24 / 2,09 = 11,5 -> 11 peças
    _, b = empacota((40, 30, 24), pilha(20, compressao=1.0))
    assert pecas(b) == 10
    _, b = empacota((40, 30, 24), pilha(20, compressao=0.95))
    assert pecas(b) == 11


def test_dobra_so_quando_precisa():
    # 30 x 30: a peça aberta (34,33 x 24,67) não cabe em nenhuma rotação -> dobra no comprimento
    p, b = empacota((30, 30, 20), pilha(10))
    assert {i.foldDescription() for i in b.items} == {"dobrada 1x no comprimento"}
    # coluna de 20 cm / 4,18 = 4 peças; base 17,2 x 24,7 numa caixa 30 x 30 = 1 coluna
    assert pecas(b) == 4
    assert sum(i.quantity for i in p.unfit_items) == 6
    sem_sobreposicao(b)


def test_sem_dobra_permitida_nao_cabe():
    _, b = empacota((30, 30, 20), pilha(10, dobras=0))
    assert pecas(b) == 0


def test_limite_de_peso_antes_do_volume():
    _, b = empacota((40, 30, 25), pilha(10), peso_max=2000)
    assert pecas(b) == 3                                 # 3 x 508,33 = 1525 g; a 4ª passaria de 2000 g
    assert float(b.getTotalWeight()) <= 2000


def test_varias_colunas_lado_a_lado():
    # 70 x 50 x 21: base comporta 2 x 2 colunas; cada coluna 21 / 2,09 = 10 peças
    _, b = empacota((70, 50, 21), pilha(100))
    assert pecas(b) == 40
    sem_sobreposicao(b)


def test_pedido_misto_rigido_e_vestuario():
    mochila = Item("MOC", "MOC", "cube", (40, 30, 20), 1500, 1, 100, True, "red")
    p, b = empacota((70, 50, 40), mochila, pilha(30))
    moc = [i for i in b.items if i.partno == "MOC"]
    assert moc and float(moc[0].position[2]) == 0          # rígido entra primeiro, no fundo
    assert pecas(b) == 31
    assert any(float(i.position[2]) >= 20 for i in b.items if i.is_stack)  # roupa por cima da mochila
    sem_sobreposicao(b)


def test_cartonize_numero_de_caixas():
    caixa = Embalagem("CX-TESTE", 70, 50, 21, 30000, tara_g=400)
    r = cartonize([(F2505_38, 100)], [caixa], fator_cubagem=300)
    assert r["ok"]
    assert r["totais"]["pecas"] == 100
    assert r["totais"]["volumes"] == 3                   # 40 + 40 + 20
    v = r["volumes"][0]
    assert v["peso_real_kg"] == pytest.approx((40 * 508.33 + 400) / 1000, abs=0.01)
    assert v["peso_cubado_kg"] == pytest.approx(70 * 50 * 21 / 1e6 * 300)


def test_cartonize_troca_ultima_caixa_pela_menor():
    grande = Embalagem("G", 70, 50, 21, 30000, custo=10)
    pequena = Embalagem("P", 36, 26, 21, 30000, custo=4)
    r = cartonize([(F2505_38, 45)], [grande, pequena])
    # só "P": 10 por caixa = 5 caixas (custo 20). "G" 40 + resto 5 numa "P" = custo 14
    assert [v["embalagem"] for v in r["volumes"]] == ["G", "P"]
    assert r["totais"]["custo_total"] == 14


def test_cartonize_item_que_nao_cabe():
    r = cartonize([(F2505_38, 1)], [Embalagem("MINI", 10, 10, 10, 1000)])
    assert r["ok"] is False


def test_pack_one_varios_tamanhos():
    p40 = Produto("F2505", "40", 34.50, 26.67, 2.20, 506.33, 1, 0.95)
    vol, sobra = pack_one(Embalagem("CX", 70, 55, 30, 30000), [(F2505_38, 10), (p40, 10)])
    assert sobra == []
    assert sorted((i["tamanho"], i["qtd"]) for i in vol.itens) == [("38", 10), ("40", 10)]
    layout_valido(vol.layout, (70, 55, 30))


def test_layout_para_visualizacao():
    r = cartonize([(F2505_38, 25)], [Embalagem("CX", 70, 50, 21, 30000)])
    lay = r["volumes"][0]["layout"]
    assert sum(b["qtd"] for b in lay) == 25
    assert [b["z"] for b in lay] == sorted(b["z"] for b in lay)   # ordem de montagem: de baixo para cima
    for b in lay:                                                  # tudo dentro da caixa
        assert b["x"] + b["c"] <= 70 and b["y"] + b["l"] <= 50 and b["z"] + b["a"] <= 21


# ---------------------------------------------------------------- fardo
FARDO = Embalagem("FD", 70, 50, 60, 30000, tara_g=150, tipo="fardo")


def test_fardo_acompanha_conteudo():
    r = cartonize([(F2505_38, 20)], [FARDO], fator_cubagem=300)
    v = r["volumes"][0]
    assert r["totais"]["volumes"] == 1 and r["totais"]["pecas"] == 20
    c, l, a = v["dimensoes_cm"]
    # base 70x50 comporta 2x2 colunas de 5 -> 70 x 50 x 11 cm; com paredes flexíveis o fardo
    # fica do tamanho do conteúdo e não pode ser maior que isso
    assert c * l * a <= 70 * 50 * 11
    assert c <= 70 and l <= 50 and a <= 60
    assert v["max_cm"] == [70, 50, 60]
    assert v["peso_cubado_kg"] == pytest.approx(c * l * a / 1e6 * 300, abs=0.001)
    layout_valido(v["layout"], (c, l, a))


def test_fardo_mais_conteudo_fica_maior():
    volumes = [cartonize([(F2505_38, q)], [FARDO])["volumes"][0]["volume_m3"] for q in (8, 40, 80)]
    assert volumes == sorted(volumes) and volumes[0] < volumes[-1]


def test_fardo_respeita_altura_maxima_e_abre_outro():
    # 60 cm / 2,09 = 28 peças por coluna x 4 colunas = 112 por fardo (peso liberado para testar só a altura)
    fardo = Embalagem("FD", 70, 50, 60, 100000, tara_g=150, tipo="fardo")
    r = cartonize([(F2505_38, 150)], [fardo])
    alt = [v["dimensoes_cm"][2] for v in r["volumes"]]
    assert r["totais"]["volumes"] == 2 and r["totais"]["pecas"] == 150
    assert all(a <= 60 for a in alt) and alt[1] < alt[0]


def test_fardo_ou_caixa_pelo_peso_taxavel():
    caixa = Embalagem("CX", 70, 50, 60, 30000)
    r = cartonize([(F2505_38, 20)], [caixa, FARDO])
    assert r["volumes"][0]["embalagem"] == "FD"      # mesma base, mas o fardo só cobra a altura usada


def test_fardo_limitado_pelo_peso():
    # 30 kg - 150 g de tara = 29,85 kg -> 58 peças de 508,33 g (59 passaria)
    r = cartonize([(F2505_38, 150)], [FARDO])
    assert [sum(i["qtd"] for i in v["itens"]) for v in r["volumes"]] == [58, 58, 34]
    assert all(v["peso_real_kg"] <= 30 for v in r["volumes"])


# ---------------------------------------------------------------- orientação, iterações, cilindro
def layout_valido(layout, dims, cilindro=False):
    """sem sobreposição e dentro da embalagem (no cilindro, dentro do círculo)"""
    for b in layout:
        assert b["x"] >= -1e-6 and b["y"] >= -1e-6 and b["z"] >= -1e-6, b
        assert b["x"] + b["c"] <= dims[0] + 1e-6 and b["y"] + b["l"] <= dims[1] + 1e-6 and b["z"] + b["a"] <= dims[2] + 1e-6, b
        if cilindro:
            r = dims[0] / 2
            fx = max(abs(b["x"] - r), abs(b["x"] + b["c"] - r))
            fy = max(abs(b["y"] - r), abs(b["y"] + b["l"] - r))
            assert fx * fx + fy * fy <= r * r + 0.05, b
    for a, b in itertools.combinations(layout, 2):
        sobrepoe = all(min(a[k] + a[d], b[k] + b[d]) - max(a[k], b[k]) > 1e-6 for k, d in (("x", "c"), ("y", "l"), ("z", "a")))
        assert not sobrepoe, (a, b)


def test_pilha_em_pe_ocupa_o_vao():
    # caixa 36 x 22 x 36: a peça deitada (34,33 x 24,67) não cabe na base; em pé (ao longo da largura) cabe
    p, b = empacota((36, 22, 36), pilha(10, compressao=0.95, dobras=0))
    assert pecas(b) == 0                                   # só deitada: não cabe
    livre = Item("F2505/38", "F2505/38", "cube", (34.33, 24.67, 2.20), 508.33, 2, 100, True, "blue",
                 compress_ratio=0.95, quantity=10)
    p, b = empacota((36, 22, 36), livre)               # 34,33 x 24,67 deitada não cabe; em pé sim
    assert pecas(b) == 10
    assert any(Bin.STACK_AXIS[i.rotation_type] != 2 for i in b.items)  # ficou em pé
    sem_sobreposicao(b)


def test_iteracoes_nao_pioram():
    pedido = [(F2505_38, 30), (Produto("F1078", "P", 30, 25, 3, 300, 0, 0.9), 15),
              (Produto("F1078", "PP", 15, 15, 4.2, 200, 0, 0.9), 10)]
    emb = Embalagem("002", 30, 40, 150, 30000, tipo="fardo")
    volumes = [cartonize(pedido, [emb], iteracoes=n)["volumes"][0]["volume_m3"] for n in (1, 8)]
    assert volumes[1] <= volumes[0]


def test_fardo_cilindrico_flexivel():
    fd = Embalagem("CIL", 80, 0, 100, 30000, tipo="fardo", forma="cilindrico")
    r = cartonize([(F2505_38, 30)], [fd], iteracoes=4)
    v = r["volumes"][0]
    assert r["ok"] and r["totais"]["pecas"] == 30
    d, d2, h = v["dimensoes_cm"]
    assert d == d2 and d <= 80 and h <= 100
    assert v["diametro_max_cm"] == 80 and v["forma"] == "cilindrico"
    assert v["peso_cubado_kg"] == pytest.approx(d * d * h / 1e6 * 300, abs=0.001)  # cobrado pelo "caixote"
    assert v["volume_real_m3"] == pytest.approx(3.14159 * (d / 2) ** 2 * h / 1e6, rel=1e-3)
    layout_valido(v["layout"], (d, d, h), cilindro=True)


def test_cilindro_nao_aceita_canto_fora_do_circulo():
    b = Bin("cil", (40, 40, 50), 100000, shape="cylinder")
    b.formatNumbers(1)
    assert b._inside([0, 0, 0], [10, 10, 1]) is False          # canto (0,0) está fora do círculo
    assert b._inside([10, 10, 0], [20, 20, 1]) is True
    assert len(b.seedPivots()) > 0


# ---------------------------------------------------------------- peça curvada em L, fardo flexível
def calca(qtd, curvavel=True):
    return Item("CALCA", "CALCA", "cube", (50, 10, 1), 300, 2, 100, False, "blue",
                compress_ratio=0.9, quantity=qtd, bendable=curvavel)


def test_peca_curvada_em_l_ocupa_o_canto():
    # 50 cm não cabe reto numa caixa 40 x 40 (nem girada); curvada em L: braços 40 + 20 (a + b = 50 + 10)
    _, b = empacota((40, 40, 10), calca(5, curvavel=False))
    assert pecas(b) == 0
    _, b = empacota((40, 40, 10), calca(5))
    assert pecas(b) == 5
    partes = sorted(i.bend for i in b.items)
    assert partes == ["A", "B"]                                    # um L = dois blocos
    a_, b_ = sorted(b.items, key=lambda i: i.bend)
    assert a_.quantity == 5 and b_.quantity == 0 and b_.layers == 5
    assert float(b_.weight) == 0 and float(a_.weight) == pytest.approx(5 * 300)
    # área preservada: braço A (a x 10) + braço B (10 x (b - 10)) = 50 x 10
    area = float(a_.width * a_.height + b_.width * b_.height)
    assert area == pytest.approx(500, abs=2)
    sem_sobreposicao(b)


def test_l_so_quando_reto_nao_cabe():
    _, b = empacota((60, 40, 10), calca(5))
    assert pecas(b) == 5 and all(i.bend is None for i in b.items)


def test_fardo_flexivel_escolhe_formato():
    fd = Embalagem("FX", 60, 60, 100, 30000, tipo="fardo")                    # forma padrão: flexível
    r = cartonize([(F2505_38, 30)], [fd], iteracoes=3)
    v = r["volumes"][0]
    assert v["forma"] in ("retangular", "cilindrico")
    so_ret = cartonize([(F2505_38, 30)], [Embalagem("R", 60, 60, 100, 30000, tipo="fardo", forma="retangular")], iteracoes=3)
    assert v["volume_m3"] <= so_ret["volumes"][0]["volume_m3"] + 1e-9


# ---------------------------------------------------------------- compactação do topo (fardo)
def test_compactacao_deita_as_pecas_do_topo():
    # caso real: 69 x F2505/40 no fardo 002 (30 x 40 x até 150) com a estratégia "em pé (outro lado)
    # primeiro": a última pilha (9 calças) ficava em pé no topo -> 138 cm; deitada o fardo cai para 121
    from py3dbp import main as core
    from py3dbp.cartonizer import _pack_strategy, estrategias
    p40 = Produto("F2505", "40", 34.5, 26.67, 2.2, 506.33, 1, 0.95)
    emb = Embalagem("002", 30, 40, 150, 35000, tipo="fardo", forma="retangular")
    est = [e for e in estrategias(3) if e[0] == "em pé (outro lado) primeiro"][0]
    original = core.Bin.compactTop
    try:
        core.Bin.compactTop = lambda self, *a, **k: None
        antes, _ = _pack_strategy(emb, (30, 40, 150), [(p40, 69)], est, "retangular")
    finally:
        core.Bin.compactTop = original
    depois, _ = _pack_strategy(emb, (30, 40, 150), [(p40, 69)], est, "retangular")
    assert antes.pecas == depois.pecas == 69
    assert antes.dimensoes_finais[2] == 138
    assert depois.dimensoes_finais[2] == 121
    layout_valido(depois.layout, (30, 40, 150))


def test_mais_iteracoes_nunca_piora():
    p40 = Produto("F2505", "40", 34.5, 26.67, 2.2, 506.33, 1, 0.95)
    emb = Embalagem("002", 30, 40, 150, 35000, tipo="fardo", forma="retangular")
    vols = [cartonize([(p40, 69)], [emb], iteracoes=n)["volumes"][0]["volume_m3"] for n in (1, 3, 8)]
    assert vols[2] <= vols[1] <= vols[0]


# ---------------------------------------------------------------- compressão lateral e peças deitadas
def test_compressao_lateral_poe_duas_calcas_lado_a_lado():
    # caixa 48 de largura: 2 x 26,67 = 53,3 não cabe; comprimidas a 88% (23,5 cada) cabem lado a lado
    def calca(squeeze):
        return Item("F2505/40", "F2505/40", "cube", (34.5, 26.67, 2.2), 506.33, 2, 100, False, "blue",
                    compress_ratio=0.95, quantity=20, squeeze=squeeze)
    _, sem = empacota((48, 36, 21), calca(1.0))
    assert pecas(sem) == 10                       # 1 coluna: 21 / 2,09
    p = Packer()
    com = Bin("cx", (48, 36, 21), 100000)
    com.squeeze_first = True                      # estratégia "comprimida na lateral primeiro"
    com.stack_rotations = [1, 0]                  # larguras lado a lado (comprimento no sentido de 36)
    p.addBin(com)
    p.addItem(calca(0.88))
    p.pack(bigger_first=True, number_of_decimals=1)
    assert pecas(com) == 20                       # 2 colunas lado a lado
    assert all("comprimida na lateral" in i.foldDescription() for i in com.items)
    sem_sobreposicao(com)
    # pelo cartonize a estratégia entra sozinha quando o produto tem compressão lateral
    prod = Produto("F2505", "40", 34.5, 26.67, 2.2, 506.33, 0, 0.95, compressao_lateral=0.88)
    vol, sobra = pack_one(Embalagem("CX", 48, 36, 21, 100000), [(prod, 20)], iteracoes=3)
    assert vol.pecas == 20 and sobra == []


def test_compressao_lateral_so_quando_precisa():
    item = Item("F", "F", "cube", (34.5, 26.67, 2.2), 506.33, 2, 100, False, "blue", compress_ratio=0.95,
                quantity=10, squeeze=0.88)
    _, b = empacota((60, 40, 30), item)
    assert pecas(b) == 10 and not any(i.isSqueezed() for i in b.items)


def test_fardo_com_pecas_deitadas():
    from py3dbp.cartonizer import Embalagem as E
    p40 = Produto("F2505", "40", 34.5, 26.67, 2.2, 506.33, 1, 0.95)
    for forma, eixo in (("manga", "z"), ("retangular", "z")):
        extra = dict(manga_cm=80, raio_canto=6, folga_ponta_cm=5) if forma == "manga" else {}
        fd = E("FD", 30 if forma != "manga" else 0, 40 if forma != "manga" else 0, 150 if forma != "manga" else 0,
               37000, tipo="fardo", forma=forma, pecas_deitadas=True, **extra)
        r = cartonize([(p40, 40)], [fd], iteracoes=3)
        v = r["volumes"][0]
        assert r["totais"]["pecas"] == 40
        # no resultado (fardo pronto/deitado) toda pilha cresce na vertical
        assert {q["eixo"] for q in v["layout"]} == {eixo}, (forma, [q["eixo"] for q in v["layout"]])
