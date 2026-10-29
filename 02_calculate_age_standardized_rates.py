from argparse import ArgumentParser
from pathlib import Path
import pandas as pd

AGE_GROUPS = {
    'younger than 5 years': ['<28 days', '1-5 months', '6-11 months', '12-23 months', '2-4 years'],
    '5-19 years': ['5-9 years', '10-14 years', '15-19 years'],
    '20-59 years': [f'{a}-{a+4} years' for a in range(20, 60, 5)],
    '60-79 years': [f'{a}-{a+4} years' for a in range(60, 80, 5)],
    '80 years or older': ['80-84 years', '85-89 years', '90-94 years', '95+ years'],
}


def population_weights(paths, start, end):
    population = pd.concat([pd.read_csv(p) for p in paths], ignore_index=True)
    population = population.loc[
        population.location_name.eq('Global') & population.sex_name.eq('Both')
        & population.year.between(start, end)
    ]
    if 'metric_name' in population:
        population = population[population.metric_name.eq('Number')]
    frames = []
    for group, ages in AGE_GROUPS.items():
        part = population[population.age_name.isin(ages)]
        if part.duplicated(['age_name', 'year']).any() or len(part) != len(ages) * (end-start+1):
            raise ValueError(f'Incomplete or duplicate population data: {group}')
        if part.val.isna().any() or (part.val < 0).any():
            raise ValueError('Invalid population estimates')
        weights = part.groupby('age_name', as_index=False).val.sum()
        if weights.val.sum() <= 0:
            raise ValueError('Zero population total')
        weights['weight'] = weights.val / weights.val.sum()
        weights['age_group'] = group
        frames.append(weights[['age_name', 'age_group', 'weight']])
    return pd.concat(frames, ignore_index=True)


def main():
    parser = ArgumentParser()
    parser.add_argument('--input', nargs='+', required=True)
    parser.add_argument('--population', nargs='+', required=True)
    parser.add_argument('--start-year', type=int, default=1990)
    parser.add_argument('--end-year', type=int, default=2023)
    parser.add_argument('--output', default='outputs/standardized_rates.csv')
    args = parser.parse_args()
    weights = population_weights(args.population, args.start_year, args.end_year)
    if weights.age_name.duplicated().any() or weights.weight.isna().any() or (weights.weight < 0).any():
        raise ValueError('Invalid standard weights')
    total = weights.groupby('age_group').weight.transform('sum')
    if (total <= 0).any():
        raise ValueError('Age-band weights must sum to a positive value')
    weights['weight'] /= total
    frames = []
    for path in args.input:
        d = pd.read_csv(path)
        d['disease'] = d['rei_name'].fillna(d.cause_name) if 'rei_name' in d else d.cause_name
        frames.append(d[d.metric_name.eq('Rate') & d.age_name.isin(weights.age_name)
                        & d.year.between(args.start_year, args.end_year)])
    data = pd.concat(frames, ignore_index=True)
    keys = ['location_name', 'sex_name', 'measure_name', 'disease', 'year']
    if data.duplicated(keys + ['age_name']).any():
        raise ValueError('Duplicate age-specific rates')
    data = data.merge(weights, on='age_name', validate='many_to_one')
    counts = data.groupby(keys + ['age_group'], dropna=False).size()
    expected = counts.index.get_level_values('age_group').map(weights.groupby('age_group').size())
    if (counts.to_numpy() != expected.to_numpy()).any():
        raise ValueError('Incomplete age-band coverage')
    if data[['val', 'lower', 'upper']].isna().any().any():
        raise ValueError('Missing estimates')
    for col in ['val', 'lower', 'upper']:
        data[col] *= data.weight
    result = data.groupby(keys + ['age_group'], as_index=False, dropna=False)[['val', 'lower', 'upper']].sum()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output, index=False)
    weights.to_csv(output.with_name(output.stem + '_weights.csv'), index=False)


if __name__ == '__main__':
    main()
