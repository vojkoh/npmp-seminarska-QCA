"""Focused checks; run from this directory with python -m unittest -v."""
import csv
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

import generate as g


class GeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_bytes = g.ORIGINAL.read_bytes()
        cls.text = cls.original_bytes.decode('utf-8')
        cls.physical = g.parse_circuit(cls.text)
        cls.selected = g.load_cells(cls.physical)

    def tearDown(self):
        self.assertEqual(g.ORIGINAL.read_bytes(), self.original_bytes)

    def test_verified_mapping(self):
        expected = dict(W1=(120, 140), W2=(120, 180), W3=(200, 60), W4=(220, 220),
                        N1=(200, 120), M0a=(140, 60), M0b=(180, 60), M0c=(160, 80),
                        M0d=(140, 100), M0e=(180, 100), M1a=(160, 180), M1b=(200, 180),
                        M1c=(180, 200), M1d=(160, 220), M1e=(200, 220))
        self.assertEqual(len(self.physical), 27)
        self.assertEqual({name: (s['x'], s['y']) for name, s in self.selected.items()}, expected)
        self.assertEqual(len({s['cell']['start'] for s in self.selected.values()}), 15)
        fixed = [name for name, s in self.selected.items()
                 if s['cell']['fields']['cell_function'] == 'QCAD_CELL_FIXED']
        self.assertEqual(fixed, ['M0a', 'M1d'])

    def test_complete_translation_and_unchanged_other_content(self):
        def mask_coordinates(text, cell):
            chunks, position = [], 0
            for start, end, _, _ in cell['coordinates']:
                chunks.extend((text[position:start], '<coordinate>'))
                position = end
            return ''.join(chunks) + text[position:]

        for name, spec in self.selected.items():
            original = spec['cell']
            index = self.physical.index(original)
            for direction, (vx, vy) in g.DIRECTIONS.items():
                with self.subTest(cell=name, direction=direction):
                    dx, dy = vx * 1.5, vy * 1.5
                    text = g.displace_cell(self.text, original, dx, dy)
                    cells = g.parse_circuit(text)
                    moved = cells[index]
                    changed = [i for i, (a, b) in enumerate(zip(self.physical, cells))
                               if (a['x'], a['y']) != (b['x'], b['y'])]
                    self.assertEqual(changed, [index])
                    self.assertEqual(len(moved['coordinates']), len(original['coordinates']))
                    self.assertEqual(len(moved['dots']), 4)
                    self.assertEqual(len(moved['objects']), 2 if name in ('M0a', 'M1d') else 1)
                    for before, after in zip(original['coordinates'], moved['coordinates']):
                        self.assertEqual(before[2], after[2])
                        self.assertAlmostEqual(after[3], before[3] + (dx, dy)[before[2]])
                    self.assertEqual(mask_coordinates(self.text, original), mask_coordinates(text, moved))
        self.assertEqual(self.text.encode('utf-8'), self.original_bytes)

    def test_overlap_touching_tolerance_and_layers(self):
        cell = self.selected['W1']['cell']
        self.assertFalse(g.check_overlap(cell, self.physical, 1, 0))
        self.assertFalse(g.check_overlap(cell, self.physical, 2, 0))
        self.assertFalse(g.check_overlap(cell, self.physical, 2 + g.TOLERANCE / 2, 0))
        self.assertTrue(g.check_overlap(cell, self.physical, 2 + g.TOLERANCE * 10, 0))
        self.assertTrue(g.check_overlap(cell, self.physical, 3, 0))
        other_layer = dict(cell, layer=cell['layer'] + 1)
        self.assertFalse(g.check_overlap(cell, [cell, other_layer], 1, 0))
        corner = dict(cell, x=cell['x'] + 20, y=cell['y'] + 20)
        self.assertFalse(g.check_overlap(cell, [cell, corner], 2, 2))
        self.assertTrue(g.check_overlap(cell, [cell, corner], 3, 3))

    def test_manifest_and_independent_variants(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'cases with spaces'
            rows = g.generate_circuits(['W1'], ['+x'], [0.5, 1, 2, 3], output)
            with (output / 'manifest.csv').open(newline='') as source:
                reader = csv.DictReader(source)
                self.assertEqual(reader.fieldnames, list(g.COLUMNS))
                manifest = list(reader)
            self.assertEqual([r['status'] for r in rows],
                             ['BASELINE', 'GENERATED', 'GENERATED', 'GENERATED', 'OVERLAP'])
            self.assertEqual((output / manifest[0]['circuit_path']).resolve(), g.ORIGINAL)
            self.assertEqual(manifest[-1]['circuit_path'], '')
            self.assertFalse((output / 'W1_px_3nm.qca').exists())
            self.assertEqual({p.name for p in output.iterdir()},
                             {'manifest.csv', 'W1_px_0p5nm.qca', 'W1_px_1nm.qca', 'W1_px_2nm.qca'})
            for row in manifest[1:-1]:
                text = (output / row['circuit_path']).read_text()
                cell = g.find_cell(g.parse_circuit(text), 120 + float(row['dx_nm']), 140)
                self.assertEqual(cell['x'], float(row['new_x_nm']))
                self.assertEqual(row['cell_id'], 'W1')
                self.assertEqual(float(row['original_x_nm']), 120)
            with self.assertRaises(FileExistsError):
                g.generate_circuits(['W1'], ['+x'], [1], output)

    def test_default_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'not-created'
            rows = g.generate_circuits(output=output, dry_run=True)
            self.assertEqual(len(rows) - 1, 420)
            self.assertEqual(sum(r['status'] == 'GENERATED' for r in rows), 378)
            self.assertEqual(sum(r['status'] == 'OVERLAP' for r in rows), 42)
            self.assertFalse(output.exists())

    def test_invalid_selections_and_distances(self):
        for options in [dict(cells=['D']), dict(cells=['W1', 'W1']), dict(cells=[]),
                        dict(directions=['diagonal']), dict(directions=['+x', '+x']),
                        dict(distances=[0]), dict(distances=[-1]), dict(distances=[float('nan')]),
                        dict(distances=[float('inf')]), dict(distances=[1, 1]), dict(distances=[1e-20])]:
            with self.subTest(options=options), self.assertRaises(ValueError):
                g.generate_circuits(dry_run=True, **options)

    def test_configuration_restrictions_and_duplicate_coordinates(self):
        config = yaml.safe_load(g.CONFIG.read_text())
        config['cells']['W1']['directions'] = ['+x']
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'cells.yaml'
            path.write_text(yaml.safe_dump(config))
            with patch.object(g, 'CONFIG', path):
                rows = g.generate_circuits(['W1'], distances=[1], dry_run=True)
                self.assertEqual([r.get('direction') for r in rows[1:]], ['+x'])
                with self.assertRaisesRegex(ValueError, 'not permitted'):
                    g.generate_circuits(['W1'], ['-x'], [1], dry_run=True)
                config['cells']['W2'].update(x=120, y=140)
                path.write_text(yaml.safe_dump(config))
                with self.assertRaisesRegex(ValueError, 'already selects'):
                    g.load_cells(self.physical)

    def test_cli_from_another_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, str(g.HERE / 'generate.py'),
                                     '--cells', 'W1', '--directions=-x', '--distances', '1',
                                     '--output', 'local-output'], cwd=directory,
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            output = Path(directory) / 'local-output'
            self.assertTrue((output / 'W1_nx_1nm.qca').is_file())
            self.assertIn('Candidates: 1; geometrically valid: 1; overlaps: 0', result.stdout)

    def test_malformed_sections_rejected(self):
        with self.assertRaisesRegex(ValueError, 'mismatched'):
            g.parse_circuit(self.text.replace('[#TYPE:CELL_DOT]', '[#TYPE:QCADLabel]', 1))
        with self.assertRaisesRegex(ValueError, 'complete circuit'):
            g.parse_circuit(self.text.replace('[#TYPE:DESIGN]', ''))


if __name__ == '__main__':
    unittest.main()
