"""Conta sobreposições e itens fora da caixa num JSON gerado por capture.py."""
import itertools, json, sys

BINS = {"example0": (589.8, 243.8, 259.1), "example1": (5.6875, 10.75, 15.0), "example2": (30, 10, 15),
        "example3": (6, 1, 5), "example4": (589.8, 243.8, 259.1), "example5": (5, 4, 3), "example6": (5, 4, 7),
        "example7-Bin1": (5, 5, 5), "example7-Bin2": (3, 3, 5)}

def over(a, b):
    return all(min(a["position"][k] + a["dimension"][k], b["position"][k] + b["dimension"][k]) -
               max(a["position"][k], b["position"][k]) > 1e-9 for k in range(3))

data = json.load(open(sys.argv[1]))
for name, r in data.items():
    for b in r["bins"]:
        size = BINS.get(b["partno"])
        out = [i["partno"] for i in b["items"] if size and any(i["position"][k] + i["dimension"][k] > size[k] + 1e-6 for k in range(3))]
        ov = [(x["partno"], y["partno"]) for x, y in itertools.combinations(b["items"], 2) if over(x, y)]
        print(f'{b["partno"]:14} itens={len(b["items"]):3} sobreposicoes={len(ov):3} fora_da_caixa={len(out)}', ov[:2])
