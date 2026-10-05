"""Os example*.py rodam sem erro, sem sobreposição e ocupando pelo menos o volume do código original.

A contagem de itens pode mudar (a correção das rotações troca as escolhas da heurística gulosa),
por isso a comparação é por volume ocupado.
"""
import itertools
import json
import os

import pytest

from baseline import capture

HERE = os.path.dirname(__file__)


@pytest.fixture(scope="module")
def resultados(tmp_path_factory):
    out = tmp_path_factory.mktemp("cap") / "atual.json"
    capture.main(str(out))
    with open(out, encoding="utf-8") as f:
        atual = json.load(f)
    with open(os.path.join(HERE, "baseline", "original.json"), encoding="utf-8") as f:
        original = json.load(f)
    return original, atual


def _bins(result):
    return {b["partno"]: b for r in result.values() for b in r["bins"]}


def _volume(b):
    return sum(i["dimension"][0] * i["dimension"][1] * i["dimension"][2] for i in b["items"])


def test_exemplos_rodam(resultados):
    _, atual = resultados
    assert {k: v["error"] for k, v in atual.items() if v["error"]} == {}


def test_sem_sobreposicao(resultados):
    _, atual = resultados
    for nome, b in _bins(atual).items():
        for x, y in itertools.combinations(b["items"], 2):
            sobrepoe = all(
                min(x["position"][q] + x["dimension"][q], y["position"][q] + y["dimension"][q])
                - max(x["position"][q], y["position"][q]) > 1e-9 for q in range(3))
            assert not sobrepoe, f"{nome}: {x['partno']} x {y['partno']}"


def test_volume_nao_piora(resultados):
    original, atual = resultados
    orig, novo = _bins(original), _bins(atual)
    for nome in orig:
        assert _volume(novo[nome]) >= _volume(orig[nome]) - 1e-6, nome
