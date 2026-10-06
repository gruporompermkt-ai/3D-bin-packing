"""Cadastro de produtos e embalagens em SQLite."""
import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "..", "data", "cubagem.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS produtos (
    codigo       TEXT NOT NULL,
    tamanho      TEXT NOT NULL,
    descricao    TEXT NOT NULL DEFAULT '',
    comprimento  REAL NOT NULL CHECK (comprimento > 0),
    largura      REAL NOT NULL CHECK (largura > 0),
    espessura    REAL NOT NULL CHECK (espessura > 0),
    peso_g       REAL NOT NULL CHECK (peso_g >= 0),
    dobras       INTEGER NOT NULL DEFAULT 0 CHECK (dobras BETWEEN 0 AND 4),
    compressao   REAL NOT NULL DEFAULT 1 CHECK (compressao > 0 AND compressao <= 1),
    empilhavel   INTEGER NOT NULL DEFAULT 1,
    atualizado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    PRIMARY KEY (codigo, tamanho)
);
CREATE TABLE IF NOT EXISTS embalagens (
    codigo       TEXT PRIMARY KEY,
    descricao    TEXT NOT NULL DEFAULT '',
    tipo         TEXT NOT NULL DEFAULT 'caixa',
    comprimento  REAL NOT NULL CHECK (comprimento > 0),
    largura      REAL NOT NULL CHECK (largura > 0),
    altura       REAL NOT NULL CHECK (altura > 0),
    peso_max_g   REAL NOT NULL CHECK (peso_max_g > 0),
    tara_g       REAL NOT NULL DEFAULT 0 CHECK (tara_g >= 0),
    custo        REAL,
    ativo        INTEGER NOT NULL DEFAULT 1,
    atualizado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
"""


@contextmanager
def conectar():
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    try:
        yield con
        con.commit()
    finally:
        con.close()


# colunas acrescentadas depois da 1ª versão: (tabela, coluna, definição)
MIGRACOES = [
    ("produtos", "orientacao_livre", "INTEGER NOT NULL DEFAULT 1"),
    ("embalagens", "forma", "TEXT NOT NULL DEFAULT 'retangular'"),
    ("produtos", "curvavel", "INTEGER NOT NULL DEFAULT 1"),
    ("embalagens", "raio_canto", "REAL NOT NULL DEFAULT 0"),
    ("embalagens", "molde", "TEXT"),
    ("embalagens", "manga_cm", "REAL NOT NULL DEFAULT 0"),
    ("embalagens", "folga_ponta_cm", "REAL NOT NULL DEFAULT 0"),
]


def iniciar():
    with conectar() as con:
        con.executescript(SCHEMA)
        for tabela, coluna, definicao in MIGRACOES:
            existentes = {r["name"] for r in con.execute(f"PRAGMA table_info({tabela})")}
            if coluna not in existentes:
                con.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {definicao}")
