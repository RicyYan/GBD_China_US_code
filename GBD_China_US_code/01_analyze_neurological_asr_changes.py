from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
PCT_DIR = Path(r"C:\Users\YR\Desktop\GBD\raw\percentage change")
OUT_DIR = ROOT / "analysis"
OUT_DIR.mkdir(exist_ok=True)

ANNUAL_PATH = ROOT / "figures" / "china_us_neurological_asr_source_data.csv"
PCT_FILES = [
    (PCT_DIR / "percentage change 20causes.csv", "cause_name"),
    (PCT_DIR / "injury percentage change.csv", "rei_name"),
    (PCT_DIR / "GBpercentage change.csv", "rei_name"),
]


def load_pct():
    frames = []
    for path, disease_col in PCT_FILES:
        cols = ["location_name", "sex_name", "age_name", "measure_name", "metric_name",
                "year_start", "year_end", "val", "lower", "upper", disease_col]
        d = pd.read_csv(path, usecols=cols)
        d = d[(d.sex_name == "Both") & (d.age_name == "Age-standardized")
              & (d.metric_name == "Rate") & (d.year_start == 1990) & (d.year_end == 2023)].copy()
        d = d.rename(columns={disease_col: "disease", "val": "pct_fraction",
                              "lower": "pct_lower_fraction", "upper": "pct_upper_fraction"})
        frames.append(d[["location_name", "measure_name", "disease", "year_start", "year_end",
                         "pct_fraction", "pct_lower_fraction", "pct_upper_fraction"]])
    x = pd.concat(frames, ignore_index=True)
    x["disease"] = x["disease"].replace({
        "Head Injuries": "Head injuries", "Spinal Injuries": "Spinal injuries",
        "Guillain-Barre syndrome": "Guillain-Barre syndrome",
    })
    for c in ["pct_fraction", "pct_lower_fraction", "pct_upper_fraction"]:
        x[c.replace("_fraction", "")] = 100 * x[c]
    # Some exports name bounds by draw ordering for negative changes; normalize numerically.
    x["ci_low"] = x[["pct_lower", "pct_upper"]].min(axis=1)
    x["ci_high"] = x[["pct_lower", "pct_upper"]].max(axis=1)
    x["direction"] = np.select(
        [x.ci_low > 0, x.ci_high < 0], ["increase", "decrease"], default="uncertain")
    return x


def endpoint_changes():
    d = pd.read_csv(ANNUAL_PATH)
    p = d.pivot_table(index=["location_name", "measure_name", "disease"], columns="year", values="val")
    p["computed_pct"] = 100 * (p[2023] / p[1990] - 1)
    p.loc[p[1990] == 0, "computed_pct"] = np.nan
    p = p.reset_index()
    levels = d[d.year == 2023][["location_name", "measure_name", "disease", "val"]].rename(columns={"val": "asr_2023"})
    return p[["location_name", "measure_name", "disease", "computed_pct"]].merge(levels)


def main():
    pct = load_pct()
    end = endpoint_changes()
    a = pct.merge(end, on=["location_name", "measure_name", "disease"], how="left", validate="one_to_one")
    a["abs_recalc_diff_pp"] = (a.pct - a.computed_pct).abs()
    a.to_csv(OUT_DIR / "asr_percentage_change_validated.csv", index=False, encoding="utf-8-sig")

    counts = (a.groupby(["location_name", "measure_name", "direction"]).size()
              .unstack(fill_value=0).reset_index())
    medians = a.groupby(["location_name", "measure_name"])["pct"].median().rename("median_pct").reset_index()
    overview = counts.merge(medians)
    overview.to_csv(OUT_DIR / "asr_change_direction_summary.csv", index=False, encoding="utf-8-sig")

    pair = a.pivot_table(index=["measure_name", "disease"], columns="location_name", values="pct").dropna().reset_index()
    pair["China_minus_US_pp"] = pair["China"] - pair["United States of America"]
    pair.to_csv(OUT_DIR / "china_us_change_contrast.csv", index=False, encoding="utf-8-sig")

    print("QUALITY")
    print("rows", len(a), "duplicates", a.duplicated(["location_name", "measure_name", "disease"]).sum())
    print("endpoint matched", a.computed_pct.notna().sum(), "max abs diff pp", a.abs_recalc_diff_pp.max())
    print("\nOVERVIEW")
    print(overview.to_string(index=False))
    for loc in ["China", "United States of America"]:
        print(f"\n===== {loc} =====")
        for measure in ["Incidence", "Prevalence", "Deaths", "DALYs (Disability-Adjusted Life Years)"]:
            q = a[(a.location_name == loc) & (a.measure_name == measure)].sort_values("pct")
            if q.empty:
                continue
            print(f"\n{measure} largest declines")
            print(q[["disease", "pct", "ci_low", "ci_high", "asr_2023", "direction"]].head(5).to_string(index=False))
            print(f"{measure} largest increases")
            print(q[["disease", "pct", "ci_low", "ci_high", "asr_2023", "direction"]].tail(5).sort_values("pct", ascending=False).to_string(index=False))
    print("\nCHINA-US LARGEST DIVERGENCES")
    print(pair.reindex(pair.China_minus_US_pp.abs().sort_values(ascending=False).index).head(15).to_string(index=False))
    print("\nTOP 2023 ASR BY LOCATION/MEASURE")
    for (loc, measure), q in a.groupby(["location_name", "measure_name"]):
        print(loc, measure)
        print(q.nlargest(5, "asr_2023")[["disease", "asr_2023", "pct"]].to_string(index=False))


if __name__ == "__main__":
    main()
