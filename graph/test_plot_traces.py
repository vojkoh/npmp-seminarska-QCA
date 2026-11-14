"""Run with: python -m unittest discover -s graph."""
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import plot_traces as p


class PlotTests(unittest.TestCase):
    def test_view_real_file_without_writing(self):
        source = Path(__file__).resolve().parents[1] / 'qca-files/demux12-results'

        def inspect_window(*, block):
            self.assertTrue(block)
            axes = p.plt.gcf().axes
            self.assertEqual(len(axes), len(expected))
            self.assertEqual([a.get_ylabel() for a in axes],
                             expected)
            self.assertEqual(list(p.plt.gcf().get_size_inches()), [10, 2.5 * len(expected)])
            for axis in axes:
                grid = axis.get_subplotspec().get_gridspec()
                self.assertEqual((grid.nrows, grid.ncols), (len(expected), 1))
                self.assertEqual(axis.get_xlabel(), 'Sample index')
                self.assertEqual(axis.get_title(), '')
                self.assertEqual(axis.yaxis.label.get_rotation(), 0)
                if not axis.get_ylabel().startswith('CLOCK '):
                    self.assertEqual(axis.get_ylim(), (-1.1, 1.1))
                    self.assertEqual(len(axis.lines), 2)
                    self.assertEqual(list(axis.lines[1].get_ydata()), [0, 0])
                    self.assertLessEqual(axis.lines[1].get_alpha(), 0.3)
                else:
                    self.assertEqual(len(axis.lines), 1)
                self.assertEqual(len(axis.lines[0].get_xdata()), 12800)
                self.assertEqual(axis.lines[0].get_xdata()[0], 0)
                self.assertEqual(axis.lines[0].get_xdata()[-1], 12799)

        for include in (False, True):
            expected = ['D', 'S', 'Y1', 'Y0'] + (
                [f'CLOCK {i}' for i in range(4)] if include else ['CLOCK 3'])
            with self.subTest(include=include), patch.object(p, 'interactive_backend'), patch.object(
                    p.plt, 'show', side_effect=inspect_window) as show, patch.object(
                    Path, 'mkdir', side_effect=AssertionError('must not create directories')), patch(
                    'matplotlib.figure.Figure.savefig',
                    side_effect=AssertionError('must not save images')):
                flags = ['--include-clocks'] if include else []
                self.assertEqual(p.main([str(source), '--view', *flags]), 0)
                show.assert_called_once_with(block=True)
        self.assertEqual(p.plt.get_fignums(), [])

    def test_single_and_no_eligible_view(self):
        simulation = SimpleNamespace(traces={'CLOCK 0': [1], 'only': [2]})

        def inspect_window(**kwargs):
            axes = p.plt.gcf().axes
            self.assertEqual(len(axes), 1)
            self.assertEqual(axes[0].get_ylabel(), 'only')
            self.assertEqual(axes[0].get_subplotspec().get_gridspec().ncols, 1)

        with patch.object(p, 'interactive_backend'), patch.object(
                p.plt, 'show', side_effect=inspect_window):
            p.view_traces(simulation)
        simulation.traces.pop('only')
        with patch.object(p, 'interactive_backend') as backend, patch.object(p.plt, 'show') as show:
            p.view_traces(simulation)
            backend.assert_not_called()
            show.assert_not_called()
        self.assertEqual(p.plt.get_fignums(), [])

    def test_selection_preserves_other_names_and_order(self):
        simulation = SimpleNamespace(traces={name: [1] for name in
            ['Clock 0', 'CLOCK 1', 'Clock 2', 'Clock 3', 'CLOCK 4', 'D', 'Clock 10']})
        self.assertEqual([name for name, _ in p.selected_traces(simulation)],
                         ['Clock 3', 'CLOCK 4', 'D', 'Clock 10'])
        self.assertEqual([name for name, _ in p.selected_traces(simulation, True)],
                         list(simulation.traces))

    def test_view_empty_and_backend_failure(self):
        empty = SimpleNamespace(traces={'empty': []})
        with patch.object(p, 'interactive_backend') as backend, patch.object(p.plt, 'show') as show:
            p.view_traces(empty)
            backend.assert_not_called()
            show.assert_not_called()
        with patch.dict(p.os.environ, {'MPLBACKEND': 'Agg'}):
            with self.assertRaisesRegex(ValueError, 'interactive view unavailable'):
                p.interactive_backend()
        source = Path(__file__).resolve().parents[1] / 'qca-files/demux12-results'
        with patch.object(p, 'interactive_backend', side_effect=ValueError('no GUI')):
            self.assertEqual(p.main([str(source), '--view']), 1)
        with self.assertRaises(SystemExit) as error:
            p.main([str(source), '--view', '-o', 'unused'])
        self.assertEqual(error.exception.code, 2)

    def test_safe_unique_names(self):
        names = [p.trace_filename(i, name) for i, name in enumerate(
            ['../a/b', 'a?b', '', 'CON', 'x' * 300])]
        self.assertEqual(len(set(names)), 5)
        for name in names:
            self.assertEqual(Path(name).name, name)
            self.assertLess(len(name), 120)

    def test_real_file(self):
        source = Path(__file__).resolve().parents[1] / 'qca-files/demux12-results'
        simulation = p.parse_simulation_file(source, for_plotting=True)
        self.assertEqual(len(simulation.traces), 8)
        self.assertIn('CLOCK 0', simulation.traces)
        self.assertTrue(all(len(v) == 12800 for v in simulation.traces.values()))
        for include in (False, True):
            with self.subTest(include=include), tempfile.TemporaryDirectory() as directory:
                output = Path(directory)
                flags = ['--include-clocks'] if include else []
                self.assertEqual(p.main([str(source), '-o', str(output), *flags]), 0)
                paths = sorted(output.glob('*.png'))
                expected = ['D', 'S', 'Y1', 'Y0'] + (
                    [f'CLOCK {i}' for i in range(4)] if include else ['CLOCK 3'])
                self.assertEqual([path.name for path in paths],
                                 [p.trace_filename(i, name) for i, name in enumerate(expected)])
                for path in paths:
                    self.assertEqual(path.read_bytes()[:8], b'\x89PNG\r\n\x1a\n')
        self.assertEqual(p.plt.get_fignums(), [])

    def test_axes_and_samples(self):
        simulation = p.parse_simulation_file(
            Path(__file__).resolve().parents[1] / 'qca-files/demux12-results',
            for_plotting=True)
        simulation.traces = {'test': simulation.traces['D'][:3]}
        figure, axis = p.plt.subplots()
        with tempfile.TemporaryDirectory() as directory, patch.object(
                p.plt, 'subplots', return_value=(figure, axis)):
            p.plot_traces(simulation, Path(directory))
        self.assertEqual(axis.get_xlabel(), 'Sample index')
        self.assertEqual(axis.get_ylabel(), 'test')
        self.assertEqual(axis.yaxis.label.get_rotation(), 0)
        self.assertEqual(axis.get_title(), '')
        self.assertEqual(axis.get_ylim(), (-1.1, 1.1))
        self.assertEqual(list(axis.lines[1].get_ydata()), [0, 0])
        self.assertEqual(list(axis.lines[0].get_xdata()), [0, 1, 2])
        self.assertEqual(list(axis.lines[0].get_ydata()), [-1, -1, -1])

    def test_clock_limits_not_fixed(self):
        for name in ('CLOCK 0', 'Clock 3'):
            figure, axis = p.plt.subplots()
            try:
                axis.plot([0, 1], [1e-23, 1e-22])
                p.label_axis(axis, name)
                self.assertNotEqual(axis.get_ylim(), (-1.1, 1.1))
                self.assertEqual(len(axis.lines), 1)
                self.assertEqual(axis.get_ylabel(), name)
                self.assertEqual(axis.yaxis.label.get_rotation(), 0)
                self.assertEqual(axis.get_title(), '')
            finally:
                p.plt.close(figure)

    def test_empty_and_invalid(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'save'
            source.write_text('[SIMULATION_DATA]\nnumber_samples=0\nnumber_of_traces=1\n'
                              '[TRACES]\n[TRACE]\ndata_labels=empty\n[TRACE_DATA]\n'
                              '[#TRACE_DATA]\n[#TRACE]\n[#TRACES]\n[#SIMULATION_DATA]\n')
            self.assertEqual(p.main([str(source)]), 0)
            text = source.read_text().replace('number_samples=0', 'number_samples=1')
            source.write_text(text.replace('[TRACE_DATA]', '[TRACE_DATA]\nNaN'))
            self.assertEqual(p.main([str(source)]), 1)
            source.write_text(text.replace('[TRACE_DATA]', '[TRACE_DATA]\n1'))
            blocked = Path(directory) / 'blocked'
            blocked.write_text('not a directory')
            self.assertEqual(p.main([str(source), '-o', str(blocked)]), 1)
            source.write_text('invalid')
            self.assertEqual(p.main([str(source)]), 1)
            self.assertEqual(p.main([str(source.with_name('missing'))]), 1)


if __name__ == '__main__':
    unittest.main()
