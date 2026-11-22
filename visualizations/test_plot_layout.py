"""Run with: python -m unittest discover -s visualizations."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import plot_layout as p


class LayoutTests(unittest.TestCase):
    def test_layout_names_match_cells_yaml(self):
        layout = p.load_layout()
        self.assertEqual(len(layout), 27)
        named = {c['name']: c for c in layout if c['name']}
        self.assertEqual(len(named), 15)
        self.assertEqual((named['M0c']['x'], named['M0c']['y']), (160, 80))
        self.assertEqual({n for n, c in named.items() if c['function'] == 'QCAD_CELL_FIXED'},
                         {'M0a', 'M1d'})
        io = sorted(c['label'] for c in layout
                    if c['function'] in ('QCAD_CELL_INPUT', 'QCAD_CELL_OUTPUT'))
        self.assertEqual(io, ['D', 'S', 'Y0', 'Y1'])

    def test_main_saves_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'layout.png'
            with patch('sys.stdout'):
                self.assertEqual(p.main(['-o', str(out)]), 0)
            self.assertGreater(out.stat().st_size, 0)
        self.assertEqual(p.plt.get_fignums(), [])


if __name__ == '__main__':
    unittest.main()
