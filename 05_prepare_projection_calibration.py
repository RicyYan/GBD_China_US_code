from argparse import ArgumentParser
from pathlib import Path

import numpy as np
import pandas as pd


METRICS = [
    ("raw number", "DALY number", "Number", "All ages"),
    ("raw ASR", "DALY ASR", "Rate", "Age-standardized"),
]


def safe_ratio(numerator: float, denominator: float) -> float:
    if pd.isna(numerator) or pd.isna(denominator) or denominator <= 0:
        return np.nan
    return numerator / denominator


def history_file(country: str) -> str:
    return "China DALY.csv" if country == "China" else "US DALY.csv"


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument("--forecast-dir", type=Path, default=Path("data/forecasts"))
    parser.add_argument("--history-dir", type=Path, default=Path("data/history"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/gbd_neuro_calibration"))
    args = parser.parse_args()

    histories = {
        country: pd.read_csv(args.history_dir / history_file(country))
        for country in ["China", "United States of America"]
    }
    coefficient_rows = []
    projection_rows = []

    for folder, metric, history_metric, history_age in METRICS:
        for path in sorted((args.forecast_dir / folder).glob("*.csv")):
            forecast = pd.read_csv(path)
            forecast = forecast[forecast["Year"].notna() & forecast["Sex"].eq("Both")].copy()
            if forecast.empty:
                continue

            country = str(forecast["Location"].iloc[0])
            cause = str(forecast["Cause of death or injury"].iloc[0])
            history_country = "China" if country == "China" else "United States of America"
            observed = histories[history_country]
            observed = observed.loc[
                observed["year"].eq(2023)
                & observed["sex_name"].eq("Both")
                & observed["cause_name"].eq(cause)
                & observed["metric_name"].eq(history_metric)
                & observed["age_name"].eq(history_age)
            ]
            anchor = forecast[forecast["Scenario"].eq("Reference") & forecast["Year"].eq(2023)]
            if len(anchor) != 1 or len(observed) != 1:
                raise ValueError(f"Anchor not unique for {country}, {cause}, {metric}")

            f = anchor.iloc[0]
            o = observed.iloc[0]
            mean_factor = safe_ratio(o["val"], f["Value"])
            lower_factor = safe_ratio(o["val"] - o["lower"], f["Value"] - f["Lower bound"])
            upper_factor = safe_ratio(o["upper"] - o["val"], f["Upper bound"] - f["Value"])
            if np.isnan([mean_factor, lower_factor, upper_factor]).any():
                raise ValueError(f"Calibration factor cannot be calculated for {country}, {cause}, {metric}")

            key = f"{country}|{cause}|Both|{metric}"
            coefficient_rows.append({
                "key": key,
                "country": country,
                "cause": cause,
                "metric": metric,
                "mean_factor": mean_factor,
                "lower_distance_factor": lower_factor,
                "upper_distance_factor": upper_factor,
            })

            future = forecast[forecast["Year"].between(2024, 2050) & forecast["Value"].notna()].copy()
            for _, row in future.iterrows():
                calibrated_mean = row["Value"] * mean_factor
                calibrated_lower = max(
                    0,
                    calibrated_mean - (row["Value"] - row["Lower bound"]) * lower_factor,
                )
                calibrated_upper = calibrated_mean + (row["Upper bound"] - row["Value"]) * upper_factor
                projection_rows.append({
                    "key": key,
                    "country": country,
                    "cause": cause,
                    "sex": "Both",
                    "metric": metric,
                    "scenario": row["Scenario"],
                    "year": int(row["Year"]),
                    "calibrated_mean": calibrated_mean,
                    "calibrated_lower": calibrated_lower,
                    "calibrated_upper": calibrated_upper,
                })

    coefficients = pd.DataFrame(coefficient_rows).sort_values(["country", "cause", "metric"])
    projections = pd.DataFrame(projection_rows).sort_values(
        ["country", "cause", "metric", "scenario", "year"]
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    coefficients.to_csv(args.output_dir / "calibration_coefficients.csv", index=False)
    projections.to_csv(args.output_dir / "calibrated_projections.csv", index=False)


if __name__ == "__main__":
    main()
