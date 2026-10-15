import json
from pathlib import Path

import numpy as np
import pandas as pd


# Paths relative to the project root
ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "data" / "raw"

RAW_FILES = [
    RAW_DIR / "injury_yld.csv",
    RAW_DIR / "guillain_barre_yld.csv",
    RAW_DIR / "neurological_20_causes_yld.csv",
]

POP_UNDER5 = RAW_DIR / "population_global_under5.csv"
POP_OLDER = RAW_DIR / "population_global.csv"

WORK_DIR = ROOT / "outputs" / "yld_age_standardization"
DATA_DIR = WORK_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

START_YEAR, END_YEAR = 1990, 2023
COUNTRIES = ["China", "United States of America"]
AGE_GROUPS = {
    "younger than 5 years": ["<28 days", "1-5 months", "6-11 months", "12-23 months", "2-4 years"],
    "5-19 years": ["5-9 years", "10-14 years", "15-19 years"],
    "20-59 years": ["20-24 years", "25-29 years", "30-34 years", "35-39 years",
                    "40-44 years", "45-49 years", "50-54 years", "55-59 years"],
    "60-79 years": ["60-64 years", "65-69 years", "70-74 years", "75-79 years"],
    "80 years or older": ["80-84 years", "85-89 years", "90-94 years", "95+ years"],
}


def records(df):
    return df.astype(object).where(pd.notna(df), None).to_dict(orient="records")


def build_weights():
    frames = []
    for source, groups in [
        (POP_UNDER5, {"younger than 5 years": AGE_GROUPS["younger than 5 years"]}),
        (POP_OLDER, {k: v for k, v in AGE_GROUPS.items() if k != "younger than 5 years"}),
    ]:
        pop = pd.read_csv(source)
        for group, ages in groups.items():
            selected = pop.loc[
                pop["location_name"].eq("Global")
                & pop["sex_name"].eq("Both")
                & pop["year"].between(START_YEAR, END_YEAR)
                & pop["age_name"].isin(ages),
                ["age_id", "age_name", "year", "val"],
            ].copy()
            if set(selected["age_name"]) != set(ages):
                missing = sorted(set(ages) - set(selected["age_name"]))
                raise ValueError(f"{source.name} missing ages for {group}: {missing}")
            if selected.duplicated(["age_name", "year"]).any():
                raise ValueError(f"Duplicate population rows in {source.name}: {group}")
            w = (selected.groupby(["age_id", "age_name"], as_index=False)["val"].sum()
                 .rename(columns={"val": "world_population_1990_2023"}))
            w["age_group"] = group
            w["weight"] = w["world_population_1990_2023"] / w["world_population_1990_2023"].sum()
            w["population_source_file"] = source.name
            w["weight_basis"] = "Global, Both sexes, population summed over 1990-2023"
            order = {age: i for i, age in enumerate(ages)}
            w["age_order"] = w["age_name"].map(order)
            frames.append(w)
    weights = pd.concat(frames, ignore_index=True)
    group_order = {g: i for i, g in enumerate(AGE_GROUPS)}
    weights["group_order"] = weights["age_group"].map(group_order)
    weights = weights.sort_values(["group_order", "age_order"]).reset_index(drop=True)
    sums = weights.groupby("age_group")["weight"].sum()
    if not np.allclose(sums.to_numpy(), 1.0, atol=1e-12):
        raise AssertionError(f"Weight sums failed: {sums.to_dict()}")
    return weights


def process_file(path, weights):
    raw = pd.read_csv(path)
    for col in ["rei_id", "rei_name"]:
        if col not in raw.columns:
            raw[col] = pd.NA
    required = {
        "measure_id", "measure_name", "location_id", "location_name", "sex_id", "sex_name",
        "age_id", "age_name", "cause_id", "cause_name", "rei_id", "rei_name", "metric_name",
        "year", "val", "lower", "upper",
    }
    missing = required - set(raw.columns)
    if missing:
        raise ValueError(f"{path.name} missing columns: {sorted(missing)}")

    rate = raw.loc[
        raw["metric_name"].astype(str).str.strip().str.casefold().eq("rate")
        & raw["location_name"].isin(COUNTRIES)
        & raw["sex_name"].eq("Both")
        & raw["year"].between(START_YEAR, END_YEAR)
        & raw["age_name"].isin([a for ages in AGE_GROUPS.values() for a in ages])
    ].copy()
    rate["source_file"] = path.name
    rate["disease_name"] = rate["rei_name"].where(rate["rei_name"].notna(), rate["cause_name"])
    # Normalize optional identifiers/names so missing rei fields retain the same
    # dtype through groupby/reset_index and the valid-key merge.
    for col in ["cause_id", "cause_name", "rei_id", "rei_name"]:
        rate[col] = rate[col].astype("string")

    missing_estimates = int(rate[["val", "lower", "upper"]].isna().sum().sum())
    negative_rows = int((rate[["val", "lower", "upper"]] < 0).any(axis=1).sum())
    interval_violations = int(((rate["lower"] > rate["val"]) | (rate["val"] > rate["upper"])).sum())
    if missing_estimates or negative_rows or interval_violations:
        raise ValueError(
            f"Invalid estimates in {path.name}: missing={missing_estimates}, "
            f"negative={negative_rows}, interval={interval_violations}"
        )

    age_map = {age: group for group, ages in AGE_GROUPS.items() for age in ages}
    rate["age_group"] = rate["age_name"].map(age_map)
    rate = rate.merge(weights[["age_name", "age_group", "weight"]],
                      on=["age_name", "age_group"], how="left", validate="many_to_one")
    if rate["weight"].isna().any():
        raise ValueError(f"Unmatched population weights in {path.name}")

    keys = [
        "source_file", "location_id", "location_name", "sex_id", "sex_name",
        "measure_id", "measure_name", "cause_id", "cause_name", "rei_id", "rei_name",
        "disease_name", "year", "age_group",
    ]
    expected = {group: len(ages) for group, ages in AGE_GROUPS.items()}
    checks = (rate.groupby(keys, dropna=False)["age_name"]
              .agg(observed_age_count="nunique", observed_row_count="size")
              .reset_index())
    checks["expected_age_count"] = checks["age_group"].map(expected)
    checks["complete_and_unique"] = (
        checks["observed_age_count"].eq(checks["expected_age_count"])
        & checks["observed_row_count"].eq(checks["expected_age_count"])
    )
    invalid = checks.loc[~checks["complete_and_unique"]].copy()
    valid_keys = checks.loc[checks["complete_and_unique"], keys]
    valid = rate.merge(valid_keys, on=keys, how="inner")
    for source, target in [("val", "weighted_val"), ("lower", "weighted_lower"), ("upper", "weighted_upper")]:
        valid[target] = valid[source] * valid["weight"]

    result = (valid.groupby(keys, as_index=False, dropna=False)
              .agg(standardized_rate=("weighted_val", "sum"),
                   standardized_lower=("weighted_lower", "sum"),
                   standardized_upper=("weighted_upper", "sum"),
                   age_count=("age_name", "nunique"),
                   weight_sum=("weight", "sum")))
    result["metric_name"] = "Rate"
    result["rate_unit_note"] = "GBD source Rate; typically per 100,000 population"
    result["standard_population"] = "Global Both population summed over 1990-2023; normalized within age group"

    qc = {
        "source_file": path.name,
        "input_rows": int(len(raw)),
        "selected_rate_age_rows": int(len(rate)),
        "candidate_groups": int(len(checks)),
        "output_rows": int(len(result)),
        "incomplete_or_duplicate_groups": int(len(invalid)),
        "missing_estimate_cells": missing_estimates,
        "negative_estimate_rows": negative_rows,
        "interval_violation_rows": interval_violations,
    }
    return rate, result, invalid, qc


weights = build_weights()
all_rates, all_results, all_invalid, qc_rows = [], [], [], []
for raw_file in RAW_FILES:
    rate, result, invalid, qc = process_file(raw_file, weights)
    all_rates.append(rate)
    all_results.append(result)
    if not invalid.empty:
        all_invalid.append(invalid)
    qc_rows.append(qc)

rates = pd.concat(all_rates, ignore_index=True)
results = pd.concat(all_results, ignore_index=True)
invalid = pd.concat(all_invalid, ignore_index=True) if all_invalid else pd.DataFrame(columns=[
    "source_file", "location_name", "sex_name", "measure_name", "cause_name", "rei_name",
    "disease_name", "year", "age_group", "observed_age_count", "observed_row_count",
    "expected_age_count", "complete_and_unique",
])

column_order = [
    "source_file", "location_id", "location_name", "sex_id", "sex_name", "year",
    "measure_id", "measure_name", "cause_id", "cause_name", "rei_id", "rei_name",
    "disease_name", "age_group", "metric_name", "standardized_rate",
    "standardized_lower", "standardized_upper", "age_count", "weight_sum",
    "rate_unit_note", "standard_population",
]
results = results[column_order]
group_order = {g: i for i, g in enumerate(AGE_GROUPS)}
results["_group_order"] = results["age_group"].map(group_order)
results = results.sort_values(
    ["_group_order", "source_file", "location_name", "disease_name", "year"],
    na_position="last",
).drop(columns="_group_order").reset_index(drop=True)

# Independent recalculation for each source, country, and age group using 2023.
manual_rows = []
for source_file in [p.name for p in RAW_FILES]:
    for country in COUNTRIES:
        for age_group, ages in AGE_GROUPS.items():
            candidate = results.loc[
                results["source_file"].eq(source_file)
                & results["location_name"].eq(country)
                & results["age_group"].eq(age_group)
                & results["year"].eq(2023)
            ].sort_values("disease_name")
            row = candidate.iloc[0]
            detail = rates.loc[
                rates["source_file"].eq(source_file)
                & rates["location_name"].eq(country)
                & rates["year"].eq(2023)
                & rates["disease_name"].eq(row["disease_name"])
                & rates["age_name"].isin(ages),
                ["age_name", "val", "weight"],
            ]
            manual_value = float((detail["val"] * detail["weight"]).sum())
            manual_rows.append({
                "source_file": source_file,
                "location_name": country,
                "age_group": age_group,
                "year": 2023,
                "disease_name": row["disease_name"],
                "program_rate": float(row["standardized_rate"]),
                "manual_rate": manual_value,
                "absolute_difference": abs(float(row["standardized_rate"]) - manual_value),
            })
manual = pd.DataFrame(manual_rows)
if not np.allclose(manual["program_rate"], manual["manual_rate"], atol=1e-10):
    raise AssertionError("Manual verification failed")

expected_per_group = 1564
counts = results.groupby("age_group").size().reindex(AGE_GROUPS.keys())
if not counts.eq(expected_per_group).all():
    raise AssertionError(f"Unexpected output row counts: {counts.to_dict()}")
if len(results) != 7820:
    raise AssertionError(f"Unexpected total rows: {len(results)}")
if not np.allclose(results["weight_sum"], 1.0, atol=1e-12):
    raise AssertionError("Result weight sums are not 1")

qc = pd.DataFrame(qc_rows)
summary_checks = pd.DataFrame([
    {"check": "Target years", "value": "1990-2023", "status": "PASS", "note": "34 years"},
    {"check": "Locations", "value": 2, "status": "PASS", "note": "China and United States of America"},
    {"check": "Sex", "value": "Both", "status": "PASS", "note": "Both sexes only"},
    {"check": "Age groups", "value": 5, "status": "PASS", "note": ", ".join(AGE_GROUPS)},
    {"check": "Rows per age group", "value": expected_per_group, "status": "PASS", "note": str(counts.to_dict())},
    {"check": "Total output rows", "value": len(results), "status": "PASS", "note": "Expected 7,820"},
    {"check": "Weight sums", "value": float(weights.groupby("age_group")["weight"].sum().min()), "status": "PASS", "note": "Each age group equals 1 within 1e-12"},
    {"check": "Incomplete or duplicate groups", "value": len(invalid), "status": "PASS", "note": "Expected 0"},
    {"check": "Manual verification max difference", "value": float(manual["absolute_difference"].max()), "status": "PASS", "note": "Tolerance 1e-10"},
])

for age_group in AGE_GROUPS:
    part = results.loc[results["age_group"].eq(age_group)].copy()
    (DATA_DIR / f"{age_group}.json").write_text(json.dumps(records(part), ensure_ascii=False), encoding="utf-8")

weights_out = weights[["population_source_file", "age_group", "age_id", "age_name",
                       "world_population_1990_2023", "weight", "weight_basis"]]
(DATA_DIR / "weights.json").write_text(json.dumps(records(weights_out), ensure_ascii=False), encoding="utf-8")
(DATA_DIR / "quality_by_file.json").write_text(json.dumps(records(qc), ensure_ascii=False), encoding="utf-8")
(DATA_DIR / "summary_checks.json").write_text(json.dumps(records(summary_checks), ensure_ascii=False), encoding="utf-8")
(DATA_DIR / "missing_age_details.json").write_text(json.dumps(records(invalid), ensure_ascii=False), encoding="utf-8")
(DATA_DIR / "manual_verification.json").write_text(json.dumps(records(manual), ensure_ascii=False), encoding="utf-8")

metadata = {
    "age_groups": list(AGE_GROUPS),
    "rows_by_age_group": {k: int(v) for k, v in counts.items()},
    "total_rows": int(len(results)),
    "manual_rows": int(len(manual)),
    "manual_max_difference": float(manual["absolute_difference"].max()),
    "invalid_groups": int(len(invalid)),
}
(DATA_DIR / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(metadata, ensure_ascii=False))
