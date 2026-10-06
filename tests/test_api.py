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


def test_migracao_banco_antigo_preserva_dados(tmp_path, monkeypatch):
    import sqlite3
    caminho = tmp_path / "antigo.db"
    con = sqlite3.connect(caminho)   # esquema da 1ª versão (sem orientacao_livre / forma)
    con.executescript("""
        CREATE TABLE produtos (codigo TEXT NOT NULL, tamanho TEXT NOT NULL, descricao TEXT NOT NULL DEFAULT '',
          comprimento REAL NOT NULL, largura REAL NOT NULL, espessura REAL NOT NULL, peso_g REAL NOT NULL,
          dobras INTEGER NOT NULL DEFAULT 0, compressao REAL NOT NULL DEFAULT 1, empilhavel INTEGER NOT NULL DEFAULT 1,
          atualizado_em TEXT NOT NULL DEFAULT '', PRIMARY KEY (codigo, tamanho));
        CREATE TABLE embalagens (codigo TEXT PRIMARY KEY, descricao TEXT NOT NULL DEFAULT '', tipo TEXT NOT NULL DEFAULT 'caixa',
          comprimento REAL NOT NULL, largura REAL NOT NULL, altura REAL NOT NULL, peso_max_g REAL NOT NULL,
          tara_g REAL NOT NULL DEFAULT 0, custo REAL, ativo INTEGER NOT NULL DEFAULT 1, atualizado_em TEXT NOT NULL DEFAULT '');
        INSERT INTO produtos (codigo, tamanho, comprimento, largura, espessura, peso_g, dobras, compressao)
          VALUES ('F2505', '38', 34.33, 24.67, 2.2, 508.33, 1, 0.95);
        INSERT INTO embalagens (codigo, tipo, comprimento, largura, altura, peso_max_g) VALUES ('002', 'fardo', 30, 40, 150, 35000);
    """)
    con.commit()
    con.close()
    monkeypatch.setattr(db, "DB_PATH", str(caminho))
    with TestClient(app) as c:
        p = c.get("/api/produtos").json()
        e = c.get("/api/embalagens").json()
        assert p[0]["tamanho"] == "38" and p[0]["orientacao_livre"] == 1
        assert e[0]["codigo"] == "002" and e[0]["forma"] == "retangular"
        r = c.post("/api/cubagem", json={"itens": [{"codigo": "F2505", "tamanho": "38", "quantidade": 10}], "iteracoes": 2})
        assert r.status_code == 200 and r.json()["totais"]["pecas"] == 10


def test_embalagem_cilindrica_usa_diametro(client):
    r = client.put("/api/embalagens/CIL", json={"tipo": "fardo", "forma": "cilindrico", "comprimento": 60,
                                                 "altura": 100, "peso_max_g": 30000})
    assert r.status_code == 200, r.text
    e = client.get("/api/embalagens").json()[0]
    assert (e["forma"], e["comprimento"], e["largura"]) == ("cilindrico", 60, 60)


def test_caixa_sem_largura_e_rejeitada(client):
    r = client.put("/api/embalagens/CX", json={"comprimento": 60, "altura": 40, "peso_max_g": 30000})
    assert r.status_code == 422


def test_embalagem_molde_e_arredondada(client):
    octo = [[.3, 0], [.7, 0], [1, .3], [1, .7], [.7, 1], [.3, 1], [0, .7], [0, .3]]
    r = client.put("/api/embalagens/OCT", json={"tipo": "fardo", "forma": "molde", "comprimento": 40, "largura": 40,
                                                 "altura": 80, "peso_max_g": 30000, "molde": octo})
    assert r.status_code == 200, r.text
    r = client.put("/api/embalagens/ARR", json={"tipo": "fardo", "forma": "arredondado", "raio_canto": 8,
                                                 "comprimento": 40, "largura": 30, "altura": 80, "peso_max_g": 30000})
    assert r.status_code == 200, r.text
    emb = {e["codigo"]: e for e in client.get("/api/embalagens").json()}
    assert emb["OCT"]["molde"] == octo and emb["ARR"]["raio_canto"] == 8
    r = client.put("/api/embalagens/RUIM", json={"tipo": "fardo", "forma": "molde", "comprimento": 40, "largura": 40,
                                                  "altura": 80, "peso_max_g": 30000, "molde": [[0, 0], [1, 1]]})
    assert r.status_code == 422
    client.put("/api/produtos/F1078/P", json={"comprimento": 16, "largura": 16, "espessura": 7, "peso_g": 260,
                                               "compressao": 0.6})
    r = client.post("/api/cubagem", json={"itens": [{"codigo": "F1078", "tamanho": "P", "quantidade": 12}],
                                          "embalagens": ["OCT"], "iteracoes": 2})
    assert r.status_code == 200, r.text
    v = r.json()["volumes"][0]
    assert v["forma"] == "molde" and v["contorno_cm"]


def test_embalagem_manga_e_numero_de_fardos(client):
    r = client.put("/api/embalagens/MANGA-80", json={"tipo": "fardo", "forma": "manga", "manga_cm": 80, "raio_canto": 6,
                                                      "folga_ponta_cm": 5, "peso_max_g": 37000})
    assert r.status_code == 200, r.text
    e = client.get("/api/embalagens").json()[0]
    assert (e["forma"], e["manga_cm"], e["folga_ponta_cm"]) == ("manga", 80, 5) and e["altura"] == 300
    assert client.put("/api/embalagens/X", json={"tipo": "fardo", "forma": "manga", "peso_max_g": 37000}).status_code == 422
    client.put("/api/produtos/F2505/38", json={"comprimento": 34.33, "largura": 24.67, "espessura": 2.2, "peso_g": 508.33,
                                               "dobras": 1, "compressao": 0.95})
    r = client.post("/api/cubagem", json={"itens": [{"codigo": "F2505", "tamanho": "38", "quantidade": 40}],
                                          "volumes": 2, "iteracoes": 2})
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["totais"]["volumes"] == 2 and [sum(i["qtd"] for i in v["itens"]) for v in res["volumes"]] == [20, 20]


def test_escolher_caixa_ou_fardo(client):
    client.put("/api/produtos/F2505/38", json={"comprimento": 34.33, "largura": 24.67, "espessura": 2.2, "peso_g": 508.33,
                                               "dobras": 1, "compressao": 0.95})
    client.put("/api/embalagens/CX", json={"comprimento": 60, "largura": 40, "altura": 40, "peso_max_g": 30000})
    client.put("/api/embalagens/MANGA", json={"tipo": "fardo", "forma": "manga", "manga_cm": 80, "raio_canto": 6,
                                               "folga_ponta_cm": 5, "peso_max_g": 37000})
    itens = [{"codigo": "F2505", "tamanho": "38", "quantidade": 20}]
    for tipo, esperado in (("caixa", "CX"), ("fardo", "MANGA")):
        r = client.post("/api/cubagem", json={"itens": itens, "tipo_embalagem": tipo, "iteracoes": 2})
        assert r.status_code == 200, r.text
        assert {v["embalagem"] for v in r.json()["volumes"]} == {esperado}
    r = client.post("/api/cubagem", json={"itens": itens, "tipo_embalagem": "caixa", "embalagens": ["MANGA"]})
    assert r.status_code == 422 and "escolha" in r.json()["detail"]


def test_compressao_lateral_e_pecas_deitadas(client):
    r = client.post("/api/produtos/importar", json={"codigo": "F2505", "texto": "40\t34,5\t26,67\t2,2\t506,33\t1\t0,95\t0,9"})
    assert r.status_code == 200, r.text
    assert client.get("/api/produtos").json()[0]["compressao_lateral"] == 0.9
    r = client.put("/api/embalagens/MANGA", json={"tipo": "fardo", "forma": "manga", "manga_cm": 80, "raio_canto": 6,
                                                   "folga_ponta_cm": 5, "peso_max_g": 37000})
    assert r.status_code == 200 and client.get("/api/embalagens").json()[0]["pecas_deitadas"] == 1
    r = client.post("/api/cubagem", json={"itens": [{"codigo": "F2505", "tamanho": "40", "quantidade": 20}], "iteracoes": 3})
    assert r.status_code == 200, r.text
    v = r.json()["volumes"][0]
    assert {q["eixo"] for q in v["layout"]} == {"z"}                       # camadas na horizontal
    assert not any("em pé" in i["forma"] for i in v["itens"])
