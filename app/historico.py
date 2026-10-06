'''
Leitura do histórico do Sisplan (calibração da cubagem e modelo de frete).

O Sisplan não guarda as medidas do volume em colunas (CAIXA_001 está vazia, PEDIDO3.ALTURA/LARGURA/
COMPRIMENTO ficam zerados): a expedição digita no PEDIDO3.OBS do volume, em formatos como
"FD: 52X42X93 CM", "CX:08X28X19 CM", "FD: 105-62-34", "CX : 35 X 35 X 13 CM".
Volumes que foram dentro de outro ("DENTRO DO OUTRO PEDIDO", "JUNTO COM O OUTRO PEDIDO") vêm marcados.
'''
import re

_NUM = r'(\d+(?:[.,]\d+)?)'
_SEP = r'\s*[xX×*-]\s*'
_MEDIDAS = re.compile(_NUM + _SEP + _NUM + _SEP + _NUM + r'\s*(mm|cm|m)?(?![a-z])', re.I)
_TIPO = re.compile(r'^\s*(FD|FARDO|CX|CAIXA)\b|^\s*(FD|CX)(?=\s*[:;\d])|\b(FARDO|CAIXA)\b', re.I)
_JUNTO = re.compile(r'\b(DENTRO|JUNTO)\b', re.I)
_PARA_CM = {'mm': 0.1, 'cm': 1.0, 'm': 100.0}


def _f(txt):
    return float(txt.replace(',', '.'))


def ler_obs_volume(obs):
    '''
    Lê o PEDIDO3.OBS de um volume.
    Retorna {tipo: 'fardo'|'caixa'|None, comprimento, largura, altura (cm, maior para menor; None se não
    digitado), junto: True quando o volume foi dentro de outro}.
    '''
    out = dict(tipo=None, comprimento=None, largura=None, altura=None, junto=False)
    if not obs or not str(obs).strip():
        return out
    texto = str(obs)
    t = _TIPO.search(texto)
    if t:
        sigla = next(g for g in t.groups() if g).upper()
        out['tipo'] = 'fardo' if sigla.startswith('F') else 'caixa'
    out['junto'] = bool(_JUNTO.search(texto))
    m = _MEDIDAS.search(texto)
    if m:
        fator = _PARA_CM[(m.group(4) or 'cm').lower()]
        c, l, a = sorted((_f(m.group(i)) * fator for i in (1, 2, 3)), reverse=True)
        out.update(comprimento=round(c, 1), largura=round(l, 1), altura=round(a, 1))
    return out
