"""Roda os example*.py e grava o resultado de cada um em JSON.

Uso:  python tests/baseline/capture.py saida.json
Gerado uma vez com o código ORIGINAL (tests/baseline/original.json) para
comparar o antes/depois das correções.
"""
import json
import os
import runpy
import sys
import time

os.environ.setdefault("MPLBACKEND", "Agg")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)


def snapshot(packer):
    bins = []
    for b in packer.bins:
        bins.append({
            "partno": b.partno,
            "items": [
                {"partno": i.partno, "position": [float(p) for p in i.position],
                 "rotation_type": i.rotation_type,
                 "dimension": [float(d) for d in i.getDimension()]}
                for i in b.items
            ],
            "unfitted": [i.partno for i in b.unfitted_items],
            "gravity": [float(g) for g in b.gravity],
        })
    return bins


def main(out):
    import matplotlib.pyplot as plt
    plt.show = lambda *a, **k: None
    result = {}
    for n in range(8):
        name = f"example{n}"
        path = os.path.join(ROOT, f"{name}.py")
        t = time.time()
        devnull = open(os.devnull, "w")
        stdout, sys.stdout = sys.stdout, devnull
        try:
            ns = runpy.run_path(path, run_name="__main__")
            result[name] = {"bins": snapshot(ns["packer"]), "error": None}
        except Exception as e:  # registra o erro em vez de parar
            result[name] = {"bins": [], "error": f"{type(e).__name__}: {e}"}
        finally:
            sys.stdout = stdout
            devnull.close()
            plt.close("all")
        result[name]["seconds"] = round(time.time() - t, 2)
        print(name, result[name]["error"] or "ok", result[name]["seconds"], "s")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1)


if __name__ == "__main__":
    main(sys.argv[1])
