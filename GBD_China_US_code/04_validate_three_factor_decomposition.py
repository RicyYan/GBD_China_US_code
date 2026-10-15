from __future__ import annotations

import itertools
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "inputs"
OUT = ROOT / "outputs"
AGES = [
    "<5 years", "5-9 years", "10-14 years", "15-19 years",
    "20-24 years", "25-29 years", "30-34 years", "35-39 years",
    "40-44 years", "45-49 years", "50-54 years", "55-59 years",
    "60-64 years", "65-69 years", "70-74 years", "75-79 years",
    "80-84 years", "85-89 years", "90-94 years", "95+ years",
]


def shapley_three_factor(a1, a2, p1, p2, r1, r2):
    factors = ("aging", "population", "epidemiological")
    values = {f: 0.0 for f in factors}

    def burden(state):
        a = a2 if state["aging"] else a1
        p = p2 if state["population"] else p1
        r = r2 if state["epidemiological"] else r1
        return float(np.sum(a * p * r))

    for order in itertools.permutations(factors):
        state = {f: False for f in factors}
        before = burden(state)
        for f in order:
            state[f] = True
            after = burden(state)
            values[f] += after - before
            before = after
    return {f: v / 6 for f, v in values.items()}


def sample_check(location, measure, cause, file_name):
    pop = pd.read_csv(INPUT / "population.csv")
    dis = pd.read_csv(INPUT / file_name)
    pop = pop[(pop.location_name == location) & (pop.sex_name == "Both") & pop.age_name.isin(AGES)]
    rate = dis[(dis.location_name == location) & (dis.sex_name == "Both") & (dis.cause_name == cause) & (dis.metric_name == "Rate") & dis.age_name.isin(AGES)]

    def ordered(df, year, value):
        x = df[df.year == year].set_index("age_name")
        return x.loc[AGES, value].to_numpy(float)

    n1, n2 = ordered(pop, 1990, "val"), ordered(pop, 2023, "val")
    a1, a2 = n1 / n1.sum(), n2 / n2.sum()
    r1, r2 = ordered(rate, 1990, "val") / 1e5, ordered(rate, 2023, "val") / 1e5
    calc = shapley_three_factor(a1, a2, n1.sum(), n2.sum(), r1, r2)

    main = pd.read_csv(OUT / "decomposition_main.csv")
    row = main[(main.location_name == location) & (main.measure == measure) & (main.cause_name == cause)].iloc[0]
    expected = {
        "aging": row.aging_effect,
        "population": row.population_effect,
        "epidemiological": row.epidemiological_effect,
    }
    for key in calc:
        if not np.isclose(calc[key], expected[key], rtol=1e-10, atol=1e-6):
            raise AssertionError(f"{location} {measure} {cause}: {key} differs: {calc[key]} vs {expected[key]}")


qa = pd.read_csv(OUT / "quality_checks.csv")
if not qa.passed.astype(str).str.lower().eq("true").all():
    raise AssertionError("quality_checks.csv contains failures")

main = pd.read_csv(OUT / "decomposition_main.csv")
age = pd.read_csv(OUT / "decomposition_age_band_contributions.csv")
if len(main) != 80:
    raise AssertionError(f"Expected 80 main rows, found {len(main)}")
if len(age) != 1440:
    raise AssertionError(f"Expected 1440 age contribution rows, found {len(age)}")

sample_check("China", "Prevalence", "Alzheimer's disease and other dementias", "china pre.csv")
sample_check("United States of America", "DALYs", "Ischemic stroke", "US DALY.csv")

print("Independent Shapley checks passed for China prevalence and US DALYs samples")
print(f"Validated {len(main)} main rows, {len(age)} age rows, and {len(qa)} QA checks")
