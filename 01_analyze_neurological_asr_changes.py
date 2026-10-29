from argparse import ArgumentParser
from pathlib import Path

import numpy as np
import pandas as pd


def read_percentage_changes(folder: Path) -> pd.DataFrame:
    frames = []
    for path in sorted(folder.glob("*.csv")):
        data = pd.read_csv(path)
        disease_column = "rei_name" if "rei_name" in data and data["rei_name"].notna().any() else "cause_name"
        data = data.loc[
            data["sex_name"].eq("Both")
            & data["age_name"].eq("Age-standardized")
            & data["metric_name"].eq("Rate")
            & data["year_start"].eq(1990)
            & data["year_end"].eq(2023)
        ].copy()
        data["disease"] = data[disease_column]
        frames.append(data)

    if not frames:
        raise ValueError(f"No percentage-change CSV files found in {folder}")

    result = pd.concat(frames, ignore_index=True)
    result["disease"] = result["disease"].replace({
        "Head Injuries": "Head injuries",
        "Spinal Injuries": "Spinal injuries",
    })
    result["pct"] = 100 * pd.to_numeric(result["val"], errors="coerce")
    lower = 100 * pd.to_numeric(result["lower"], errors="coerce")
    upper = 100 * pd.to_numeric(result["upper"], errors="coerce")
    result["ci_low"] = np.minimum(lower, upper)
    result["ci_high"] = np.maximum(lower, upper)
    result["direction"] = np.select(
        [result["ci_low"] > 0, result["ci_high"] < 0],
        ["increase", "decrease"],
        default="uncertain",
    )
    return result[["location_name", "measure_name", "disease", "pct", "ci_low", "ci_high", "direction"]]


def read_endpoint_changes(path: Path) -> pd.DataFrame:
    data = pd.read_csv(path)
    endpoints = data[data["year"].isin([1990, 2023])].pivot_table(
        index=["location_name", "measure_name", "disease"],
        columns="year",
        values="val",
        aggfunc="first",
    )
    endpoints["computed_pct"] = 100 * (endpoints[2023] / endpoints[1990] - 1)
    endpoints.loc[endpoints[1990].eq(0), "computed_pct"] = np.nan
    return endpoints.reset_index().rename(columns={2023: "asr_2023"})


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument("--percentage-dir", type=Path, default=Path("data/percentage_change"))
    parser.add_argument("--annual-data", type=Path, default=Path("data/china_us_neurological_asr_source_data.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/asr_changes"))
    args = parser.parse_args()

    changes = read_percentage_changes(args.percentage_dir)
    endpoints = read_endpoint_changes(args.annual_data)
    result = changes.merge(
        endpoints[["location_name", "measure_name", "disease", "computed_pct", "asr_2023"]],
        on=["location_name", "measure_name", "disease"],
        how="left",
        validate="one_to_one",
    )
    result["recalculation_difference"] = (result["pct"] - result["computed_pct"]).abs()

    summary = result.pivot_table(
        index=["location_name", "measure_name"],
        columns="direction",
        values="disease",
        aggfunc="count",
        fill_value=0,
    ).reset_index()
    contrast = result.pivot_table(
        index=["measure_name", "disease"],
        columns="location_name",
        values="pct",
    ).dropna().reset_index()
    contrast["China_minus_US_pp"] = contrast["China"] - contrast["United States of America"]

    args.output_dir.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output_dir / "asr_percentage_changes.csv", index=False)
    summary.to_csv(args.output_dir / "asr_change_summary.csv", index=False)
    contrast.to_csv(args.output_dir / "china_us_change_contrast.csv", index=False)


if __name__ == "__main__":
    main()
