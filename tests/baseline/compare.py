"""Compara dois JSONs do capture.py: itens, volume ocupado e sobreposições por caixa."""
import itertools, json, sys

def stats(path):
    out = {}
    for r in json.load(open(path)).values():
        for b in r["bins"]:
            vol = sum(i["dimension"][0] * i["dimension"][1] * i["dimension"][2] for i in b["items"])
            ov = sum(1 for x, y in itertools.combinations(b["items"], 2)
                     if all(min(x["position"][q] + x["dimension"][q], y["position"][q] + y["dimension"][q])
                            - max(x["position"][q], y["position"][q]) > 1e-9 for q in range(3)))
            out[b["partno"]] = (len(b["items"]), round(vol, 1), ov)
    return out

a, b = stats(sys.argv[1]), stats(sys.argv[2])
for k in a:
    print(f"{k:14} itens {a[k][0]:>3} -> {b[k][0]:<3} volume {a[k][1]:>11} -> {b[k][1]:<11} sobreposicoes {a[k][2]} -> {b[k][2]}")
