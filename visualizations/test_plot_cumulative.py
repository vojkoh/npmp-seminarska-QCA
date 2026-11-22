"""Run with: python -m unittest discover -s visualizations."""
import unittest

import plot_cumulative as p


class CumulativeTests(unittest.TestCase):
    def test_counts_accumulate_over_absolute_offsets(self):
        cells = {'W1': ('wire', [(0, 1, True), (0, -1, False), (0, 2, False)]),
                 'N1': ('inverter', [(-1, 0, False), (2, 0, True)])}
        self.assertEqual(p.cumulative_failures(cells), [(1, 2, 3), (2, 3, 5)])

    def test_figure_plots_cumulative_series(self):
        figure = p.build_figure([(0.5, 0, 4), (1, 3, 8)])
        try:
            line = figure.axes[0].lines[0]
            self.assertEqual(list(line.get_ydata()), [0, 37.5])
            self.assertEqual([t.get_text() for t in figure.axes[0].texts],
                             ['0,0 %\n(0/4)', '37,5 %\n(3/8)'])
        finally:
            p.plt.close(figure)


if __name__ == '__main__':
    unittest.main()
