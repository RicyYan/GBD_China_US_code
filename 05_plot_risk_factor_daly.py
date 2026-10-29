from argparse import ArgumentParser
from pathlib import Path
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import numpy as np
import pandas as pd


COUNTRIES = ["China", "United States of America"]
COLORS = [
    "#4477AA", "#EE6677", "#228833", "#CCBB44", "#66CCEE",
    "#AA3377", "#BBBBBB", "#EE8866", "#44AA99", "#999933",
    "#882255", "#6699CC", "#AA4466",
]


def load_data(path: Path) -> pd.DataFrame:
    data = pd.read_csv(path)
    data = data.loc[
        data["measure_name"].eq("DALYs (Disability-Adjusted Life Years)")
        & data["sex_name"].eq("Both")
        & data["age_name"].eq("Age-standardized")
        & data["metric_name"].eq("Rate")
        & data["location_name"].isin(COUNTRIES),
        ["location_name", "cause_name", "rei_name", "year", "val"],
    ].dropna(subset=["rei_name", "val"])
    if data.empty:
        raise ValueError("No age-standardized DALY-rate data found")
    return data


def plot_country(data: pd.DataFrame, country: str, output: Path) -> None:
    country_data = data[data["location_name"].eq(country)]
    causes = (
        country_data.groupby("cause_name")["val"].mean()
        .sort_values(ascending=False).index.tolist()
    )
    risks = (
        country_data.groupby("rei_name")["val"].sum()
        .sort_values(ascending=False).index.tolist()
    )
    years = np.arange(country_data["year"].min(), country_data["year"].max() + 1)
    ncols = 4
    nrows = int(np.ceil(len(causes) / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(12, 2.3 * nrows), sharex=True)
    axes = np.atleast_1d(axes).ravel()

    for ax, cause in zip(axes, causes):
        table = (
            country_data[country_data["cause_name"].eq(cause)]
            .pivot_table(index="year", columns="rei_name", values="val", aggfunc="sum")
            .reindex(index=years, columns=risks, fill_value=0)
            .fillna(0)
        )
        positive = table.clip(lower=0)
        negative = table.clip(upper=0)
        ax.stackplot(years, positive.T, colors=COLORS[:len(risks)], linewidth=0)
        if negative.lt(0).any().any():
            ax.stackplot(years, negative.T, colors=COLORS[:len(risks)], linewidth=0)
        ax.axhline(0, color="#555555", linewidth=0.6)
        ax.set_title("\n".join(textwrap.wrap(cause, 28)), fontsize=8)
        ax.grid(axis="y", color="#DDDDDD", linewidth=0.5)
        ax.tick_params(labelsize=7)

    for ax in axes[len(causes):]:
        ax.remove()

    handles = [Patch(color=COLORS[i % len(COLORS)], label=risk) for i, risk in enumerate(risks)]
    fig.legend(handles=handles, loc="lower center", ncol=min(6, len(risks)), fontsize=7, frameon=False)
    fig.suptitle(f"Risk-attributable neurological DALY rates: {country.replace(' of America', '')}", fontsize=12)
    fig.supxlabel("Year")
    fig.supylabel("Age-standardized DALY rate per 100,000")
    fig.tight_layout(rect=(0.02, 0.08, 1, 0.96))
    fig.savefig(output, dpi=300, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("data/risk_factor_daly.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/risk_factor_daly"))
    args = parser.parse_args()

    data = load_data(args.input)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for country in COUNTRIES:
        name = "china" if country == "China" else "united_states"
        plot_country(data, country, args.output_dir / f"{name}_risk_factor_daly.png")


if __name__ == "__main__":
    main()
