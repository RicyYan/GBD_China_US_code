from pathlib import Path
import textwrap

import matplotlib as mpl
mpl.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent

INPUT = ROOT / "data" / "raw" / "risk_factors.csv"

OUT = ROOT / "outputs" / "risk_factor_daly"
OUT.mkdir(parents=True, exist_ok=True)

JPG_OUT = OUT / "jpg"
JPG_OUT.mkdir(parents=True, exist_ok=True)


mpl.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
    "svg.fonttype": "none",
    "pdf.fonttype": 42,
    "font.size": 7,
    "axes.titlesize": 7.4,
    "axes.labelsize": 8,
    "axes.linewidth": 0.65,
    "xtick.labelsize": 6.3,
    "ytick.labelsize": 6.3,
    "legend.fontsize": 6.5,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "legend.frameon": False,
})

# Color-blind-conscious, muted categorical palette; fixed across every panel/export.
COLORS = [
    "#4477AA", "#EE6677", "#228833", "#CCBB44", "#66CCEE",
    "#AA3377", "#BBBBBB", "#EE8866", "#44AA99", "#999933",
    "#882255", "#6699CC", "#AA4466",
]

COUNTRIES = ["China", "United States of America"]
COUNTRY_TITLES = {"China": "China", "United States of America": "United States"}


def load_data():
    raw = pd.read_csv(INPUT)
    d = raw.loc[
        (raw["measure_name"] == "DALYs (Disability-Adjusted Life Years)")
        & (raw["sex_name"] == "Both")
        & (raw["age_name"] == "Age-standardized")
        & (raw["metric_name"] == "Rate")
        & raw["location_name"].isin(COUNTRIES),
        ["location_name", "cause_name", "rei_name", "year", "val"],
    ].copy()
    if d.empty:
        raise ValueError("No age-standardized DALY-rate records were found.")
    key = ["location_name", "cause_name", "rei_name", "year"]
    if d.duplicated(key).any():
        raise ValueError("Duplicate country-cause-risk-year records were found.")
    if d["val"].isna().any():
        raise ValueError("Missing DALY-rate values were found.")
    return d


def display_cause(name):
    replacements = {
        "Alzheimer's disease and other dementias": "Alzheimer's disease and\nother dementias",
        "Neonatal encephalopathy due to birth asphyxia and trauma":
            "Neonatal encephalopathy due to\nbirth asphyxia and trauma",
        "Intracerebral hemorrhage": "Intracerebral haemorrhage",
        "Subarachnoid hemorrhage": "Subarachnoid haemorrhage",
    }
    return replacements.get(name, "\n".join(textwrap.wrap(name, 28)))


def build_arrays(d):
    # Rank diseases by the two-country mean total attributable rate.
    cause_order = (
        d.groupby(["location_name", "cause_name", "year"], observed=True)["val"].sum()
        .groupby("cause_name").mean().sort_values(ascending=False).index.tolist()
    )
    # Largest layers at the bottom improve stability and readability.
    risk_order = d.groupby("rei_name", observed=True)["val"].sum().sort_values(ascending=False).index.tolist()
    years = np.arange(int(d.year.min()), int(d.year.max()) + 1)
    arrays = {}
    ylimits = {}
    for cause in cause_order:
        maxima, minima = [], []
        for country in COUNTRIES:
            p = (d[(d.location_name == country) & (d.cause_name == cause)]
                 .pivot(index="year", columns="rei_name", values="val")
                 .reindex(index=years, columns=risk_order, fill_value=0.0)
                 .fillna(0.0))
            arrays[(country, cause)] = p
            maxima.append(p.clip(lower=0).sum(axis=1).max())
            minima.append(p.clip(upper=0).sum(axis=1).min())
        top = max(maxima)
        bottom = min(minima)
        pad = max(top - bottom, 1.0) * 0.04
        ylimits[cause] = (bottom - pad if bottom < 0 else 0, top + pad)
    return cause_order, risk_order, years, arrays, ylimits


def style_axis(ax, cause, ylimits, row, col, nrows, show_ylabel):
    ax.set_title(display_cause(cause), pad=3, fontweight="semibold")
    ax.set_xlim(1990, 2023)
    ax.set_ylim(*ylimits[cause])
    ax.set_xticks([1990, 2000, 2010, 2020, 2023])
    ax.grid(axis="y", color="#D9D9D9", linewidth=0.45, alpha=0.8)
    ax.axhline(0, color="#555555", linewidth=0.55, zorder=3)
    ax.set_axisbelow(True)
    ax.tick_params(length=2.5, width=0.55, pad=1.5)
    if row < nrows - 1:
        ax.tick_params(labelbottom=False)
    if not show_ylabel:
        ax.tick_params(labelleft=False)
        ax.spines["left"].set_visible(False)
    if row == nrows - 1:
        ax.set_xlabel("Year")


def add_stack(ax, p, risk_order):
    # Rank within each country-disease panel. The largest average absolute
    # attributable burden is drawn nearest zero (the visual bottom/base).
    local_order = p.abs().mean(axis=0).sort_values(ascending=False).index.tolist()
    color_map = dict(zip(risk_order, COLORS))
    pos = p.clip(lower=0)
    neg = p.clip(upper=0)
    ax.stackplot(
        p.index.to_numpy(),
        *[pos[r].to_numpy() for r in local_order],
        colors=[color_map[r] for r in local_order],
        linewidth=0.25,
        edgecolor="white",
        alpha=0.96,
    )
    ax.stackplot(
        p.index.to_numpy(),
        *[neg[r].to_numpy() for r in local_order],
        colors=[color_map[r] for r in local_order],
        linewidth=0.25,
        edgecolor="white",
        alpha=0.96,
    )


def legend_handles(risk_order):
    return [Patch(facecolor=c, edgecolor="none", label=r) for r, c in zip(risk_order, COLORS)]


def save_jpg(fig, stem):
    fig.savefig(JPG_OUT / f"{stem}.jpg", dpi=400, bbox_inches="tight",
                facecolor="white", pil_kwargs={"quality": 95, "subsampling": 0})


def plot_country(country, cause_order, risk_order, arrays, ylimits):
    nrows, ncols = 5, 2
    fig, axes = plt.subplots(nrows, ncols, figsize=(7.20, 8.25), constrained_layout=False)
    for i, cause in enumerate(cause_order):
        row, col = divmod(i, ncols)
        ax = axes[row, col]
        add_stack(ax, arrays[(country, cause)], risk_order)
        style_axis(ax, cause, ylimits, row, col, nrows, show_ylabel=True)
    fig.supylabel("Age-standardized DALY rate per 100,000 population", x=0.012, fontsize=8.5)
    fig.suptitle(COUNTRY_TITLES[country], x=0.04, y=0.985, ha="left", fontsize=12, fontweight="bold")
    fig.legend(handles=legend_handles(risk_order), loc="lower center", ncol=4,
               bbox_to_anchor=(0.5, 0.005), columnspacing=1.2, handlelength=1.2)
    fig.subplots_adjust(left=0.105, right=0.985, top=0.935, bottom=0.16, hspace=0.42, wspace=0.12)
    stem = "china_risk_factor_daly" if country == "China" else "united_states_risk_factor_daly"
    save_jpg(fig, stem)
    plt.close(fig)


def plot_combined(cause_order, risk_order, arrays, ylimits):
    # Five rows × four columns: matched diseases share a row and a common y-scale.
    nrows, ncols = 5, 4
    fig, axes = plt.subplots(nrows, ncols, figsize=(11.8, 8.45), constrained_layout=False)
    for country_idx, country in enumerate(COUNTRIES):
        for local_i, cause in enumerate(cause_order):
            row, local_col = divmod(local_i, 2)
            col = country_idx * 2 + local_col
            ax = axes[row, col]
            add_stack(ax, arrays[(country, cause)], risk_order)
            style_axis(ax, cause, ylimits, row, col, nrows, show_ylabel=True)
    fig.text(0.255, 0.968, "China", ha="center", va="top", fontsize=12, fontweight="bold")
    fig.text(0.745, 0.968, "United States", ha="center", va="top", fontsize=12, fontweight="bold")
    fig.text(0.018, 0.952, "a", fontsize=11, fontweight="bold")
    fig.text(0.508, 0.952, "b", fontsize=11, fontweight="bold")
    fig.supylabel("Age-standardized DALY rate per 100,000 population", x=0.006, fontsize=8.5)
    fig.legend(handles=legend_handles(risk_order), loc="lower center", ncol=7,
               bbox_to_anchor=(0.5, 0.004), columnspacing=1.2, handlelength=1.2)
    fig.subplots_adjust(left=0.064, right=0.992, top=0.91, bottom=0.13, hspace=0.42, wspace=0.14)
    save_jpg(fig, "china_united_states_combined_risk_factor_daly")
    plt.close(fig)


def main():
    d = load_data()
    cause_order, risk_order, years, arrays, ylimits = build_arrays(d)
    for country in COUNTRIES:
        plot_country(country, cause_order, risk_order, arrays, ylimits)
    plot_combined(cause_order, risk_order, arrays, ylimits)
    print(f"Wrote JPG outputs to: {JPG_OUT}")
    print(f"Years: {years.min()}-{years.max()}; causes: {len(cause_order)}; risks: {len(risk_order)}")


if __name__ == "__main__":
    main()
