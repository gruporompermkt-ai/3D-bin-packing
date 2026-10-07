"""API de cubagem: cadastro de produtos/embalagens e cálculo de volumes de um pedido.

Unidades: centímetros e gramas. Compressão de 0 a 1 (1 = incomprimível), aplicada só na espessura.
"""
import json
import os
import re
from contextlib import asynccontextmanager
from typing import List, Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from py3dbp import moldes
from py3dbp.cartonizer import ITERACOES_PADRAO, Embalagem, Produto, cartonize

from . import db, frete

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
    curvavel: bool = True
    compressao_lateral: float = Field(1.0, gt=0, le=1, description="1 = não cede; 0,9 = comprimento/largura cedem até 90%")


class EmbalagemIn(BaseModel):
    descricao: str = ""
    tipo: Literal["caixa", "fardo"] = "caixa"
    forma: Literal["flexivel", "retangular", "cilindrico", "arredondado", "molde", "manga"] = "flexivel"
    manga_cm: float = Field(0, ge=0, description="fardo de manga: largura do tubo deitado no rolo (cm)")
    folga_ponta_cm: float = Field(0, ge=0, description="fardo de manga: cm a mais em cada ponta franzida")
    pecas_deitadas: bool = Field(True, description="fardo: camadas sempre na horizontal (como o estoque arruma)")
    raio_canto: float = Field(0, ge=0, description="cm, fardo arredondado")
    molde: Optional[List[List[float]]] = Field(None, description="fardo molde: [[x, y], ...] de 0 a 1")
    comprimento: Optional[float] = Field(None, gt=0, description="cm, interno (dispensado no fardo de manga)")
    largura: Optional[float] = Field(None, gt=0, description="cm; ignorada no fardo cilíndrico e de manga")
    altura: Optional[float] = Field(None, gt=0, description="cm (fardo de manga: comprimento máximo, opcional)")
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
    volumes: Optional[int] = Field(None, ge=1, le=200, description="número de fardos que o cliente quer (fardo de manga)")
    tipo_embalagem: Optional[Literal["caixa", "fardo"]] = Field(None, description="só caixas ou só fardos (vazio = todas)")
    iteracoes: int = Field(ITERACOES_PADRAO, ge=1, le=40)
    # estimativa de frete (opcional): destino, transportadora e valor da mercadoria
    cep: Optional[str] = Field(None, max_length=12)
    uf: Optional[str] = Field(None, min_length=2, max_length=2)
    transportadora: Optional[str] = Field(None, max_length=10, description="código da transportadora no Sisplan")
    valor_mercadoria: Optional[float] = Field(None, ge=0)


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
                                   empilhavel, orientacao_livre, curvavel, compressao_lateral)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(codigo, tamanho) DO UPDATE SET descricao=excluded.descricao, comprimento=excluded.comprimento,
                 largura=excluded.largura, espessura=excluded.espessura, peso_g=excluded.peso_g, dobras=excluded.dobras,
                 compressao=excluded.compressao, empilhavel=excluded.empilhavel, orientacao_livre=excluded.orientacao_livre,
                 curvavel=excluded.curvavel, compressao_lateral=excluded.compressao_lateral,
                 atualizado_em=datetime('now','localtime')""",
            (_norm(codigo), tamanho.strip().upper(), p.descricao, p.comprimento, p.largura, p.espessura, p.peso_g,
             p.dobras, p.compressao, int(p.empilhavel), int(p.orientacao_livre), int(p.curvavel), p.compressao_lateral))
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
            lateral = _num(campos[7]) if len(campos) > 7 and campos[7] else 1.0
            linhas.append(dict(tamanho=tam.upper(), produto=ProdutoIn(
                comprimento=comp, largura=larg, espessura=esp, peso_g=peso, dobras=dobras, compressao=comp_ratio,
                compressao_lateral=lateral)))
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
def _embalagem_dict(r):
    d = dict(r)
    d["molde"] = json.loads(d["molde"]) if d.get("molde") else None
    return d


@app.get("/api/embalagens")
def listar_embalagens():
    with db.conectar() as con:
        return [_embalagem_dict(r) for r in con.execute("SELECT * FROM embalagens ORDER BY comprimento*largura*altura")]


@app.put("/api/embalagens/{codigo}")
def salvar_embalagem(codigo: str, e: EmbalagemIn):
    if e.tara_g >= e.peso_max_g:
        raise HTTPException(422, "a tara deve ser menor que o peso máximo")
    forma = e.forma if e.tipo == "fardo" else "retangular"
    comprimento, altura = e.comprimento, e.altura
    largura = e.largura if e.largura is not None or forma != "cilindrico" else e.comprimento  # cilindro sem largura: diâmetro = comprimento
    if forma == "manga":
        if e.manga_cm <= 0:
            raise HTTPException(422, "informe a largura da manga deitada (cm)")
        if e.raio_canto * 2 >= e.manga_cm:
            raise HTTPException(422, "raio do canto grande demais para essa manga")
        modelo = Embalagem(codigo, 0, 0, altura or 0, e.peso_max_g, e.tara_g, tipo="fardo", forma="manga",
                           raio_canto=e.raio_canto, manga_cm=e.manga_cm, folga_ponta_cm=e.folga_ponta_cm)
        comprimento, largura, altura = modelo.comprimento, modelo.largura, modelo.altura
    if comprimento is None or altura is None:
        raise HTTPException(422, "informe comprimento e altura")
    if largura is None:
        raise HTTPException(422, "informe a largura")
    molde = None
    if forma == "molde":
        try:
            moldes.validar_molde(e.molde)
        except (ValueError, TypeError) as erro:
            raise HTTPException(422, f"molde inválido: {erro}")
        molde = json.dumps(e.molde)
    with db.conectar() as con:
        con.execute(
            """INSERT INTO embalagens (codigo, descricao, tipo, forma, comprimento, largura, altura, peso_max_g, tara_g, custo, ativo,
                                     raio_canto, molde, manga_cm, folga_ponta_cm, pecas_deitadas)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(codigo) DO UPDATE SET descricao=excluded.descricao, tipo=excluded.tipo, forma=excluded.forma,
                 raio_canto=excluded.raio_canto, molde=excluded.molde, manga_cm=excluded.manga_cm,
                 folga_ponta_cm=excluded.folga_ponta_cm, pecas_deitadas=excluded.pecas_deitadas,
                 comprimento=excluded.comprimento, largura=excluded.largura, altura=excluded.altura,
                 peso_max_g=excluded.peso_max_g, tara_g=excluded.tara_g, custo=excluded.custo, ativo=excluded.ativo,
                 atualizado_em=datetime('now','localtime')""",
            (_norm(codigo), e.descricao, e.tipo, forma, comprimento, largura, altura, e.peso_max_g, e.tara_g, e.custo,
             int(e.ativo), e.raio_canto if forma in ("arredondado", "manga") else 0, molde,
             e.manga_cm if forma == "manga" else 0, e.folga_ponta_cm if forma == "manga" else 0, int(e.pecas_deitadas)))
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
                                   r["dobras"], r["compressao"], bool(r["empilhavel"]), bool(r["orientacao_livre"]),
                                   bool(r["curvavel"]), r["compressao_lateral"] or 1),
                           it.quantidade))
        if faltando:
            raise HTTPException(422, {"mensagem": "produtos sem cadastro", "produtos": faltando})
        rows = con.execute("SELECT * FROM embalagens WHERE ativo=1").fetchall()
    catalogo = [Embalagem(r["codigo"], r["comprimento"], r["largura"], r["altura"], r["peso_max_g"], r["tara_g"],
                          r["custo"], r["tipo"], r["forma"], r["raio_canto"] or 0,
                          json.loads(r["molde"]) if r["molde"] else None, r["manga_cm"] or 0,
                          r["folga_ponta_cm"] or 0, bool(r["pecas_deitadas"])) for r in rows]
    if pedido.tipo_embalagem:
        catalogo = [e for e in catalogo if e.tipo == pedido.tipo_embalagem]
    if pedido.embalagens:
        quero = {_norm(c) for c in pedido.embalagens}
        catalogo = [e for e in catalogo if e.codigo in quero]
    if not catalogo:
        raise HTTPException(422, "nenhuma embalagem ativa com essa escolha" if (pedido.tipo_embalagem or pedido.embalagens)
                            else "nenhuma embalagem ativa cadastrada")
    resultado = cartonize(linhas, catalogo, pedido.fator_cubagem or FATOR_CUBAGEM, pedido.iteracoes, pedido.volumes)
    resultado["pedido"] = pedido.pedido
    if pedido.cep or pedido.uf:
        resultado["frete"] = frete.estimar(resultado, pedido.cep, pedido.uf, pedido.transportadora,
                                           pedido.valor_mercadoria)
    return resultado


@app.get("/api/frete")
def frete_info():
    ''' modelo de frete: se está instalado, precisão no teste e transportadoras conhecidas '''
    return frete.info()


@app.get("/api/health")
def health():
    with db.conectar() as con:
        con.execute("SELECT 1")
    return {"ok": True}


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))


app.mount("/static", StaticFiles(directory=STATIC), name="static")
