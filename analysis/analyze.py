"""Single-file QCADesigner-E demultiplexer analysis; no simulator automation."""
import argparse
import csv
from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys
from time import perf_counter

import numpy as np

REQUIRED = {'D', 'S', 'Y0', 'Y1', 'Clock 3'}
CLOCK_LABELS = {f'Clock {i}' for i in range(4)}
CORE_CHILDREN = {'SIMULATION_DATA': {'TRACES', 'CLOCKS'},
                 'TRACES': {'TRACE'}, 'CLOCKS': {'TRACE'},
                 'TRACE': {'TRACE_DATA'}, 'TRACE_DATA': set()}
NUMBER = r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?'
NUMERIC_TEXT = re.compile(rf'\s*(?:{NUMBER}\s+)*{NUMBER}\s*\Z')


class AnalysisError(ValueError):
    """Malformed input or insufficient reliable measurement data."""


@dataclass
class Simulation:
    samples: int
    traces: dict


def parse_simulation_file(path, *, for_plotting=False):
    """Read once; buffer numerical text until labels/counts are known.

    Tags outside simulation data (e.g. bus layout) are structurally checked too.
    All numeric blocks are lexically validated, including ignored clocks.
    for_plotting retains original labels and every clock's values, omits
    circuit-specific requirements, and permits empty data for callers to skip.
    """
    stack, records, metadata = [], [], {}
    current = None
    sections = set()
    with open(path, encoding='utf-8') as source:
        for line_number, raw in enumerate(source, 1):
            line = raw.strip()
            if not line:
                continue
            if line.startswith('['):
                if not line.endswith(']'):
                    raise AnalysisError(f'line {line_number}: malformed tag')
                closing = line.startswith('[#')
                tag = line[2:-1] if closing else line[1:-1]
                if closing:
                    if not stack or stack[-1] != tag:
                        raise AnalysisError(f'line {line_number}: mismatched closing {tag}')
                    if tag == 'TRACE':
                        records.append(current)
                        current = None
                    stack.pop()
                else:
                    parent = stack[-1] if stack else None
                    if not tag or '[' in tag or ']' in tag:
                        raise AnalysisError(f'line {line_number}: malformed tag')
                    if parent in CORE_CHILDREN and tag not in CORE_CHILDREN[parent]:
                        raise AnalysisError(f'line {line_number}: unexpected {tag} inside {parent}')
                    if tag == 'SIMULATION_DATA' and parent not in {None, 'SIMULATION_OUTPUT'}:
                        raise AnalysisError('misplaced SIMULATION_DATA')
                    if tag == 'SIMULATION_OUTPUT' and (parent is not None or tag in sections):
                        raise AnalysisError('misplaced or duplicate SIMULATION_OUTPUT')
                    if tag == 'SIMULATION_OUTPUT':
                        sections.add(tag)
                    if tag in {'SIMULATION_DATA', 'TRACES', 'CLOCKS'}:
                        if tag in sections:
                            raise AnalysisError(f'duplicate section {tag}')
                        sections.add(tag)
                    if tag in {'TRACES', 'CLOCKS'} and parent != 'SIMULATION_DATA':
                        raise AnalysisError(f'{tag} outside SIMULATION_DATA')
                    if tag == 'TRACE':
                        if current is not None or parent not in {'TRACES', 'CLOCKS'}:
                            raise AnalysisError('misplaced TRACE')
                        current = {'text': [], 'fields': {}, 'data_seen': False, 'container': parent}
                    if tag == 'TRACE_DATA':
                        if parent != 'TRACE' or current['data_seen']:
                            raise AnalysisError('misplaced or duplicate TRACE_DATA')
                        current['data_seen'] = True
                    stack.append(tag)
                continue
            if stack and stack[-1] == 'TRACE_DATA':
                current['text'].append(line)
            elif stack and stack[-1] in {'TRACE', 'SIMULATION_DATA'}:
                if '=' not in line:
                    raise AnalysisError(f'line {line_number}: expected metadata')
                key, value = (part.strip() for part in line.split('=', 1))
                target = current['fields'] if stack[-1] == 'TRACE' else metadata
                if key in target:
                    raise AnalysisError(f'duplicate metadata {key}')
                target[key] = value
            elif stack and stack[-1] in {'TRACES', 'CLOCKS'}:
                raise AnalysisError(f'line {line_number}: unexpected content in {stack[-1]}')
    if stack:
        raise AnalysisError(f'unclosed tag {stack[-1]}')
    try:
        samples = int(metadata['number_samples'])
        declared_traces = int(metadata['number_of_traces'])
        if samples < 0 or (samples == 0 and not for_plotting) or declared_traces < 0:
            raise ValueError
    except (KeyError, ValueError):
        raise AnalysisError('missing or invalid number_samples/number_of_traces') from None
    traces = {}
    for record in records:
        label = record['fields'].get('data_labels', '')
        # Simulator exports use CLOCK; retain canonical Clock names downstream.
        if not for_plotting and label in {f'CLOCK {i}' for i in range(4)}:
            label = 'Clock ' + label[-1]
        if not label or label in traces:
            raise AnalysisError(f'missing or duplicate trace label: {label!r}')
        if not for_plotting and (record['container'] == 'CLOCKS') != (label in CLOCK_LABELS):
            raise AnalysisError(f'{label}: misplaced or unrecognized clock label')
        fields = record['fields']
        if ('drawtrace' in fields and fields['drawtrace'] not in {'TRUE', 'FALSE'}
                or 'trace_function' in fields and not re.fullmatch(r'[+-]?[0-9]+', fields['trace_function'])):
            raise AnalysisError(f'{label}: invalid trace metadata')
        text = ' '.join(record['text'])
        if not record['data_seen'] or (not NUMERIC_TEXT.fullmatch(text) and not (for_plotting and not text)):
            raise AnalysisError(f'{label}: missing data or invalid/non-finite numerical token')
        # Full lexical validation prevents fromstring's silent truncation behavior.
        values = np.fromstring(text, sep=' ')
        if len(values) != samples and not (for_plotting and not len(values)):
            raise AnalysisError(f'{label}: expected {samples} samples, got {len(values)}')
        if not np.isfinite(values).all():
            raise AnalysisError(f'{label}: non-finite data')
        traces[label] = values if for_plotting or label not in {'Clock 0', 'Clock 1', 'Clock 2'} else None
    if (sum(r['container'] == 'TRACES' for r in records) != declared_traces
            or (not for_plotting and sum(r['container'] == 'CLOCKS' for r in records) != 4)):
        raise AnalysisError('number_of_traces does not match signal traces plus four clocks')
    missing = REQUIRED - traces.keys()
    if missing and not for_plotting:
        raise AnalysisError(f'missing required traces: {sorted(missing)}')
    return Simulation(samples, traces)


def _runs(mask):
    edges = np.flatnonzero(np.diff(np.r_[False, mask, False]))
    return list(zip(edges[::2].tolist(), edges[1::2].tolist()))


def validate_clock(clock, low=3.8e-23, high=9.8e-22, tolerance=1e-6):
    """Return all low plateaus and diagnostics; completeness requires both edges."""

    if not np.isfinite([low, high, tolerance]).all() or high <= low or not 0 <= tolerance < .25:
        raise AnalysisError('require finite LOW < HIGH and 0 <= clock tolerance < 0.25')
    if not np.isfinite(clock).all():
        raise AnalysisError('Clock 3 contains non-finite samples')

    z = (clock - low) / (high - low)

    # Allow only arithmetic roundoff at the configured inclusive boundaries.
    epsilon = 8 * np.finfo(float).eps
    lows, highs = np.abs(z) <= tolerance + epsilon, np.abs(z - 1) <= tolerance + epsilon
    warnings = []

    def warn(message, start, end):
        warnings.append(f'Clock 3 [{start}, {end}): {message}')

    for start, end in _runs((z < -tolerance - epsilon) | (z > 1 + tolerance + epsilon)):
        warn('outside LOW–HIGH range', start, end)

    if not highs.any():
        warn('missing HIGH plateau', 0, len(z))
    if not lows.any():
        raise AnalysisError('Clock 3: missing LOW plateau; no reliable holds')

    for index in np.flatnonzero((lows[:-1] & highs[1:]) | (highs[:-1] & lows[1:])):
        warn('unexpected phase sequence: missing sampled transition', int(index), int(index) + 2)

    for start, end in _runs(~(lows | highs)):
        left = 'L' if start and lows[start - 1] else 'H' if start else None
        right = 'L' if end < len(z) and lows[end] else 'H' if end < len(z) else None
        direction = -1 if right == 'L' or left == 'H' else 1
        delta = np.diff(z[max(0, start - 1):min(len(z), end + 1)])
        bad = np.flatnonzero(delta * direction < -tolerance)
        for index in bad:
            warn('unexpected spike / non-monotonic transition', max(0, start - 1) + int(index), max(0, start - 1) + int(index) + 2)
        if left is not None and right == left:
            warn('unexpected phase sequence', start, end)

    holds = []
    low_runs = _runs(lows)

    for (_, previous_end), (start, _) in zip(low_runs, low_runs[1:]):
        if not highs[previous_end:start].any():
            raise AnalysisError(f'Clock 3 [{previous_end}, {start}): LOW plateaus without intervening HIGH; ambiguous cycle alignment')

    for index, (start, end) in enumerate(low_runs):
        complete = start > 0 and end < len(z) and z[start - 1] > tolerance + epsilon and z[end] > tolerance + epsilon
        holds.append(dict(hold_index=index, start_sample=start, end_sample=end,
                          sample_count=end - start, complete=bool(complete)))
        if not complete:
            warn('partial hold excluded from alignment', start, end)
        if end - start < 2:
            warn('unusually short hold', start, end)

    lengths = [h['sample_count'] for h in holds if h['complete']]
    starts = [h['start_sample'] for h in holds]

    for values, name in [(lengths, 'hold lengths'), (np.diff(starts), 'periods')]:
        if len(values) > 1 and np.ptp(values) > max(1, .05 * np.median(values)):
            warn(f'inconsistent {name}', 0, len(z))

    if not any(h['complete'] for h in holds) or not highs.any():
        raise AnalysisError('Clock 3: insufficient reliable complete holds/HIGH plateau')

    return holds, warnings


def find_hold_phases(clock, **kwargs):
    return validate_clock(clock, **kwargs)[0]


def polarization_to_logic(value, threshold=.5):
    return 1 if value >= threshold else 0 if value <= -threshold else None


def calculate_statistics(values, threshold=.5):
    mean = float(np.mean(values))
    logic = polarization_to_logic(mean, threshold)
    minimum, maximum = float(np.min(values)), float(np.max(values))
    return dict(minimum=minimum, maximum=maximum, median=float(np.median(values)),
                mean=mean, sample_count=len(values), logical_value=logic,
                stable=bool(minimum >= threshold if logic == 1 else maximum <= -threshold if logic == 0 else False))


def align_traces(holds, delay=1):
    if not isinstance(delay, int) or delay < 0:
        raise AnalysisError('delay must be a nonnegative integer')
    by_index = {h['hold_index']: h for h in holds}
    for hold in holds:
        output = by_index.get(hold['hold_index'] + delay)
        if hold['complete'] and output and output['complete']:
            yield hold, output


def validate_demultiplexer(stats):
    d, s = (stats[label]['logical_value'] for label in ('D', 'S'))
    if d is None or s is None or not all(stats[x]['stable'] for x in ('D', 'S')):
        return 'INVALID_INPUT', None

    expected = {'Y0': d & (1 - s), 'Y1': d & s}

    if any(stats[x]['logical_value'] is None for x in expected):
        return 'UNDEFINED_OUTPUT', expected
    if any(stats[x]['logical_value'] != expected[x] for x in expected):
        return 'WRONG_LOGIC', expected
    if not all(stats[x]['stable'] for x in expected):
        return 'UNSTABLE_OUTPUT', expected
    return 'PASS', expected


def calculate_summary(rows, details):
    combos = {(r['D'], r['S']) for r in rows if r['status'] != 'INVALID_INPUT'}
    correct = sum(all(r['status'] == 'PASS' for r in rows if (r['D'], r['S']) == c) for c in combos)
    outputs = [d for d in details if d['trace_label'] in {'Y0', 'Y1'}]
    signed = [d for d in outputs if d['signed_mean_polarization'] is not None]
    return dict(
            correct_input_combinations=correct, total_input_combinations=len(combos),
            correct_outputs=sum(d['logical_value'] == d['expected_logical_value'] and d['stable'] for d in signed),
            total_outputs=len(outputs), undefined_outputs=sum(d['logical_value'] is None for d in outputs),
            unstable_outputs=sum(not d['stable'] for d in outputs),
            mean_absolute_output_polarization=float(np.mean([abs(d['mean']) for d in outputs])) if outputs else None,
            minimum_signed_mean_polarization=min((d['signed_mean_polarization'] for d in signed), default=None),
            worst_signed_sample_polarization=min((d['worst_signed_polarization'] for d in signed), default=None),
            circuit_passed=len(combos) == 4 and all(r['status'] == 'PASS' for r in rows)
            )


def analyze(simulation, threshold=.5, full=False, delay=1, **clock_options):
    if not np.isfinite(threshold) or not 0 < threshold <= 1:
        raise AnalysisError('threshold must be finite and in (0, 1]')
    holds, warnings = validate_clock(simulation.traces['Clock 3'], **clock_options)
    rows, details, seen = [], [], set()
    labels = [label for label in simulation.traces if not label.startswith('Clock ')]
    for ih, oh in align_traces(holds, delay):
        stats = {}
        for label in labels:
            h = oh if label in {'Y0', 'Y1'} else ih
            stats[label] = calculate_statistics(simulation.traces[label][h['start_sample']:h['end_sample']], threshold)
        status, expected = validate_demultiplexer(stats)
        d, s = stats['D']['logical_value'], stats['S']['logical_value']
        rows.append(dict(input_hold_index=ih['hold_index'], output_hold_index=oh['hold_index'],
                         D=d, S=s, Y0=stats['Y0']['logical_value'], Y1=stats['Y1']['logical_value'], status=status))
        for label, stat in stats.items():
            h = oh if label in {'Y0', 'Y1'} else ih
            exp = expected.get(label) if expected else None
            sign = 2 * exp - 1 if exp is not None else None
            details.append(dict(input_hold_index=ih['hold_index'], trace_label=label,
                                measurement_hold_index=h['hold_index'], start_sample=h['start_sample'],
                                end_sample=h['end_sample'], input_d=d, input_s=s, **stat,
                                expected_logical_value=exp,
                                signed_mean_polarization=sign * stat['mean'] if sign is not None else None,
                                worst_signed_polarization=(stat['minimum'] if sign == 1 else -stat['maximum']) if sign is not None else None,
                                status=status))
        if status == 'INVALID_INPUT':
            warnings.append(f'input hold {ih["hold_index"]}: undefined or unstable inputs')
        elif d is not None and s is not None:
            seen.add((d, s))
        if not full and len(seen) == 4:
            break
    if not rows:
        raise AnalysisError('insufficient complete holds / missing delayed outputs')
    complete = len(seen) == 4
    if not complete:
        warnings.append('INCOMPLETE_DATA: incomplete truth table or missing delayed output measurements')
    summary = calculate_summary(rows, details)
    status = 'INCOMPLETE_DATA' if not complete else 'PASS' if summary['circuit_passed'] else 'FAIL'
    return dict(holds=holds, rows=rows, details=details, warnings=warnings,
                summary=summary, status=status, complete=complete, delay=delay, threshold=threshold)


def export_csv(path, details):
    with open(path, 'w', newline='', encoding='utf-8') as output:
        writer = csv.DictWriter(output, fieldnames=list(details[0]))
        writer.writeheader()
        writer.writerows(details)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('simulation')
    parser.add_argument('--threshold', type=float, default=.5)
    parser.add_argument('--clock-low', type=float, default=3.8e-23)
    parser.add_argument('--clock-high', type=float, default=9.8e-22)
    parser.add_argument('--clock-tolerance', type=float, default=1e-6, help='fraction of HIGH - LOW (default: 1e-6)')
    parser.add_argument('--csv', type=Path)
    parser.add_argument('--json', type=Path)
    parser.add_argument('--full', action='store_true')
    parser.add_argument('--verbose', '--debug', action='store_true')
    args = parser.parse_args(argv)

    try:
        start = perf_counter()
        simulation = parse_simulation_file(args.simulation)
        parsed = perf_counter()
        result = analyze(simulation, args.threshold, args.full, low=args.clock_low, high=args.clock_high, tolerance=args.clock_tolerance)
        analyzed = perf_counter()
        result['timings'] = dict(parsing_seconds=parsed-start, analysis_seconds=analyzed-parsed, total_seconds=analyzed-start)

        for warning in result['warnings']:
            print(f'warning: {warning}', file=sys.stderr)
        print(f'Simulation file: {args.simulation}\nDeclared samples: {simulation.samples}')
        print(f'Complete hold phases: {sum(h["complete"] for h in result["holds"])}\nOutput delay: 1 clock cycle\nPolarization threshold: {args.threshold}')
        print('Input hold | Output hold | D | S | Y0 | Y1 | Status')
        for row in result['rows']:
            print(' | '.join('U' if v is None else str(v) for v in row.values()))
        print('\nDetailed measurements:')
        print('input hold | trace | measurement hold | [start,end) | n | min | max | median | mean | logic | stable | status')
        for d in result['details']:
            print(f'{d["input_hold_index"]} | {d["trace_label"]} | {d["measurement_hold_index"]} | [{d["start_sample"]},{d["end_sample"]}) | {d["sample_count"]} | {d["minimum"]:.6g} | {d["maximum"]:.6g} | {d["median"]:.6g} | {d["mean"]:.6g} | {d["logical_value"] if d["logical_value"] is not None else "U"} | {d["stable"]} | {d["status"]}')
        for key, value in result['summary'].items():
            print(f'{key}: {value}')
        print('Overall result: ' + result['status'])
        if args.csv:
            export_csv(args.csv, result['details'])
        if args.json:
            args.json.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        if args.verbose:
            print(json.dumps(result['timings']), file=sys.stderr)

        return 2 if not result['complete'] else 0 if result['summary']['circuit_passed'] else 1
    except (OSError, UnicodeError, AnalysisError) as error:
        print(f'error: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
