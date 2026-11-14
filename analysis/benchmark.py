"""Reproducible synthetic benchmark, NOT a verified simulator baseline."""
from pathlib import Path
import tempfile
from time import perf_counter

import analyze
from test_analyze import fixture, serialize


def main():
    # Nine cycles, 12,807 samples, eight traces; two exhaustive tables + drain.
    simulation = fixture([(0, 0), (0, 1), (1, 0), (1, 1)] * 2 + [(0, 0)], width=1417)
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
        path = Path(directory) / 'synthetic.txt'
        path.write_text(serialize(simulation))
        times = []
        for _ in range(10):
            start = perf_counter()
            sim = analyze.parse_simulation_file(path)
            parsed = perf_counter()
            result = analyze.analyze(sim)
            end = perf_counter()
            assert result['summary']['circuit_passed']
            times.append((parsed-start, end-parsed, end-start))
        print(f'SYNTHETIC ONLY: {simulation.samples} samples, 8 traces, {path.stat().st_size} bytes, 10 runs')
        for column, name in enumerate(['parse', 'analysis', 'total']):
            values = sorted(t[column] for t in times)
            print(f'{name}: median={(values[4]+values[5])/2:.6f}s min={min(values):.6f}s max={max(values):.6f}s')


if __name__ == '__main__':
    main()
