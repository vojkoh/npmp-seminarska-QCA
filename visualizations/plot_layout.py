"""Draw the original demultiplexer layout with every displaced cell's name.

Install: python -m pip install -r visualizations/requirements.txt
Usage: python visualizations/plot_layout.py [-o OUTPUT_PNG]
View only: python visualizations/plot_layout.py --view
Or: just -f visualizations/justfile layout / layout-view

Reads the unchanged qca-files/demultiplexer_12.qca and generator/cells.yaml through
the generator's own parser, so the diagram always matches what is displaced.
Cells use QCADesigner's own colours: normal cells by clock zone (0 green,
1 magenta, 2 cyan, 3 white), fixed cells orange, inputs blue, outputs yellow.
Displaced cells are named; unnamed cells are never displaced. Each cell also
shows its clock zone in the corner. +y is DOWN, as in QCADesigner-E.
Default output: analysis_results/cell-layout.png.
"""
import argparse
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'generator'))
sys.path.insert(0, str(ROOT / 'graph'))
from generate import ORIGINAL, load_cells, parse_circuit
from plot_traces import interactive_backend

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Patch, Rectangle

# Exact colours QCADesigner uses on screen.
CLOCK_COLORS = {'0': '#00ff00', '1': '#ff00ff', '2': '#00ffff', '3': '#ffffff'}
FUNCTION_COLORS = {'QCAD_CELL_FIXED': '#ff8000', 'QCAD_CELL_INPUT': '#0000ff',
                   'QCAD_CELL_OUTPUT': '#ffff00'}
EDGE = '0.15'
LABEL = re.compile(r'^psz=(.*)$', re.MULTILINE)


def cell_label(text, cell):
    """QCADesigner stores an I/O or fixed cell's label text inside the cell span."""
    match = LABEL.search(text, cell['start'], cell['end'])
    return match.group(1).strip() if match else ''


def load_layout(original=ORIGINAL):
    text = original.read_text(encoding='utf-8')
    cells = parse_circuit(text)
    names = {spec['cell']['start']: (name, spec) for name, spec in load_cells(cells).items()}
    layout = []
    for cell in cells:
        name, spec = names.get(cell['start'], (None, None))
        layout.append(dict(
            x=cell['x'], y=cell['y'], size=cell['width'], name=name,
            group=spec['group'] if spec else None,
            function=cell['fields']['cell_function'],
            clock=cell['fields'].get('cell_options.clock', ''),
            label=cell_label(text, cell)))
    return layout


def gate_box(axis, cells, title):
    xs = [c['x'] for c in cells]
    ys = [c['y'] for c in cells]
    half = cells[0]['size'] / 2 + 1  # stay inside the 2 nm gap between cells
    x0, y0 = min(xs) - half, min(ys) - half
    axis.add_patch(FancyBboxPatch((x0, y0), max(xs) - min(xs) + 2 * half,
                                  max(ys) - min(ys) + 2 * half,
                                  boxstyle='round,pad=0,rounding_size=4', fill=False,
                                  edgecolor='0.35', linestyle='--',
                                  linewidth=1.2, zorder=0))
    axis.text(x0 - 3, (min(ys) + max(ys)) / 2, title, ha='right', va='center',
              fontsize=9, color='0.25')


def cell_color(cell):
    return FUNCTION_COLORS.get(cell['function']) or CLOCK_COLORS.get(cell['clock'], '#d9d9d9')


def build_figure(layout, title=None):
    figure, axis = plt.subplots(figsize=(9, 9), layout='constrained')
    for cell in layout:
        half = cell['size'] / 2
        fixed = cell['function'] == 'QCAD_CELL_FIXED'
        io = cell['function'] in ('QCAD_CELL_INPUT', 'QCAD_CELL_OUTPUT')
        face = cell_color(cell)
        ink = 'white' if cell['function'] == 'QCAD_CELL_INPUT' else 'black'
        axis.add_patch(Rectangle((cell['x'] - half, cell['y'] - half), cell['size'], cell['size'],
                                 facecolor=face, edgecolor=EDGE, linewidth=1.0, zorder=2))
        if cell['name']:
            text = cell['name'] + (f'\n{cell["label"]}' if fixed and cell['label'] else '')
        elif io:
            kind = 'VHOD' if cell['function'] == 'QCAD_CELL_INPUT' else 'IZHOD'
            text = f'{cell["label"]}\n{kind}'
        else:
            text = ''
        if text:
            axis.text(cell['x'], cell['y'], text, ha='center', va='center', fontsize=9,
                      color=ink, fontweight='bold', zorder=3)
        axis.text(cell['x'] + half - 1, cell['y'] + half - 1, cell['clock'], ha='right',
                  va='bottom', fontsize=6, color=ink, zorder=3)
    for gate, title_text in (('M0', 'Zgornja\nmajoritetna\nvrata (M0)'),
                              ('M1', 'Spodnja\nmajoritetna\nvrata (M1)')):
        members = [c for c in layout if c['name'] and c['name'].startswith(gate)]
        if members:
            gate_box(axis, members, title_text)
    xs = [c['x'] for c in layout]
    ys = [c['y'] for c in layout]
    axis.set_xlim(min(xs) - 60, max(xs) + 20)
    axis.set_ylim(max(ys) + 20, min(ys) - 20)  # +y is down in QCADesigner-E
    axis.set_aspect('equal')
    axis.set_xticks(sorted(set(xs)))
    axis.set_yticks(sorted(set(ys)))
    axis.tick_params(labelsize=8, length=0)
    axis.set_xlabel('x [nm]')
    axis.set_ylabel('y [nm] (+ navzdol)')
    for spine in axis.spines.values():
        spine.set_visible(False)
    handles = [Patch(facecolor=c, edgecolor=EDGE, label=f'Urina cona {k}')
               for k, c in CLOCK_COLORS.items()]
    handles += [Patch(facecolor=FUNCTION_COLORS[f], edgecolor=EDGE, label=label)
                for f, label in (('QCAD_CELL_FIXED', 'Fiksna polarizacija'),
                                 ('QCAD_CELL_INPUT', 'Vhod'), ('QCAD_CELL_OUTPUT', 'Izhod'))]
    figure.legend(handles=handles, loc='outside lower center', ncol=4, frameon=False,
                  fontsize=9)
    if title:
        figure.suptitle(title, parse_math=False)
    axis.text(1, 1.01, 'poimenovane celice se premikajo; majhna številka: urina cona', transform=axis.transAxes, ha='right',
              va='bottom', fontsize=7, color='0.4')
    return figure


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--view', action='store_true',
                      help='show the layout in an interactive window; save nothing')
    mode.add_argument('-o', '--output', type=Path,
                      help='PNG path (default: analysis_results/cell-layout.png)')
    args = parser.parse_args(argv)
    output = args.output or ROOT / 'analysis_results' / 'cell-layout.png'
    title = f'Premaknjene celice v {ORIGINAL.name}'
    try:
        layout = load_layout()
        if args.view:
            interactive_backend()
        figure = build_figure(layout, title)
        try:
            if args.view:
                figure.canvas.manager.set_window_title(title)
                plt.show(block=True)
                return 0
            output.parent.mkdir(parents=True, exist_ok=True)
            figure.savefig(output, format='png', dpi=150)
        finally:
            plt.close(figure)
    except (OSError, ValueError, KeyError, ImportError, RuntimeError) as error:
        print(f'error: {error}', file=sys.stderr)
        return 1
    print(f'Saved layout to {output}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
