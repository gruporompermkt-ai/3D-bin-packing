'''
Leitura do histórico do Sisplan (calibração da cubagem e modelo de frete).

No Sisplan a caixa (CAIXA_001) não tem colunas de medida: as medidas e o peso vêm escritos na
descrição, em formatos como "CAIXA 60X40X40 1,2KG", "CX 60 x 40 x 40cm - 850g" ou "FARDO".
'''
import re

_NUM = r'(\d+(?:[.,]\d+)?)'
_MEDIDAS = re.compile(_NUM + r'\s*(?:cm)?\s*[xX×*]\s*' + _NUM + r'\s*(?:cm)?\s*[xX×*]\s*' + _NUM + r'\s*(mm|cm|m)?\b', re.I)
_PESO = re.compile(_NUM + r'\s*(kg|g|gr|grs)\b', re.I)
_PARA_CM = {'mm': 0.1, 'cm': 1.0, 'm': 100.0}


def _f(txt):
    return float(txt.replace(',', '.'))


def ler_desc_caixa(descricao):
    '''
    Extrai medidas (cm) e peso (g) da descrição da caixa.
    Retorna {comprimento, largura, altura, peso_g}; o que não estiver escrito vem None.
    Medidas sem unidade são tratadas como cm; ordenadas da maior para a menor.
    '''
    out = dict(comprimento=None, largura=None, altura=None, peso_g=None)
    if not descricao:
        return out
    texto = str(descricao)
    m = _MEDIDAS.search(texto)
    if m:
        fator = _PARA_CM[(m.group(4) or 'cm').lower()]
        c, l, a = sorted((_f(m.group(i)) * fator for i in (1, 2, 3)), reverse=True)
        out.update(comprimento=round(c, 1), largura=round(l, 1), altura=round(a, 1))
        texto = texto[:m.start()] + ' ' + texto[m.end():]
    p = _PESO.search(texto)
    if p:
        valor = _f(p.group(1))
        out['peso_g'] = round(valor * 1000 if p.group(2).lower() == 'kg' else valor, 1)
    return out
