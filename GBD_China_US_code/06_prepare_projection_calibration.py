import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent

FORECAST_ROOT = ROOT / "data" / "raw" / "forecasts"
HISTORY_ROOT = ROOT / "data" / "raw" / "history"
OUT = ROOT / "outputs" / "gbd_neuro_calibration"

def finite_or_none(x):
    return None if pd.isna(x) or not np.isfinite(x) else float(x)


def ratio(num, den):
    if pd.isna(num) or pd.isna(den) or den <= 0:
        return np.nan
    return num / den


def load_history(country):
    filename = "China DALY.csv" if country == "China" else "US DALY.csv"
    return pd.read_csv(HISTORY_ROOT / filename)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    histories = {c: load_history(c) for c in ["China", "United States of America"]}
    coeffs, projections, issues = [], [], []

    for metric_folder, metric_label, hist_metric, hist_age in [
        ("raw number", "DALY number", "Number", "All ages"),
        ("raw ASR", "DALY ASR", "Rate", "Age-standardized"),
    ]:
        for file in sorted((FORECAST_ROOT / metric_folder).glob("*.csv")):
            pred = pd.read_csv(file)
            pred = pred[pred["Year"].notna()].copy()
            country_pred = str(pred["Location"].dropna().iloc[0])
            country_hist = "China" if country_pred == "China" else "United States of America"
            cause = str(pred["Cause of death or injury"].dropna().iloc[0])
            sexes = sorted(pred["Sex"].dropna().unique().tolist())
            if sexes != ["Both"]:
                issues.append({"severity": "warning", "issue": "Unexpected forecast sex coverage", "file": file.name, "detail": str(sexes)})

            p = pred[(pred["Scenario"] == "Reference") & (pred["Sex"] == "Both")]
            anchor = p[p["Year"] == 2023]
            h = histories[country_hist]
            obs = h[(h["year"] == 2023) & (h["sex_name"] == "Both") &
                    (h["cause_name"] == cause) & (h["metric_name"] == hist_metric) &
                    (h["age_name"] == hist_age)]
            key = f"{country_pred}|{cause}|Both|{metric_label}"
            if len(anchor) != 1 or len(obs) != 1:
                issues.append({"severity": "error", "issue": "Anchor match not unique", "file": file.name,
                               "detail": f"{key}; forecast={len(anchor)}, observed={len(obs)}"})
                continue

            a, o = anchor.iloc[0], obs.iloc[0]
            k_mean = ratio(o.val, a.Value)
            k_upper = ratio(o.upper - o.val, a["Upper bound"] - a.Value)
            k_lower = ratio(o.val - o.lower, a.Value - a["Lower bound"])
            flags = []
            if pd.isna(k_mean) or pd.isna(k_upper) or pd.isna(k_lower):
                flags.append("不可计算系数")
            if pd.notna(k_mean) and (k_mean > 3 or k_mean < 0.3):
                flags.append("均值系数超出0.3–3")
            if pd.notna(k_upper) and (k_upper > 3 or k_upper < 0.3):
                flags.append("上界距离系数超出0.3–3")
            if pd.notna(k_lower) and (k_lower > 3 or k_lower < 0.3):
                flags.append("下界距离系数超出0.3–3")

            coeffs.append({
                "key": key, "country": country_pred, "cause": cause, "sex": "Both", "metric": metric_label,
                "forecast_2023_mean": finite_or_none(a.Value), "forecast_2023_lower": finite_or_none(a["Lower bound"]),
                "forecast_2023_upper": finite_or_none(a["Upper bound"]), "gbd2023_mean": finite_or_none(o.val),
                "gbd2023_lower": finite_or_none(o.lower), "gbd2023_upper": finite_or_none(o.upper),
                "mean_factor": finite_or_none(k_mean), "upper_distance_factor": finite_or_none(k_upper),
                "lower_distance_factor": finite_or_none(k_lower), "qa_flag": "; ".join(flags) if flags else "通过",
                "source_forecast": str(file), "source_history": str(HISTORY_ROOT / ("China DALY.csv" if country_pred == "China" else "US DALY.csv")),
            })

            future = pred[(pred["Sex"] == "Both") & (pred["Year"] >= 2024) & (pred["Year"] <= 2050) & pred["Value"].notna()].copy()
            for _, row in future.sort_values(["Scenario", "Year"]).iterrows():
                projections.append({
                    "key": key, "country": country_pred, "cause": cause, "sex": "Both", "metric": metric_label,
                    "scenario": str(row.Scenario),
                    "year": int(row.Year), "forecast_mean": finite_or_none(row.Value),
                    "forecast_lower": finite_or_none(row["Lower bound"]), "forecast_upper": finite_or_none(row["Upper bound"]),
                    "mean_factor": finite_or_none(k_mean), "upper_distance_factor": finite_or_none(k_upper),
                    "lower_distance_factor": finite_or_none(k_lower), "coefficient_qa": "; ".join(flags) if flags else "通过",
                })

    expected_coeffs, expected_proj = 2 * 20 * 2, 2 * 20 * 2 * 5 * 27
    if len(coeffs) != expected_coeffs:
        issues.append({"severity": "error", "issue": "Coefficient row count mismatch", "file": "all", "detail": f"actual={len(coeffs)}, expected={expected_coeffs}"})
    if len(projections) != expected_proj:
        issues.append({"severity": "error", "issue": "Projection row count mismatch", "file": "all", "detail": f"actual={len(projections)}, expected={expected_proj}"})
    issues.append({"severity": "limitation", "issue": "Sex coverage", "file": "all forecast CSVs", "detail": "Only Both is present; Male/Female projections cannot be calculated from supplied forecast files."})
    issues.append({"severity": "note", "issue": "Past scenario", "file": "all forecast CSVs", "detail": "Past contains no non-missing values for 2024–2050 and is therefore not included as a future scenario."})
    issues.append({"severity": "method", "issue": "Scenario calibration", "file": "all forecast CSVs", "detail": "Reference-derived 2023 factors are applied uniformly to all five future scenarios to preserve official relative scenario differences."})

    payload = {"coefficients": coeffs, "projections": projections, "issues": issues,
               "counts": {"coefficients": len(coeffs), "projections": len(projections)}}
    (OUT / "calibration_data.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame(coeffs).to_csv(OUT / "calibration_coefficients.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(projections).to_csv(OUT / "calibrated_projection_inputs.csv", index=False, encoding="utf-8-sig")
    print(json.dumps({"counts": payload["counts"], "issues": issues,
                      "flagged_coefficients": sum(x["qa_flag"] != "通过" for x in coeffs)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
