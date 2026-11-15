"""Systematic single-cell displacement of the fixed 27-cell demultiplexer."""
import argparse
import csv
import math
import os
from pathlib import Path
import re

import yaml

HERE = Path(__file__).resolve().parent
ORIGINAL = HERE.parent / 'qca-files' / 'demultiplexer_12.qca'
CONFIG = HERE / 'cells.yaml'
DEFAULT_DISTANCES = (0.5, 1, 1.5, 2, 3, 4, 5)
DIRECTIONS = {'+x': (1, 0), '-x': (-1, 0), '+y': (0, 1), '-y': (0, -1)}
TOLERANCE = 1e-9  # nm; touching boundaries are allowed.
TAG = re.compile(r'^\[(#?)([^\[\]]+)\]$')
FIELD = re.compile(r'^[ \t]*([^=\r\n]+?)[ \t]*=[ \t]*([^\r\n]*?)[ \t]*(?:\r?\n)?$')
AXES = {'x': 0, 'y': 1, 'bounding_box.xWorld': 0, 'bounding_box.yWorld': 1}
COLUMNS = ('case_id', 'cell_id', 'cell_group', 'direction', 'displacement_nm',
           'dx_nm', 'dy_nm', 'original_x_nm', 'original_y_nm', 'new_x_nm',
           'new_y_nm', 'status', 'circuit_path')


def number(value):
    if isinstance(value, bool):
        raise ValueError('expected a finite number, not a boolean')
    result = float(value)
    if not math.isfinite(result):
        raise ValueError('coordinates and distances must be finite')
    return result


def parse_circuit(text):
    """Keep source spans, not a reconstructed file; labels remain inside cells.

    The stack delimits nested sections. Only design-object and dot coordinates
    are marked for translation; dimensions and every other field stay verbatim.
    """
    stack, cells = [], []
    current, layer, offset = None, -1, 0
    for line in text.splitlines(keepends=True):
        tag = TAG.fullmatch(line.strip())
        if tag:
            closing, kind = tag.groups()
            if closing:
                if not stack or stack[-1] != kind:
                    raise ValueError(f'mismatched closing section: {kind}')
                if kind == 'TYPE:QCADCell':
                    current['end'] = offset + len(line)
                    cells.append(current)
                    current = None
                stack.pop()
            else:
                if kind == 'TYPE:QCADLayer':
                    layer += 1
                elif kind == 'TYPE:QCADCell':
                    if current is not None or 'TYPE:QCADLayer' not in stack:
                        raise ValueError('unexpected nested or unlayered cell')
                    current = dict(start=offset, layer=layer, fields={},
                                   objects=[], dots=[], coordinates=[])
                elif current is not None and kind in ('TYPE:QCADDesignObject', 'TYPE:CELL_DOT'):
                    current['objects' if kind == 'TYPE:QCADDesignObject' else 'dots'].append({})
                stack.append(kind)
        elif current is not None:
            field = FIELD.fullmatch(line)
            if field:
                key, value = field.groups()
                parent = stack[-1]
                if parent == 'TYPE:QCADCell':
                    current['fields'][key] = value
                elif parent in ('TYPE:QCADDesignObject', 'TYPE:CELL_DOT'):
                    target = current['objects' if parent == 'TYPE:QCADDesignObject' else 'dots'][-1]
                    target[key] = value
                    if key in AXES:
                        current['coordinates'].append((offset + field.start(2),
                                                       offset + field.end(2),
                                                       AXES[key], number(value)))
        offset += len(line)
    if stack or len(cells) != 27:
        raise ValueError('expected a complete circuit containing exactly 27 cells')
    for cell in cells:
        obj, fields = cell['objects'][0], cell['fields']
        cell.update(x=number(obj['x']), y=number(obj['y']),
                    width=number(fields['cell_options.cxCell']),
                    height=number(fields['cell_options.cyCell']))
        expected = (cell['x'] - cell['width'] / 2, cell['y'] - cell['height'] / 2,
                    cell['width'], cell['height'])
        actual = tuple(number(obj['bounding_box.' + key])
                       for key in ('xWorld', 'yWorld', 'cxWorld', 'cyWorld'))
        if (min(cell['width'], cell['height']) <= 0
                or fields['cell_options.mode'] != 'QCAD_CELL_MODE_NORMAL'
                or any(abs(a - b) > TOLERANCE for a, b in zip(actual, expected))
                or len(cell['dots']) != 4 or number(fields['number_of_dots']) != 4):
            raise ValueError('expected normal, axis-aligned four-dot cells')
    return cells


def find_cell(cells, x, y):
    matches = [cell for cell in cells if abs(cell['x'] - x) <= TOLERANCE
               and abs(cell['y'] - y) <= TOLERANCE]
    if len(matches) != 1:
        raise ValueError(f'coordinate ({x}, {y}) matches {len(matches)} cells, expected one')
    return matches[0]


def load_cells(physical_cells):
    with CONFIG.open(encoding='utf-8') as source:
        selected = yaml.safe_load(source)['cells']
    if not isinstance(selected, dict) or len(selected) != 15:
        raise ValueError('cells.yaml must configure the 15 selected cells')
    seen = set()
    for name, spec in selected.items():
        if not re.fullmatch(r'(?:W[1-4]|N1|M[01][a-e])', name):
            raise ValueError(f'unknown semantic cell identifier: {name}')
        spec['x'], spec['y'] = number(spec['x']), number(spec['y'])
        cell = find_cell(physical_cells, spec['x'], spec['y'])
        if cell['start'] in seen:
            raise ValueError(f'{name}: another identifier already selects this cell')
        if cell['fields']['cell_function'] in ('QCAD_CELL_INPUT', 'QCAD_CELL_OUTPUT'):
            raise ValueError(f'{name}: external inputs and outputs are excluded')
        directions = spec['directions']
        if (spec['group'] not in ('wire', 'inverter', 'majority')
                or not isinstance(directions, list) or not directions
                or any(direction not in DIRECTIONS for direction in directions)
                or len(directions) != len(set(directions))):
            raise ValueError(f'{name}: invalid group or permitted directions')
        seen.add(cell['start'])
        spec['cell'] = cell
    return selected


def check_overlap(cell, cells, dx, dy):
    """Compare just the moved physical rectangle against its same-layer peers."""
    return any(other is not cell and other['layer'] == cell['layer']
               and abs(cell['x'] + dx - other['x'])
               < (cell['width'] + other['width']) / 2 - TOLERANCE
               and abs(cell['y'] + dy - other['y'])
               < (cell['height'] + other['height']) / 2 - TOLERANCE
               for other in cells)


def displace_cell(original_text, cell, dx, dy):
    """Translate one cell's center, box, dots and attached label geometry."""
    if (cell['x'] + dx, cell['y'] + dy) == (cell['x'], cell['y']):
        raise ValueError('displacement is too small to change the cell coordinates')
    chunks, position = [], 0
    for start, end, axis, value in cell['coordinates']:
        delta = (dx, dy)[axis]
        if delta:
            translated = number(value + delta)
            chunks.extend((original_text[position:start], format(translated, '.17g')))
            position = end
    chunks.append(original_text[position:])
    return ''.join(chunks)


def generate_circuits(cells=None, directions=None, distances=DEFAULT_DISTANCES,
                      output=Path('generated/systematic'), dry_run=False):
    original_text = ORIGINAL.read_bytes().decode('utf-8')
    physical_cells = parse_circuit(original_text)
    configured = load_cells(physical_cells)
    names = list(configured) if cells is None else cells
    distances = [number(distance) for distance in distances]
    if not names or len(names) != len(set(names)) or any(name not in configured for name in names):
        raise ValueError('select distinct configured cell identifiers')
    if (not distances or any(distance <= 0 for distance in distances)
            or len(distances) != len(set(distances))):
        raise ValueError('distances must be distinct, positive finite numbers')
    if directions is not None:
        if not directions or len(directions) != len(set(directions)):
            raise ValueError('select distinct permitted directions')
        for name in names:
            if any(direction not in configured[name]['directions'] for direction in directions):
                raise ValueError(f'{name}: requested direction is not permitted by cells.yaml')
    if any(check_overlap(cell, physical_cells, 0, 0) for cell in physical_cells):
        raise ValueError('the original circuit already contains overlapping cells')
    output = Path(output)
    if not dry_run:
        output.mkdir(parents=True, exist_ok=True)
        if any(output.iterdir()):
            raise FileExistsError(f'output directory must be empty: {output}')
    rows = [dict(case_id='baseline', status='BASELINE',
                 circuit_path=Path(os.path.relpath(ORIGINAL, output)).as_posix())]
    for name in names:
        spec = configured[name]
        cell = spec['cell']
        for direction in spec['directions'] if directions is None else directions:
            for distance in distances:
                dx, dy = (component * distance for component in DIRECTIONS[direction])
                token = str(distance).removesuffix('.0').replace('.', 'p')
                direction_token = direction.replace('+', 'p').replace('-', 'n')
                case_id = f'{name}_{direction_token}_{token}nm'
                overlap = check_overlap(cell, physical_cells, dx, dy)
                filename = '' if overlap else case_id + '.qca'
                if not overlap:
                    variant = displace_cell(original_text, cell, dx, dy)
                    if not dry_run:
                        with (output / filename).open('x', encoding='utf-8', newline='') as target:
                            target.write(variant)
                rows.append(dict(case_id=case_id, cell_id=name, cell_group=spec['group'],
                                 direction=direction, displacement_nm=distance, dx_nm=dx, dy_nm=dy,
                                 original_x_nm=cell['x'], original_y_nm=cell['y'],
                                 new_x_nm=cell['x'] + dx, new_y_nm=cell['y'] + dy,
                                 status='OVERLAP' if overlap else 'GENERATED', circuit_path=filename))
    if not dry_run:
        with (output / 'manifest.csv').open('x', encoding='utf-8', newline='') as target:
            writer = csv.DictWriter(target, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cells', help='Comma-separated identifiers; default: all 15')
    parser.add_argument('--directions', help='Comma-separated permitted directions; e.g. +x,+y or --directions=-x')
    parser.add_argument('--distances', default=','.join(map(str, DEFAULT_DISTANCES)), help='Comma-separated distances in nm')
    parser.add_argument('--output', type=Path, default=Path('generated/systematic'), help='Output directory, relative to the current directory')
    parser.add_argument('--dry-run', action='store_true', help='Check all candidates without writing any files')
    args = parser.parse_args(argv)
    try:
        rows = generate_circuits(cells=args.cells.split(',') if args.cells is not None else None,
                                 directions=args.directions.split(',') if args.directions is not None else None,
                                 distances=args.distances.split(','), output=args.output, dry_run=args.dry_run)
    except (OSError, ValueError, TypeError, KeyError, IndexError, yaml.YAMLError) as error:
        parser.exit(2, f'error: {error}\n')
    valid = sum(row['status'] == 'GENERATED' for row in rows)
    print(f'Candidates: {len(rows) - 1}; geometrically valid: {valid}; overlaps: {len(rows) - 1 - valid}')
    print('Dry run: no files written.' if args.dry_run else f'Output: {args.output.resolve()}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
