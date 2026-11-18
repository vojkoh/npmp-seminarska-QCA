"""Run with: python -m unittest discover -s visualizations."""
import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import plot_displacements as p

FIELDS = ['case_id', 'cell_id', 'cell_group', 'direction', 'displacement_nm', 'dx_nm',
          'dy_nm', 'original_x_nm', 'original_y_nm', 'new_x_nm', 'new_y_nm', 'status',
          'circuit_path']


def make_run(root, cases):
    """cases: (case_id, cell_id, group, dx, dy, manifest_status, verdict or None)."""
    (root / 'circuits').mkdir(parents=True)
    with (root / 'circuits' / 'manifest.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, FIELDS, restval='')
        writer.writeheader()
        writer.writerow({'case_id': 'baseline', 'status': 'BASELINE'})
        for case_id, cell, group, dx, dy, status, verdict in cases:
            writer.writerow({'case_id': case_id, 'cell_id': cell, 'cell_group': group,
                             'dx_nm': dx, 'dy_nm': dy, 'status': status})
            if verdict:
                out = root / 'results' / case_id
                out.mkdir(parents=True)
                (out / 'full-summary.json').write_text(json.dumps({'status': verdict}))


class DisplacementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'run.test'
        make_run(self.root, [
            ('W1_py_1nm', 'W1', 'wire', 0, 1, 'GENERATED', 'PASS'),
            ('W1_ny_2nm', 'W1', 'wire', 0, -2, 'GENERATED', 'FAIL'),
            ('W2_py_1nm', 'W2', 'wire', 0, 1, 'GENERATED', None),
            ('N1_px_1nm', 'N1', 'inverter', 1, 0, 'GENERATED', 'PASS'),
            ('M0a_px_1nm', 'M0a', 'majority', 1, 0, 'GENERATED', 'FAIL'),
            ('M1b_ny_3nm', 'M1b', 'majority', 0, -3, 'OVERLAP', None),
            ('M1a_py_5nm', 'M1a', 'majority', 0, 5, 'GENERATED', 'PASS'),
        ])

    def tearDown(self):
        self.tmp.cleanup()

    def test_load_skips_overlap_and_missing(self):
        with patch('sys.stderr'):
            cells = p.load_runs(self.root)
        self.assertEqual(list(cells), ['W1', 'N1', 'M0a', 'M1a'])
        self.assertEqual(cells['W1'][1], [(0, 1, True), (0, -2, False)])
        self.assertEqual([k for k, _ in p.layout(cells)], ['wire', 'inverter', 'M0', 'M1'])

    def test_figure_colors_and_shared_limits(self):
        with patch('sys.stderr'):
            figure = p.build_figure(p.load_runs(self.root))
        try:
            visible = [a for a in figure.axes if a.get_visible()]
            self.assertEqual(len(visible), 4)
            w1 = visible[0]
            self.assertTrue(w1.get_title().startswith('W1  (1/2 pravilnih)'))
            colors = [tuple(c.get_facecolor()[0][:3]) for c in w1.collections]
            self.assertEqual(colors, [matplotlib_rgb(p.PASS_COLOR), matplotlib_rgb(p.FAIL_COLOR)])
            for axis in visible:
                self.assertEqual(axis.get_xlim(), w1.get_xlim())
                ylo, yhi = axis.get_ylim()
                self.assertGreater(ylo, yhi)  # inverted: +y down
        finally:
            p.plt.close(figure)

    def test_main_saves_png(self):
        out = Path(self.tmp.name) / 'overview.png'
        with patch('sys.stderr'), patch('sys.stdout'):
            self.assertEqual(p.main([str(self.root), '-o', str(out)]), 0)
        self.assertGreater(out.stat().st_size, 0)
        self.assertEqual(p.plt.get_fignums(), [])

    def test_missing_manifest_fails(self):
        with patch('sys.stderr'):
            self.assertEqual(p.main([str(Path(self.tmp.name) / 'nope')]), 1)


def matplotlib_rgb(color):
    from matplotlib.colors import to_rgb
    return to_rgb(color)


if __name__ == '__main__':
    unittest.main()
