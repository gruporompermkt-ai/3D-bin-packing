"""API de cubagem: cadastro de produtos/embalagens e cálculo de volumes de um pedido.

Unidades: centímetros e gramas. Compressão de 0 a 1 (1 = incomprimível), aplicada só na espessura.
"""
import os
import re
from contextlib import asynccontextmanager
from typing import List, Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from py3dbp.cartonizer import ITERACOES_PADRAO, Embalagem, Produto, cartonize

from . import db

FATOR_CUBAGEM = float(os.environ.get("FATOR_CUBAGEM", "300"))
STATIC = os.path.join(os.path.dirname(__file__), "static")

@asynccontextmanager
async def _lifespan(_app):
    db.iniciar()
    yield


app = FastAPI(title="Cubagem", version="1.0", lifespan=_lifespan)


# ---------------------------------------------------------------- modelos
class ProdutoIn(BaseModel):
    descricao: str = ""
    comprimento: float = Field(gt=0, description="cm")
    largura: float = Field(gt=0, description="cm")
    espessura: float = Field(gt=0, description="cm")
    peso_g: float = Field(ge=0)
    dobras: int = Field(0, ge=0, le=4)
    compressao: float = Field(1.0, gt=0, le=1)
    empilhavel: bool = True
    orientacao_livre: bool = True


class EmbalagemIn(BaseModel):
    descricao: str = ""
    tipo: Literal["caixa", "fardo"] = "caixa"
    forma: Literal["retangular", "cilindrico"] = "retangular"
    comprimento: float = Field(gt=0, description="cm, interno")
    largura: Optional[float] = Field(None, gt=0, description="cm; ignorada no fardo cilíndrico")
    altura: float = Field(gt=0)
    peso_max_g: float = Field(gt=0)
    tara_g: float = Field(0, ge=0)
    custo: Optional[float] = Field(None, ge=0)
    ativo: bool = True


class ImportarIn(BaseModel):
    codigo: str = Field(min_length=1)
    texto: str = Field(min_length=1, description="colado do Excel: tamanho, comprimento, largura, espessura, peso, dobras, compressão")


class ItemPedido(BaseModel):
    codigo: str
    tamanho: str
    quantidade: int = Field(gt=0, le=100000)


class PedidoIn(BaseModel):
    pedido: str = ""
    itens: List[ItemPedido] = Field(min_length=1)
    fator_cubagem: Optional[float] = Field(None, gt=0)
    embalagens: Optional[List[str]] = None
    iteracoes: int = Field(ITERACOES_PADRAO, ge=1, le=40)


# ---------------------------------------------------------------- produtos
def _norm(codigo):
    return codigo.strip().upper()


@app.get("/api/produtos")
def listar_produtos(codigo: Optional[str] = None):
    with db.conectar() as con:
        if codigo:
            rows = con.execute("SELECT * FROM produtos WHERE codigo = ? ORDER BY codigo, tamanho", (_norm(codigo),))
        else:
            rows = con.execute("SELECT * FROM produtos ORDER BY codigo, tamanho")
        return [dict(r) for r in rows]


@app.put("/api/produtos/{codigo}/{tamanho}")
def salvar_produto(codigo: str, tamanho: str, p: ProdutoIn):
    with db.conectar() as con:
        con.execute(
            """INSERT INTO produtos (codigo, tamanho, descricao, comprimento, largura, espessura, peso_g, dobras, compressao,
                                   empilhavel, orientacao_livre)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(codigo, tamanho) DO UPDATE SET descricao=excluded.descricao, comprimento=excluded.comprimento,
                 largura=excluded.largura, espessura=excluded.espessura, peso_g=excluded.peso_g, dobras=excluded.dobras,
                 compressao=excluded.compressao, empilhavel=excluded.empilhavel, orientacao_livre=excluded.orientacao_livre,
                 atualizado_em=datetime('now','localtime')""",
            (_norm(codigo), tamanho.strip().upper(), p.descricao, p.comprimento, p.largura, p.espessura, p.peso_g,
             p.dobras, p.compressao, int(p.empilhavel), int(p.orientacao_livre)))
    return {"ok": True}


@app.delete("/api/produtos/{codigo}/{tamanho}")
def apagar_produto(codigo: str, tamanho: str):
    with db.conectar() as con:
        n = con.execute("DELETE FROM produtos WHERE codigo=? AND tamanho=?", (_norm(codigo), tamanho.strip().upper())).rowcount
    if not n:
        raise HTTPException(404, "produto não encontrado")
    return {"ok": True}


def _num(s):
    s = s.strip().replace(" ", "")
    # pt-BR: "1.500" (sem vírgula, grupos de 3) é milhar, não 1,5
    if "," in s or re.fullmatch(r"-?\d{1,3}(\.\d{3})+", s):
        s = s.replace(".", "").replace(",", ".")
    return float(s)


def parse_planilha(texto):
    """Linhas coladas do Excel (TAB, ; ou espaços). Linhas cujo 2º campo não é número (cabeçalho) são ignoradas."""
    linhas, erros = [], []
    for n, linha in enumerate(texto.splitlines(), 1):
        if not linha.strip():
            continue
        campos = [c for c in re.split(r"\t|;", linha)] if ("\t" in linha or ";" in linha) else linha.split()
        campos = [c.strip() for c in campos]
        try:
            _num(campos[1])
        except (IndexError, ValueError):
            continue  # cabeçalho
        try:
            tam, comp, larg, esp, peso = campos[0], *(_num(c) for c in campos[1:5])
            dobras = int(round(_num(campos[5]))) if len(campos) > 5 and campos[5] else 0
            comp_ratio = _num(campos[6]) if len(campos) > 6 and campos[6] else 1.0
            linhas.append(dict(tamanho=tam.upper(), produto=ProdutoIn(
                comprimento=comp, largura=larg, espessura=esp, peso_g=peso, dobras=dobras, compressao=comp_ratio)))
        except Exception as e:  # noqa: BLE001 - devolve o erro da linha para o usuário
            erros.append({"linha": n, "texto": linha, "erro": str(e).splitlines()[0]})
    return linhas, erros


@app.post("/api/produtos/importar")
def importar(dados: ImportarIn):
    linhas, erros = parse_planilha(dados.texto)
    if erros:
        raise HTTPException(422, {"mensagem": "linhas inválidas, nada foi gravado", "erros": erros})
    if not linhas:
        raise HTTPException(422, {"mensagem": "nenhuma linha com números encontrada", "erros": []})
    for l in linhas:
        salvar_produto(dados.codigo, l["tamanho"], l["produto"])
    return {"ok": True, "gravados": len(linhas), "tamanhos": [l["tamanho"] for l in linhas]}


# ---------------------------------------------------------------- embalagens
@app.get("/api/embalagens")
def listar_embalagens():
    with db.conectar() as con:
        return [dict(r) for r in con.execute("SELECT * FROM embalagens ORDER BY comprimento*largura*altura")]


@app.put("/api/embalagens/{codigo}")
def salvar_embalagem(codigo: str, e: EmbalagemIn):
    if e.tara_g >= e.peso_max_g:
        raise HTTPException(422, "a tara deve ser menor que o peso máximo")
    forma = e.forma if e.tipo == "fardo" else "retangular"
    largura = e.comprimento if forma == "cilindrico" else e.largura   # cilindro: comprimento = diâmetro
    if largura is None:
        raise HTTPException(422, "informe a largura")
    with db.conectar() as con:
        con.execute(
            """INSERT INTO embalagens (codigo, descricao, tipo, forma, comprimento, largura, altura, peso_max_g, tara_g, custo, ativo)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(codigo) DO UPDATE SET descricao=excluded.descricao, tipo=excluded.tipo, forma=excluded.forma,
                 comprimento=excluded.comprimento, largura=excluded.largura, altura=excluded.altura,
                 peso_max_g=excluded.peso_max_g, tara_g=excluded.tara_g, custo=excluded.custo, ativo=excluded.ativo,
                 atualizado_em=datetime('now','localtime')""",
            (_norm(codigo), e.descricao, e.tipo, forma, e.comprimento, largura, e.altura, e.peso_max_g, e.tara_g, e.custo,
             int(e.ativo)))
    return {"ok": True}


@app.delete("/api/embalagens/{codigo}")
def apagar_embalagem(codigo: str):
    with db.conectar() as con:
        n = con.execute("DELETE FROM embalagens WHERE codigo=?", (_norm(codigo),)).rowcount
    if not n:
        raise HTTPException(404, "embalagem não encontrada")
    return {"ok": True}


# ---------------------------------------------------------------- cubagem
@app.post("/api/cubagem")
def calcular(pedido: PedidoIn):
    with db.conectar() as con:
        linhas, faltando = [], []
        for it in pedido.itens:
            r = con.execute("SELECT * FROM produtos WHERE codigo=? AND tamanho=?",
                            (_norm(it.codigo), it.tamanho.strip().upper())).fetchone()
            if r is None:
                faltando.append(f"{_norm(it.codigo)}/{it.tamanho.strip().upper()}")
                continue
            linhas.append((Produto(r["codigo"], r["tamanho"], r["comprimento"], r["largura"], r["espessura"], r["peso_g"],
                                   r["dobras"], r["compressao"], bool(r["empilhavel"]), bool(r["orientacao_livre"])),
                           it.quantidade))
        if faltando:
            raise HTTPException(422, {"mensagem": "produtos sem cadastro", "produtos": faltando})
        rows = con.execute("SELECT * FROM embalagens WHERE ativo=1").fetchall()
    catalogo = [Embalagem(r["codigo"], r["comprimento"], r["largura"], r["altura"], r["peso_max_g"], r["tara_g"],
                          r["custo"], r["tipo"], r["forma"]) for r in rows]
    if pedido.embalagens:
        quero = {_norm(c) for c in pedido.embalagens}
        catalogo = [e for e in catalogo if e.codigo in quero]
    if not catalogo:
        raise HTTPException(422, "nenhuma embalagem ativa cadastrada")
    resultado = cartonize(linhas, catalogo, pedido.fator_cubagem or FATOR_CUBAGEM, pedido.iteracoes)
    resultado["pedido"] = pedido.pedido
    return resultado


@app.get("/api/health")
def health():
    with db.conectar() as con:
        con.execute("SELECT 1")
    return {"ok": True}


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))


app.mount("/static", StaticFiles(directory=STATIC), name="static")
