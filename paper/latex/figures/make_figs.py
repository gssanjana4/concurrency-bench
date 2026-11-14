#!/usr/bin/env python3
"""Figures for the concurrency paper (matplotlib, vector PDF, ACL widths).

    python3 figures/make_figs.py [--data build/figdata.json]

Reads only build/figdata.json (written by make_numbers4.py from the same analyze4
outputs as numbers.tex), so figures and macros cannot disagree.
Writes figures/fig_{nonser_by_config,choices,choices_aware,h6_scaling,labels,templates}.pdf
(fig_labels panel (b) and fig_templates are EXPLORATORY, from explore4.py via figdata).

Colours: Okabe-Ito, reordered so adjacent models pass a CVD check (deutan
delta-E >= 9.6, checked with the dataviz validator); every model also has its
own marker, and labels have their own hatch, so nothing relies on colour alone.
Dry-run inputs get a "DRY RUN DATA" watermark on every figure.
"""
from __future__ import annotations

import argparse
import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from decimal import ROUND_HALF_UP, Decimal  # noqa: E402


def two(x) -> str:
    """Two decimals, rounding half up as make_numbers4.fmt does (0.125 -> 0.13, not Python's 0.12), so that the
    heat-map cells agree with the tables (review T4/T8: Qwen's lock share printed 0.12 against 0.13 elsewhere)."""
    return str(Decimal(repr(float(x))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

HERE = os.path.dirname(os.path.abspath(__file__))
COL_W = 3.03     # ACL column width (in)
TEXT_W = 6.30    # ACL text width (in)
MODEL_COLORS = ["#0072B2", "#E69F00", "#009E73", "#D55E00", "#56B4E9", "#CC79A7"]
MODEL_MARKERS = ["o", "s", "^", "D", "v", "P"]
LABEL_COLORS = {"stale_overwrite": "#0072B2", "partial_action": "#E69F00", "write_skew": "#CC79A7"}
LABEL_HATCH = {"stale_overwrite": "", "partial_action": "////", "write_skew": "...."}
CHOICE_ORDER = ["reread", "cas", "lock", "message", "none"]
FULFIL_COLOR = "#009E73"
INK, MUTED, GRID = "#222222", "#666666", "#DDDDDD"

plt.rcParams.update({
    "font.family": "serif", "font.serif": ["Times New Roman", "Times", "Nimbus Roman", "DejaVu Serif"],
    "font.size": 7, "axes.titlesize": 7, "axes.labelsize": 7, "xtick.labelsize": 6, "ytick.labelsize": 6,
    "legend.fontsize": 6, "axes.edgecolor": MUTED, "axes.linewidth": 0.6, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.labelcolor": INK, "text.color": INK, "xtick.major.width": 0.6, "ytick.major.width": 0.6,
    "pdf.fonttype": 42, "ps.fonttype": 42, "axes.spines.top": False, "axes.spines.right": False,
    "savefig.bbox": "tight", "savefig.pad_inches": 0.02,
})


def watermark(fig, dry):
    if dry:
        fig.text(0.5, 0.5, "DRY RUN DATA", fontsize=22, color="red", alpha=0.18, ha="center", va="center",
                 rotation=20, weight="bold", zorder=100)


def tt(s):
    return s.replace("_", r"\_") if plt.rcParams["text.usetex"] else s


def fig_nonser(d, out):
    """(a) non_serializable rate by config, one dot+CI per model (aware off, n=2, contended)."""
    models, configs = d["models"], d["configs"]
    fig, ax = plt.subplots(figsize=(COL_W, 2.9))
    k = len(models)
    off = np.linspace(-0.33, 0.33, k)
    for i, m in enumerate(models):
        for j, c in enumerate(configs):
            v = d["a"][m["id"]].get(c)
            if v is None or v[0] is None:
                continue
            y = j + off[i]
            ax.plot([v[1], v[2]], [y, y], color=MODEL_COLORS[i], lw=1.0, solid_capstyle="round")
            ax.plot(v[0], y, MODEL_MARKERS[i], color=MODEL_COLORS[i], ms=3.6, mec="white", mew=0.5,
                    label=m["name"] if j == 0 else None)
    ax.set_yticks(range(len(configs)))
    ax.set_yticklabels(configs, family="monospace")
    ax.invert_yaxis()
    ax.set_xlim(-0.02, 1.02)
    ax.set_xlabel("non-serializable episode rate (95% Wilson CI)")
    ax.grid(axis="x", color=GRID, lw=0.5)
    ax.set_axisbelow(True)
    for j in range(len(configs) - 1):
        ax.axhline(j + 0.5, color=GRID, lw=0.5)
    ax.legend(ncol=3, loc="upper center", bbox_to_anchor=(0.45, -0.17), frameon=False, handletextpad=0.2, columnspacing=0.8)
    watermark(fig, d["dry_run"])
    fig.savefig(out)
    plt.close(fig)


def fig_choices(d, out, aware="0"):
    """(b) coordination-choice rates: heatmap per config (rows models, cols choices)."""
    models, configs = d["models"], d["configs"]
    fig, axes = plt.subplots(2, 3, figsize=(TEXT_W, 3.0), sharex=True, sharey=True)
    cmap = matplotlib.colors.LinearSegmentedColormap.from_list("blues", ["#F4F8FB", "#9CC3E0", "#0B4F8A"])
    for ax, c in zip(axes.flat, configs):
        mat = np.full((len(models), len(CHOICE_ORDER)), np.nan)
        for i, m in enumerate(models):
            for j, ch in enumerate(CHOICE_ORDER):
                v = d["b"][aware][m["id"]][c].get(ch)
                if v is not None:
                    mat[i, j] = v
        ax.imshow(mat, vmin=0, vmax=1, cmap=cmap, aspect="auto")
        for i in range(mat.shape[0]):
            for j in range(mat.shape[1]):
                if not np.isnan(mat[i, j]):
                    ax.text(j, i, two(mat[i, j]), ha="center", va="center", fontsize=5.2,
                            color="white" if mat[i, j] > 0.6 else INK)
        ax.set_title(c, family="monospace")
        ax.set_xticks(range(len(CHOICE_ORDER)))
        ax.set_xticklabels(CHOICE_ORDER, family="monospace", rotation=0)
        ax.set_yticks(range(len(models)))
        ax.set_yticklabels([m["name"] for m in models])
        for s in ax.spines.values():
            s.set_visible(False)
        ax.tick_params(length=0)
    fig.text(0.5, -0.01, "share of agents making each choice (choices overlap; successful calls only)", ha="center")
    fig.tight_layout(h_pad=0.6, w_pad=0.4)
    watermark(fig, d["dry_run"])
    fig.savefig(out)
    plt.close(fig)


def fig_h6(d, out):
    """(c) H6: non_serializable vs number of agents (cas_available, aware off, seed 0, registered H6 clusters)."""
    models, ns = d["models"], d["scale_ns"]
    fig, ax = plt.subplots(figsize=(COL_W, 2.1))
    jit = np.linspace(-0.06, 0.06, len(models))
    for i, m in enumerate(models):
        ys = [d["c"][m["id"]].get(str(n)) for n in ns]
        xs = [np.log2(n) + jit[i] for n in ns]
        pts = [(x, y) for x, y in zip(xs, ys) if y is not None]
        if not pts:
            continue
        ax.plot(*zip(*pts), "-", marker=MODEL_MARKERS[i], color=MODEL_COLORS[i], lw=1.2, ms=3.6, mec="white", mew=0.5,
                label=m["name"])
    ax.set_xticks([np.log2(n) for n in ns])
    ax.set_xticklabels([str(n) for n in ns])
    ax.set_xlabel("agents per episode (log scale)")
    ax.set_ylabel("non-serializable rate")
    ax.set_ylim(-0.03, 1.03)
    ax.grid(axis="y", color=GRID, lw=0.5)
    ax.set_axisbelow(True)
    ax.legend(ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.25), frameon=False, handletextpad=0.3, columnspacing=0.8)
    watermark(fig, d["dry_run"])
    fig.savefig(out)
    plt.close(fig)


def fig_labels(d, out):
    """(d) top: primary-label breakdown of non-serializable episodes (exclusive; sums to the non_serializable rate).
    bottom (EXPLORATORY): store-based fulfilment (bar; posthoc_review.py), agent-view fulfilment (hollow circle; E1,
    explore4.py), both among agents whose intent was still valid, and unnecessary give-up among agents that saw a
    concurrency rejection (diamond)."""
    models, configs, labels = d["models"], d["configs"], d["labels"]
    has_e1 = "e1" in d
    nrow = 2 if has_e1 else 1
    fig, axes = plt.subplots(nrow, len(configs), figsize=(TEXT_W, 1.9 if nrow == 1 else 3.35), sharey=True, squeeze=False)
    y = np.arange(len(models))
    for ax, c in zip(axes[0], configs):
        left = np.zeros(len(models))
        for lab in labels:
            w = np.array([d["d"][m["id"]][c].get(lab) or 0.0 for m in models])
            ax.barh(y, w, left=left, height=0.62, color=LABEL_COLORS[lab], hatch=LABEL_HATCH[lab],
                    edgecolor="white", linewidth=0.6, label=lab if c == configs[0] else None)
            left += w
        ax.set_title(c, family="monospace")
    if has_e1:
        for ax, c in zip(axes[1], configs):
            fv = [((d["e1"][m["id"]].get(c) or {}).get("fulfil")) for m in models]
            sv = [((d["e1"][m["id"]].get(c) or {}).get("store_fulfil")) for m in models]
            gv = [((d["e1"][m["id"]].get(c) or {}).get("giveup")) for m in models]
            # bars: store-based fulfilment (effect survives in the final store; post hoc); hollow circle: agent-view
            ax.barh(y, [v or 0.0 for v in sv], height=0.62, color=FULFIL_COLOR, edgecolor="white", linewidth=0.6)
            fy = [(v, yy) for v, yy in zip(fv, y) if v is not None]
            if fy:
                ax.plot([v for v, _ in fy], [yy for _, yy in fy], "o", mfc="none", mec=INK, ms=3.0, mew=0.6, linestyle="none")
            gy = [(v, yy) for v, yy in zip(gv, y) if v is not None]
            if gy:
                ax.plot([v for v, _ in gy], [yy for _, yy in gy], "D", color=INK, ms=2.6, mec="white", mew=0.4, linestyle="none",
                        label="unnecessary give-up (agents that saw a rejection)" if c == configs[0] else None)
    for row in axes:
        for ax in row:
            ax.set_xlim(0, 1)
            ax.set_xticks([0, 0.5, 1])
            ax.set_xticklabels(["0", ".5", "1"])
            ax.grid(axis="x", color=GRID, lw=0.5)
            ax.set_axisbelow(True)
            ax.tick_params(axis="y", length=0)
        row[0].set_yticks(y)
        row[0].set_yticklabels([m["name"] for m in models])
    axes[0][0].invert_yaxis()
    h0, l0 = axes[0][0].get_legend_handles_labels()
    if has_e1:
        axes[0][0].text(-0.62, 1.30, "(a) integrity: primary label, share of contended episodes", transform=axes[0][0].transAxes,
                        ha="left", fontsize=6.5, weight="bold")
        axes[1][0].text(-0.62, 1.10, "(b) goodput, EXPLORATORY: share of agents", transform=axes[1][0].transAxes,
                        ha="left", fontsize=6.5, weight="bold")
        from matplotlib.lines import Line2D
        from matplotlib.patches import Patch
        h1 = [Patch(facecolor=FULFIL_COLOR, edgecolor="white"),
              Line2D([], [], marker="o", mfc="none", mec=INK, ms=3.0, mew=0.6, linestyle="none"),
              Line2D([], [], marker="D", color=INK, ms=2.6, mec="white", mew=0.4, linestyle="none")]
        l1 = ["fulfilled, effect in final store", "fulfilled, agent's own view", "unnecessary give-up"]
        fig.legend(h0 + h1, l0 + l1, loc="lower center", ncol=3, bbox_to_anchor=(0.5, -0.005), frameon=False,
                   columnspacing=1.2, handletextpad=0.3)
        fig.subplots_adjust(left=0.12, right=0.99, top=0.9, bottom=0.17, wspace=0.12, hspace=0.42)
    else:
        fig.legend(h0, l0, loc="lower center", ncol=3, bbox_to_anchor=(0.5, -0.1), frameon=False)
        fig.text(0.5, -0.17, "share of contended episodes, by primary label", ha="center")
        fig.tight_layout(w_pad=0.3)
    watermark(fig, d["dry_run"])
    fig.savefig(out)
    plt.close(fig)


def fig_templates(d, out):
    """(e) EXPLORATORY E6: non-serializable rate per template x config, one heatmap per model (aware off, n=2)."""
    models, configs, tpls = d["models"], d["configs"], d["templates"]
    fig, axes = plt.subplots(2, 3, figsize=(TEXT_W, 3.6), sharex=True, sharey=True)
    cmap = matplotlib.colors.LinearSegmentedColormap.from_list("reds", ["#FBF6F4", "#E7A68F", "#8A2B0B"])
    for ax, m in zip(axes.flat, models):
        mat = np.full((len(tpls), len(configs)), np.nan)
        for i, t in enumerate(tpls):
            for j, c in enumerate(configs):
                v = d["tpl"][m["id"]][t][c]
                if v is not None:
                    mat[i, j] = v
        ax.imshow(mat, vmin=0, vmax=1, cmap=cmap, aspect="auto")
        for i in range(mat.shape[0]):
            for j in range(mat.shape[1]):
                if not np.isnan(mat[i, j]):
                    ax.text(j, i, two(mat[i, j]), ha="center", va="center", fontsize=4.8,
                            color="white" if mat[i, j] > 0.6 else INK)
        ax.set_title(m["name"])
        ax.set_xticks(range(len(configs)))
        ax.set_xticklabels(configs, family="monospace", rotation=35, ha="right", fontsize=5)
        ax.set_yticks(range(len(tpls)))
        ax.set_yticklabels(tpls, family="monospace", fontsize=5)
        for s_ in ax.spines.values():
            s_.set_visible(False)
        ax.tick_params(length=0)
    fig.tight_layout(h_pad=0.6, w_pad=0.4)
    watermark(fig, d["dry_run"])
    fig.savefig(out)
    plt.close(fig)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(os.path.dirname(HERE), "build", "figdata.json"))
    a = ap.parse_args(argv)
    d = json.load(open(a.data))
    fig_nonser(d, os.path.join(HERE, "fig_nonser_by_config.pdf"))
    fig_choices(d, os.path.join(HERE, "fig_choices.pdf"), "0")
    fig_choices(d, os.path.join(HERE, "fig_choices_aware.pdf"), "1")
    fig_h6(d, os.path.join(HERE, "fig_h6_scaling.pdf"))
    fig_labels(d, os.path.join(HERE, "fig_labels.pdf"))
    if "tpl" in d:
        fig_templates(d, os.path.join(HERE, "fig_templates.pdf"))
    print(f"figures written (dry_run={d['dry_run']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
