"""Turn eval/results/results.csv into a summary table (markdown) and 3 slide-ready charts.

  python -m eval.report
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "eval" / "results"

# Display order and names. Colour = role (agent / baseline / ablation), so it carries meaning.
METHODS = ["agent", "rules_only", "restart_all", "no_invariants", "no_verify"]
LABEL = {"agent": "Full agent", "rules_only": "Rules only\n(no LLM)", "restart_all": "Restart\neverything",
         "no_invariants": "No invariant\nchecks (logs only)", "no_verify": "No verify\nstep"}
ROLE = {"agent": "Agent", "rules_only": "Baseline", "restart_all": "Baseline",
        "no_invariants": "Ablation", "no_verify": "Ablation"}
COLOR = {"Agent": "#2a78d6", "Baseline": "#898781", "Ablation": "#eb6834"}
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e1e0d9", "#fcfcfb"

plt.rcParams.update({"font.family": ["Segoe UI", "DejaVu Sans"], "font.size": 13, "axes.edgecolor": "#c3c2b7",
                     "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
                     "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE})


def load():
    df = pd.read_csv(RESULTS / "results.csv")
    df["total_tokens"] = df.tokens_in + df.cache_read + df.cache_write + df.tokens_out
    return df


def agg(g):
    rec = g[g.recovered == 1]
    return pd.Series({
        "runs": len(g), "success": g.success.mean(), "outcome_ok": g.outcome_correct.mean(),
        "recovered": g.recovered.mean(), "rc_f1": g.root_cause_f1.mean(),
        "ttr": rec.time_to_recover_s.mean() if len(rec) else float("nan"),
        "actions": g.n_actions.mean(), "unnecessary": g.n_unnecessary.mean(),
        "dup": g.duplicate_shipments.sum(), "lost": g.orders_lost.mean(), "false_claim": g.false_claim.mean(),
        "tokens": g.total_tokens.mean(), "cost": g.cost_usd.sum(),
    })


def table(df, title):
    rows = ["| Method | Runs | Success | Outcome right | Shop recovered | Root-cause F1 | Time to recover (s) | Actions | "
            "Unnecessary actions | Duplicate shipments | Orders lost (mean) | False 'fixed' claims | Tokens (mean) | Cost ($) |",
            "|" + "---|" * 14]
    for m in METHODS:
        g = df[df.method == m]
        if g.empty:
            continue
        a = agg(g)
        ttr = "-" if pd.isna(a.ttr) else f"{a.ttr:.0f}"
        rows.append(f"| {m} | {int(a.runs)} | {a.success:.0%} | {a.outcome_ok:.0%} | {a.recovered:.0%} | {a.rc_f1:.2f} | {ttr} | "
                    f"{a.actions:.1f} | {a.unnecessary:.2f} | {int(a.dup)} | {a.lost:.2f} | {a.false_claim:.0%} | "
                    f"{a.tokens:,.0f} | {a.cost:.3f} |")
    return f"### {title}\n\n" + "\n".join(rows) + "\n"


def scenario_table(df, title):
    rows = ["| Scenario | Expected | Successes | Outcomes right | Recovered | Root-cause F1 | Orders lost (mean) | Actions (mean) |",
            "|" + "---|" * 8]
    for s, g in df.groupby("scenario", sort=False):
        rows.append(f"| {s} | {g.expected_outcome.iloc[0]} | {int(g.success.sum())}/{len(g)} | {int(g.outcome_correct.sum())}/{len(g)} | "
                    f"{int(g.recovered.sum())}/{len(g)} | {g.root_cause_f1.mean():.2f} | {g.orders_lost.mean():.1f} | {g.n_actions.mean():.1f} |")
    return f"### {title}\n\n" + "\n".join(rows) + "\n"


def failures(df):
    bad = df[(df.success == 0)]
    if bad.empty:
        return "### Failed runs\n\nNone.\n"
    rows = ["| Run | Outcome (expected) | Recovered | Still failing | Actions | Root causes (expected) |", "|---|---|---|---|---|---|"]
    for _, r in bad.iterrows():
        rows.append(f"| {r.job_id} | {r.outcome} ({r.expected_outcome}) | {r.recovered} | {r.still_failing if isinstance(r.still_failing, str) else ''} "
                    f"| {r.actions if isinstance(r.actions, str) else '-'} | {r.root_causes if isinstance(r.root_causes, str) else '-'} "
                    f"({r.expected_root_causes if isinstance(r.expected_root_causes, str) else '-'}) |")
    return "### Failed runs\n\n" + "\n".join(rows) + "\n"


def style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="y", color=GRID, linewidth=1)
    ax.set_axisbelow(True)


def legend(ax, roles, **kw):
    handles = [plt.Rectangle((0, 0), 1, 1, color=COLOR[r]) for r in roles]
    ax.legend(handles, roles, frameon=False, labelcolor=INK2, **kw)


def bar_by_method(ax, df, col, fmt, ylim=None, ylabel=""):
    ms = [m for m in METHODS if m in set(df.method)]
    vals = [df[df.method == m][col].mean() for m in ms]
    ns = [len(df[df.method == m]) for m in ms]
    bars = ax.bar(range(len(ms)), vals, width=0.62, color=[COLOR[ROLE[m]] for m in ms])
    style(ax)
    ax.set_xticks(range(len(ms)))
    ax.set_xticklabels([LABEL[m] + "\n(n=" + str(n) + ")" for m, n in zip(ms, ns)], fontsize=11)
    ax.set_ylabel(ylabel)
    top = ylim[1] if ylim else max(vals + [1]) * 1.25
    ax.set_ylim(0, top)
    for b, v, n in zip(bars, vals, ns):
        ax.text(b.get_x() + b.get_width() / 2, v + top * 0.02, fmt(v), ha="center", va="bottom", color=INK, fontsize=13, fontweight="bold")
    return ms


def chart_success(ho):
    fig, ax = plt.subplots(figsize=(11, 5.8), dpi=200)
    ms = bar_by_method(ax, ho, "success", lambda v: f"{v:.0%}", ylim=(0, 1.3), ylabel="Runs fully correct")
    ax.set_yticks([0, .25, .5, .75, 1.0])
    ax.set_yticklabels(["0%", "25%", "50%", "75%", "100%"])
    ax.set_title("Held-out scenarios: share of runs where the outcome was right AND the shop really recovered",
                 loc="left", fontsize=13, color=INK, pad=14)
    legend(ax, [r for r in ("Agent", "Baseline", "Ablation") if r in {ROLE[m] for m in ms}], loc="upper center", ncol=3)
    fig.tight_layout()
    fig.savefig(RESULTS / "chart_success.png")


def chart_losses(ho):
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.6), dpi=200)
    bar_by_method(axes[0], ho, "orders_lost", lambda v: f"{v:.1f}", ylabel="Orders")
    axes[0].set_title("Customer orders lost after the fix\n(mean per run)", loc="left", fontsize=13, color=INK)
    bar_by_method(axes[1], ho, "false_claim", lambda v: f"{v:.0%}", ylim=(0, 1.2))
    axes[1].set_yticks([0, .25, .5, .75, 1.0])
    axes[1].set_yticklabels(["0%", "25%", "50%", "75%", "100%"])
    axes[1].set_title("Said 'fixed' but the shop was still broken\n(share of runs)", loc="left", fontsize=13, color=INK)
    for ax in axes:
        ax.tick_params(axis="x", labelsize=9.5)
    fig.tight_layout()
    fig.savefig(RESULTS / "chart_losses.png")


def chart_scenarios(df):
    """Grid of held-out scenarios x methods. Cell = share of runs that fully succeeded (k/n printed)."""
    from matplotlib.colors import LinearSegmentedColormap
    ho = df[df.set == "heldout"]
    scen = list(dict.fromkeys(ho.scenario))
    ms = [m for m in METHODS if m in set(ho.method)]
    cmap = LinearSegmentedColormap.from_list("one_hue", ["#e7eef8", "#2a78d6"])   # one hue, light -> dark
    fig, ax = plt.subplots(figsize=(11, 0.5 * len(scen) + 2.2), dpi=200)
    for i, sname in enumerate(scen):
        for j, m in enumerate(ms):
            g = ho[(ho.scenario == sname) & (ho.method == m)]
            v = g.success.mean()
            ax.add_patch(plt.Rectangle((j, i), 0.96, 0.9, color=cmap(v)))
            ax.text(j + 0.48, i + 0.45, f"{int(g.success.sum())}/{len(g)}", ha="center", va="center", fontsize=12,
                    fontweight="bold", color="white" if v > 0.55 else INK)
    ax.set_xlim(0, len(ms))
    ax.set_ylim(len(scen), 0)
    ax.set_xticks([j + 0.48 for j in range(len(ms))])
    ax.set_xticklabels([LABEL[m] for m in ms], fontsize=10.5)
    ax.xaxis.tick_top()
    ax.set_yticks([i + 0.45 for i in range(len(scen))])
    ax.set_yticklabels([s_.replace("ho_", "") for s_ in scen], fontsize=11.5)
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.tick_params(length=0)
    fig.text(0.01, 0.01, "Each cell: successful runs / runs (the agent ran 3x per scenario, the others once). "
             "Darker blue = more successful.", fontsize=10, color=INK2)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(RESULTS / "chart_scenarios.png")


def main():
    df = load()
    dev, ho = df[df.set == "dev"], df[df.set == "heldout"]
    versions = sorted(df.agent_version.unique())
    parts = ["# Evaluation results\n",
             f"Agent source versions in these results: `{', '.join(versions)}`. Success = outcome matches expectation AND an independent "
             "check shows the shop recovered (the only exemption: the payment-success check when the provider is down).\n"]
    if len(dev):
        parts += [table(dev, "Dev set (used while building)")]
    if len(ho):
        parts += [table(ho, "Held-out set (never tuned on)")]
    for name, d in (("Dev", dev), ("Held-out", ho)):
        if len(d[d.method == "agent"]):
            parts.append(scenario_table(d[d.method == "agent"], f"Full agent per scenario: {name}"))
    parts.append(failures(df))
    (RESULTS / "summary.md").write_text("\n".join(parts), encoding="utf-8")
    if len(ho):
        chart_success(ho)
        chart_losses(ho)
    if len(ho):
        chart_scenarios(df)
    print("wrote summary.md + charts to", RESULTS)


if __name__ == "__main__":
    main()
