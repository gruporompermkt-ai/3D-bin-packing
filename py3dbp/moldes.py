'''
Modos (moldes) de fardo: a seção do fardo vista de cima vira uma grade de células quadradas
(como "tijolos"), que o empacotador de caixas consegue usar. Uma célula pertence ao fardo quando
o seu centro está dentro do contorno.

  arredondado  retângulo com cantos arredondados de raio r
  molde        polígono qualquer, com pontos normalizados de 0 a 1 (ex.: contorno traçado de uma foto)

Como as paredes do fardo são flexíveis, o contorno é esticado para a base que estiver sendo
testada (comprimento x largura); o raio dos cantos fica em cm.
'''
import math

import numpy as np

CELULA_CM = 1.0


def _centros(comprimento, largura, celula):
    nx = max(1, int(math.ceil(comprimento / celula - 1e-9)))
    ny = max(1, int(math.ceil(largura / celula - 1e-9)))
    xs = (np.arange(nx) + 0.5) * celula
    ys = (np.arange(ny) + 0.5) * celula
    return np.meshgrid(xs, ys, indexing='ij')


def raio_efetivo(comprimento, largura, raio):
    return max(0.0, min(float(raio), comprimento / 2, largura / 2))


def mascara_arredondada(comprimento, largura, raio, celula=CELULA_CM):
    ''' células (i ao longo do comprimento, j da largura) dentro do retângulo arredondado '''
    r = raio_efetivo(comprimento, largura, raio)
    X, Y = _centros(comprimento, largura, celula)
    dentro = (X <= comprimento) & (Y <= largura)
    if r > 0:
        # distância ao retângulo "encolhido" de r: fora dos cantos ela é 0
        dx = np.maximum(np.maximum(r - X, X - (comprimento - r)), 0)
        dy = np.maximum(np.maximum(r - Y, Y - (largura - r)), 0)
        dentro &= dx * dx + dy * dy <= r * r + 1e-9
    return dentro


def mascara_poligono(comprimento, largura, pontos, celula=CELULA_CM):
    ''' células cujo centro está dentro do polígono (pontos de 0 a 1 esticados para a base) '''
    X, Y = _centros(comprimento, largura, celula)
    px = np.array([p[0] for p in pontos], dtype=float) * comprimento
    py = np.array([p[1] for p in pontos], dtype=float) * largura
    dentro = np.zeros(X.shape, dtype=bool)
    # ray casting vetorizado
    j = len(px) - 1
    for i in range(len(px)):
        cruza = ((py[i] > Y) != (py[j] > Y)) & \
                (X < (px[j] - px[i]) * (Y - py[i]) / ((py[j] - py[i]) or 1e-12) + px[i])
        dentro ^= cruza
        j = i
    return dentro


def contorno_arredondado(comprimento, largura, raio, segmentos=8):
    ''' polígono (cm) do retângulo arredondado, para desenhar '''
    r = raio_efetivo(comprimento, largura, raio)
    if r <= 0:
        return [[0, 0], [comprimento, 0], [comprimento, largura], [0, largura]]
    pts = []
    cantos = [(comprimento - r, r, -90), (comprimento - r, largura - r, 0), (r, largura - r, 90), (r, r, 180)]
    for cx, cy, a0 in cantos:
        for k in range(segmentos + 1):
            a = math.radians(a0 + 90 * k / segmentos)
            pts.append([round(cx + r * math.cos(a), 2), round(cy + r * math.sin(a), 2)])
    return pts


def contorno_poligono(comprimento, largura, pontos):
    return [[round(p[0] * comprimento, 2), round(p[1] * largura, 2)] for p in pontos]


def area_poligono(pts):
    a = 0.0
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
        a += x0 * y1 - x1 * y0
    return abs(a) / 2


def validar_molde(pontos):
    ''' pontos normalizados: >= 3, entre 0 e 1, área > 0 '''
    if not pontos or len(pontos) < 3:
        raise ValueError('o molde precisa de pelo menos 3 pontos')
    for p in pontos:
        if len(p) != 2 or not all(0 <= float(v) <= 1 for v in p):
            raise ValueError('cada ponto do molde é [x, y] com valores de 0 a 1')
    if area_poligono([[float(x), float(y)] for x, y in pontos]) <= 0.01:
        raise ValueError('o molde não tem área')
