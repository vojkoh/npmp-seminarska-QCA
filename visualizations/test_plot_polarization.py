"""Run with: python -m unittest discover -s visualizations."""
import csv
from pathlib import Path
import tempfile
import unittest

import plot_polarization as p

FIELDS = ['input_hold_index', 'trace_label', 'mean']


def write_measurements(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, FIELDS)
        writer.writeheader()
        for index, (label, mean) in enumerate(rows):
            writer.writerow({'input_hold_index': index, 'trace_label': label, 'mean': mean})


class PolarizationTests(unittest.TestCase):
    cells = {'W1': ('wire', [(0, 1, {'Y0': 0.95, 'Y1': 0.80})])}
    baseline = {'Y0': 0.95, 'Y1': 0.95}

    def test_weakest_window_uses_absolute_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'm.csv'
            write_measurements(path, [('D', 1), ('Y0', -0.95), ('Y0', 0.80),
                                      ('Y1', -0.70), ('Y1', 0.95)])
            self.assertEqual(p.weakest_outputs(path), {'Y0': 0.80, 'Y1': 0.70})

    def test_both_outputs_share_one_scale(self):
        norm = p.shared_norm(self.cells, self.baseline)
        self.assertEqual((norm.vmin, norm.vmax), (0.80, 0.95))

    def test_one_circle_series_per_output(self):
        norm = p.shared_norm(self.cells, self.baseline)
        for output, expected in (('Y0', [0.95, 0.95]), ('Y1', [0.80, 0.95])):
            figure = p.build_figure(self.cells, output, norm, self.baseline)
            try:
                axis = [a for a in figure.axes if a.get_visible() and a.get_title()][0]
                self.assertEqual(len(axis.collections), 1)
                self.assertEqual(list(axis.collections[0].get_array()), expected)
                self.assertEqual(list(axis.collections[0].get_offsets()[0]), [0, 1])
                self.assertEqual(axis.collections[0].get_sizes()[0], p.MARKER_SIZE)
            finally:
                p.plt.close(figure)


if __name__ == '__main__':
    unittest.main()
