"""Head to head: the same 60-beat run on the audio and markdown backends."""
import os
import sys

import numpy as np

import simulate


def main(out):
    os.makedirs(out, exist_ok=True)
    runs = {b: simulate.main(out, b, quiet=True) for b in ("audio", "md")}
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    beats = [r["beat"] for r in runs["audio"]]
    lines = {
        "message thread": ([r["thread_tokens"] for r in runs["audio"]], [r["thread_bytes"] for r in runs["audio"]], "#c0392b"),
        "plain markdown files": ([r["md_tokens"] for r in runs["audio"]], [r["md_bytes"] for r in runs["audio"]], "#95a5a6"),
        "Ensemble, audio": ([r["ens_tokens"] for r in runs["audio"]], [r["ens_bytes"] for r in runs["audio"]], "#2471a3"),
        "Ensemble, markdown": ([r["ens_tokens"] for r in runs["md"]], [r["ens_bytes"] for r in runs["md"]], "#27ae60"),
    }
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.3))
    for name, (tok, size, col) in lines.items():
        ls = "--" if name == "Ensemble, markdown" else "-"
        ax[0].plot(beats, np.cumsum(tok), color=col, ls=ls, label=name)
        ax[1].plot(beats, size, color=col, ls=ls, label=name)
    ax[0].set_title("Conductor tokens read, cumulative", fontsize=10)
    ax[1].set_title("Storage on disk (bytes, log scale)", fontsize=10)
    ax[1].set_yscale("log")
    for a in ax:
        a.set_xlabel("beat"); a.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(os.path.join(out, "head_to_head.png"), dpi=150)
    print(f"{'':22s}{'tokens':>8s}{'storage':>12s}")
    for name, (tok, size, _) in lines.items():
        print(f"{name:22s}{sum(tok):8.0f}{size[-1]:>12,d} B")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "out")
