import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import app, parse_planilha

PLANILHA_F2505 = """f2505\tcomprimento\tlargura\tespessura\tpeso (g)\tquantidades de dobras possiveis\tindice de compressao
38\t34,33\t24,67\t2,20\t508,33\t1,00\t0,95
40\t34,50\t26,67\t2,20\t506,33\t1,00\t0,95
54\t35,00\t27,17\t2,66\t611,00\t1,00\t0,95
"""


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "t.db"))
    with TestClient(app) as c:
        yield c


def test_parse_planilha_colada_do_excel():
    linhas, erros = parse_planilha(PLANILHA_F2505)
    assert erros == []
    assert [l["tamanho"] for l in linhas] == ["38", "40", "54"]
    p = linhas[0]["produto"]
    assert (p.comprimento, p.largura, p.espessura, p.peso_g, p.dobras, p.compressao) == (34.33, 24.67, 2.2, 508.33, 1, 0.95)


def test_parse_milhar_sem_virgula():
    linhas, _ = parse_planilha("G\t40\t30\t20\t1.500\t0\t1")
    assert linhas[0]["produto"].peso_g == 1500
    linhas, _ = parse_planilha("G\t40\t30\t20\t1.234,5\t0\t1")
    assert linhas[0]["produto"].peso_g == 1234.5
    linhas, _ = parse_planilha("G\t34.33\t30\t2.2\t500\t0\t0.95")
    assert (linhas[0]["produto"].comprimento, linhas[0]["produto"].compressao) == (34.33, 0.95)


def test_importar_e_listar(client):
    r = client.post("/api/produtos/importar", json={"codigo": "f2505", "texto": PLANILHA_F2505})
    assert r.status_code == 200, r.text
    assert r.json()["gravados"] == 3
    prods = client.get("/api/produtos", params={"codigo": "F2505"}).json()
    assert [(p["codigo"], p["tamanho"]) for p in prods] == [("F2505", "38"), ("F2505", "40"), ("F2505", "54")]


def test_importar_rejeita_compressao_invalida(client):
    r = client.post("/api/produtos/importar", json={"codigo": "X", "texto": "38\t30\t20\t2\t500\t1\t1,5"})
    assert r.status_code == 422
    assert client.get("/api/produtos").json() == []


def test_cubagem_ponta_a_ponta(client):
    client.post("/api/produtos/importar", json={"codigo": "F2505", "texto": PLANILHA_F2505})
    r = client.put("/api/embalagens/cx-teste", json={"comprimento": 70, "largura": 50, "altura": 21,
                                                      "peso_max_g": 30000, "tara_g": 400})
    assert r.status_code == 200, r.text
    r = client.post("/api/cubagem", json={"pedido": "123", "itens": [{"codigo": "F2505", "tamanho": "38", "quantidade": 100}]})
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["ok"] and res["pedido"] == "123"
    assert res["totais"]["pecas"] == 100 and res["totais"]["volumes"] == 3


def test_cubagem_produto_sem_cadastro(client):
    client.put("/api/embalagens/CX", json={"comprimento": 70, "largura": 50, "altura": 21, "peso_max_g": 30000})
    r = client.post("/api/cubagem", json={"itens": [{"codigo": "NAOEXISTE", "tamanho": "M", "quantidade": 1}]})
    assert r.status_code == 422
    assert r.json()["detail"]["produtos"] == ["NAOEXISTE/M"]


def test_tela_inicial(client):
    r = client.get("/")
    assert r.status_code == 200 and "Cubagem" in r.text
