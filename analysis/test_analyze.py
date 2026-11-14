"""Synthetic writer-format fixtures, not baseline simulation verification."""
import contextlib
import io
import csv
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import analyze as a


def fixture(combinations=None, width=4):
    combinations = combinations or [(0, 0), (0, 1), (1, 0), (1, 1), (0, 0)]
    period = np.r_[1., .7, .3, np.zeros(width), .3, .7, 1.]
    n = len(period)
    clock = np.tile(period, len(combinations)) * (9.8e-22 - 3.8e-23) + 3.8e-23
    traces = {'D': [], 'S': [], 'Y0': [], 'Y1': []}
    for index, (d, s) in enumerate(combinations):
        pd, ps = combinations[index - 1] if index else (0, 0)
        for label, bit in zip(traces, [d, s, pd & (1 - ps), pd & ps]):
            traces[label].extend([.95 if bit else -.95] * n)
    traces = {k: np.array(v) for k, v in traces.items()}
    traces.update({f'Clock {i}': clock.copy() for i in range(4)})
    return a.Simulation(len(clock), traces)


def serialize(sim, late=False):
    def trace(label):
        fields = f'data_labels={label}\ntrace_function=0\ndrawtrace=TRUE\n'
        data = '[TRACE_DATA]\n' + ' '.join(f'{v:.9e}' for v in sim.traces[label]) + '\n[#TRACE_DATA]\n'
        return '[TRACE]\n' + (data + fields if late else fields + data) + '[#TRACE]\n'
    metadata = f'number_samples={sim.samples}\nnumber_of_traces={len(sim.traces)-4}\n'
    clocks = '[CLOCKS]\n' + ''.join(trace(f'Clock {i}') for i in [3, 1, 0, 2]) + '[#CLOCKS]\n'
    signals = '[TRACES]\n' + ''.join(trace(k) for k in reversed(list(sim.traces)) if not k.startswith('Clock ')) + '[#TRACES]\n'
    return '[SIMULATION_OUTPUT]\n[SIMULATION_DATA]\n' + (clocks + signals + metadata if late else metadata + signals + clocks) + '[#SIMULATION_DATA]\n[#SIMULATION_OUTPUT]\n'


class AnalyzerTests(unittest.TestCase):
    def parse(self, text):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory) / 'simulation.txt'
            path.write_text(text)
            return a.parse_simulation_file(path)

    def test_01_correct_delayed_demux(self):
        result = a.analyze(self.parse(serialize(fixture())))
        self.assertTrue(result['summary']['circuit_passed'])
        self.assertEqual([(r['input_hold_index'], r['output_hold_index']) for r in result['rows']], [(0, 1), (1, 2), (2, 3), (3, 4)])

    def test_02_wrong(self):
        sim = fixture(); sim.traces['Y0'][13:17] = .95
        self.assertEqual(a.analyze(sim)['rows'][0]['status'], 'WRONG_LOGIC')

    def test_03_undefined(self):
        sim = fixture(); sim.traces['Y0'][13:17] = 0
        self.assertEqual(a.analyze(sim)['rows'][0]['status'], 'UNDEFINED_OUTPUT')

    def test_04_unstable(self):
        sim = fixture(); sim.traces['Y0'][13] = .1
        result = a.analyze(sim)
        self.assertEqual(result['rows'][0]['status'], 'UNSTABLE_OUTPUT')
        self.assertAlmostEqual(result['summary']['worst_signed_sample_polarization'], -.1)

    def test_05_monotonic(self):
        holds, warnings = a.validate_clock(fixture().traces['Clock 3'])
        self.assertEqual(warnings, [])
        self.assertEqual((holds[0]['start_sample'], holds[0]['end_sample']), (3, 7))

    def test_06_spike(self):
        sim = fixture(); sim.traces['Clock 3'][2] = 9e-22
        self.assertTrue(any('spike' in x for x in a.validate_clock(sim.traces['Clock 3'])[1]))

    def test_07_partial_start(self):
        sim = fixture()
        sim.traces = {k: v[4:] for k, v in sim.traces.items()}
        holds, warnings = a.validate_clock(sim.traces['Clock 3'])
        self.assertFalse(holds[0]['complete'])
        self.assertEqual(next(a.align_traces(holds))[0]['hold_index'], 1)
        self.assertTrue(any('partial' in w for w in warnings))

    def test_08_missing_delayed(self):
        sim = fixture([(0, 0), (0, 1), (1, 0), (1, 1)])
        result = a.analyze(sim)
        self.assertFalse(result['complete'])
        self.assertEqual(len(result['rows']), 3)

    def test_09_short_and_extra(self):
        sim = fixture()
        for delta in [-1, 1]:
            text = serialize(sim).replace(f'number_samples={sim.samples}', f'number_samples={sim.samples+delta}')
            with self.assertRaises(a.AnalysisError): self.parse(text)

    def test_10_tags(self):
        text = serialize(fixture())
        for bad in [text.replace('[#TRACE_DATA]', '[#TRACE]', 1), text.replace('[#SIMULATION_OUTPUT]', '')]:
            with self.assertRaises(a.AnalysisError): self.parse(bad)

    def test_11_tiny_clock(self):
        holds = a.find_hold_phases(fixture().traces['Clock 3'])
        self.assertEqual(len(holds), 5)
        self.assertTrue(all(h['sample_count'] == 4 for h in holds))

    def test_12_repeats(self):
        result = a.analyze(fixture([(0, 0), (0, 0), (0, 1), (1, 0), (1, 1), (0, 0)]))
        self.assertEqual(len(result['rows']), 5)
        self.assertTrue(result['summary']['circuit_passed'])

    def test_13_two_tables(self):
        sim = fixture([(0, 0), (0, 1), (1, 0), (1, 1)] * 2 + [(0, 0)])
        self.assertEqual(len(a.analyze(sim)['rows']), 4)
        self.assertEqual(len(a.analyze(sim, full=True)['rows']), 8)

    def test_order_and_bad_numbers(self):
        text = serialize(fixture(), late=True)
        self.assertTrue(a.analyze(self.parse(text))['summary']['circuit_passed'])
        for token in ['1.0junk', 'NaN', 'inf', '1e999']:
            with self.assertRaises(a.AnalysisError): self.parse(text.replace('-9.500000000e-01', token, 1))

    def test_duplicates_missing_count_and_trace(self):
        text = serialize(fixture())
        for bad in [text.replace('data_labels=D', 'data_labels=S'), text.replace('number_samples=50', 'bad=50'), text.replace('data_labels=D', 'data_labels=X')]:
            with self.assertRaises(a.AnalysisError): self.parse(bad)

    def test_signed_metrics_and_unknown_no_delay(self):
        sim = fixture(); sim.traces['extra'] = sim.traces['D'].copy()
        result = a.analyze(sim)
        self.assertAlmostEqual(result['summary']['minimum_signed_mean_polarization'], .95)
        self.assertTrue(all(d['measurement_hold_index'] == d['input_hold_index'] for d in result['details'] if d['trace_label'] == 'extra'))

    def test_cycle_gaps_preserved(self):
        holds = [dict(hold_index=i, complete=valid) for i, valid in [(0, True), (1, False), (2, True), (3, True)]]
        self.assertEqual([(x['hold_index'], y['hold_index']) for x, y in a.align_traces(holds)], [(2, 3)])

    def test_cli_exports_and_exits(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory) / 'sim.txt'; path.write_text(serialize(fixture()))
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(a.main([str(path), '--csv', str(path)+'.csv', '--json', str(path)+'.json']), 0)
                self.assertEqual(a.main([str(path), '--threshold', 'nan']), 2)
                sim = fixture(); sim.traces['Y0'][13:17] = .95
                path.write_text(serialize(sim))
                self.assertEqual(a.main([str(path)]), 1)

    def test_nested_content_cannot_hide_invalid_samples(self):
        text = serialize(fixture())
        bad_inputs = [
            text.replace('[TRACE_DATA]', '[TRACE_DATA]\n[HIDDEN]\nNaN\n[#HIDDEN]', 1),
            text.replace('[TRACE]', '[HIDDEN]\n[#HIDDEN]\n[TRACE]', 1),
            text.replace('[SIMULATION_DATA]', '[BUS_LAYOUT]\n[SIMULATION_DATA]', 1)
                .replace('[#SIMULATION_DATA]', '[#SIMULATION_DATA]\n[#BUS_LAYOUT]', 1),
            text.replace('[TRACES]', '[TRACES]\nNaN', 1),
            text.replace('drawtrace=TRUE', 'drawtrace=maybe', 1),
            text.replace('trace_function=0', 'trace_function=NaN', 1),
        ]
        for text in bad_inputs:
            with self.subTest(text=text[:100]), self.assertRaises(a.AnalysisError):
                self.parse(text)

    def test_uppercase_clock_labels(self):
        for late in [False, True]:
            with self.subTest(late=late):
                text = serialize(fixture(), late=late).replace('data_labels=Clock ', 'data_labels=CLOCK ')
                sim = self.parse(text)
                self.assertTrue(a.CLOCK_LABELS <= sim.traces.keys())
                self.assertIsNone(sim.traces['Clock 0'])
                self.assertTrue(a.analyze(sim)['summary']['circuit_passed'])

    def test_clock_aliases_preserve_validation(self):
        text = serialize(fixture())
        for bad in [text.replace('data_labels=Clock 0', 'data_labels=CLOCK 3'),
                    text.replace('data_labels=Clock 0', 'data_labels=CLOCK 4'),
                    text.replace('data_labels=D', 'data_labels=CLOCK 0')]:
            with self.subTest(text=bad[:100]), self.assertRaises(a.AnalysisError):
                self.parse(bad)

    def test_clock_container_labels_are_not_interchangeable(self):
        text = serialize(fixture())
        for bad in [text.replace('data_labels=Clock 0', 'data_labels=other'),
                    text.replace('data_labels=Clock 3', 'data_labels=temp')
                        .replace('data_labels=D', 'data_labels=Clock 3')
                        .replace('data_labels=temp', 'data_labels=D')]:
            with self.assertRaises(a.AnalysisError):
                self.parse(bad)

    def test_low_spike_does_not_create_false_cycle(self):
        sim = fixture()
        sim.traces['Clock 3'][5] += .1 * (9.8e-22 - 3.8e-23)
        with self.assertRaisesRegex(a.AnalysisError, 'ambiguous cycle alignment'):
            a.analyze(sim)

    def test_amplitude_tolerance_and_inclusive_boundaries(self):
        low, high, tolerance = 3.8e-23, 9.8e-22, 1e-6
        sim = fixture()
        clock = sim.traces['Clock 3']
        clock[3] = low - tolerance * (high - low)
        clock[6] = low + tolerance * (high - low)
        holds, warnings = a.validate_clock(clock)
        self.assertEqual((holds[0]['start_sample'], holds[0]['end_sample']), (3, 7))
        self.assertEqual(warnings, [])
        clock[3] = low + 2 * tolerance * (high - low)
        self.assertEqual(a.find_hold_phases(clock)[0]['start_sample'], 4)
        with self.assertRaises(a.AnalysisError):
            a.validate_clock(np.ones(20) * 9.8e-22)

    def test_partial_end_excluded_without_renumbering(self):
        sim = fixture()
        sim.traces = {k: v[:-5] for k, v in sim.traces.items()}
        result = a.analyze(sim)
        self.assertFalse(result['holds'][-1]['complete'])
        self.assertEqual(len(result['rows']), 3)
        self.assertEqual(result['status'], 'INCOMPLETE_DATA')

    def test_repeated_failure_cannot_be_overwritten_by_pass(self):
        sim = fixture([(0, 0), (0, 0), (0, 1), (1, 0), (1, 1), (0, 0)])
        sim.traces['Y0'][13:17] = .95
        result = a.analyze(sim)
        self.assertEqual(len(result['rows']), 5)
        self.assertEqual(result['summary']['correct_input_combinations'], 3)
        self.assertEqual(result['summary']['correct_outputs'], 9)
        self.assertEqual(result['summary']['total_outputs'], 10)
        self.assertAlmostEqual(result['summary']['minimum_signed_mean_polarization'], -.95)
        self.assertEqual(result['status'], 'FAIL')

    def test_invalid_input_does_not_establish_coverage_or_expected_outputs(self):
        sim = fixture()
        sim.traces['D'][3] = .1
        result = a.analyze(sim)
        self.assertEqual(result['rows'][0]['status'], 'INVALID_INPUT')
        self.assertEqual(result['summary']['total_input_combinations'], 3)
        self.assertEqual(result['summary']['correct_outputs'], 6)
        self.assertEqual(result['summary']['total_outputs'], 8)
        self.assertTrue(all(d['expected_logical_value'] is None for d in result['details']
                            if d['input_hold_index'] == 0))

    def test_machine_exports_and_incomplete_exit(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory) / 'sim.txt'
            jp, cp = Path(directory) / 'out.json', Path(directory) / 'out.csv'
            for sim, status, code in [(fixture(), 'PASS', 0),
                    (fixture([(0, 0), (0, 1), (1, 0), (1, 1)]), 'INCOMPLETE_DATA', 2)]:
                path.write_text(serialize(sim, late=True))
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(a.main([str(path), '--json', str(jp), '--csv', str(cp)]), code)
                result = json.loads(jp.read_text())
                self.assertEqual(result['status'], status)
                with cp.open(newline='') as source:
                    rows = list(csv.DictReader(source))
                self.assertEqual(len(rows), len(result['details']))
                self.assertEqual(int(rows[0]['start_sample']), result['details'][0]['start_sample'])

    def test_exact_threshold_and_status_precedence(self):
        self.assertTrue(a.calculate_statistics(np.array([-.5, -.5]))['stable'])
        self.assertTrue(a.calculate_statistics(np.array([.5, .5]))['stable'])
        stats = {k: a.calculate_statistics(np.array([-.95])) for k in ['D', 'S', 'Y0', 'Y1']}
        stats['Y0'] = a.calculate_statistics(np.array([.95]))
        stats['Y1'] = a.calculate_statistics(np.array([0.]))
        self.assertEqual(a.validate_demultiplexer(stats)[0], 'UNDEFINED_OUTPUT')

    def test_writer_precision_multiline_and_bus_layout(self):
        text = serialize(fixture(), late=True)
        text = text.replace('9.500000000e-01', '9.500000e-01')
        text = text.replace(' ', '\t')  # Restore spaces in clock labels only.
        text = text.replace('Clock\t', 'Clock ')
        text = text.replace('[#SIMULATION_OUTPUT]', '[BUS_LAYOUT]\n[BUS]\nname=test\n[#BUS]\n[#BUS_LAYOUT]\n[#SIMULATION_OUTPUT]')
        self.assertTrue(a.analyze(self.parse(text))['summary']['circuit_passed'])


if __name__ == '__main__':
    unittest.main()
