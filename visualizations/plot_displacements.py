"""Plot every displaced cell's runs as PASS/FAIL dots on one overview figure.

Install: python -m pip install -r visualizations/requirements.txt
Usage: python visualizations/plot_displacements.py analysis_results/run.XXXXXX [-o OUTPUT_PNG]
View only: python visualizations/plot_displacements.py analysis_results/run.XXXXXX --view
Or: just -f visualizations/justfile viz-view analysis_results/run.XXXXXX

The input is a workflow run directory containing circuits/manifest.csv and
results/<case_id>/full-summary.json. Each cell gets its own subplot: x is the
dx displacement, y the dy displacement (nm). A dot is one run: blue for PASS,
red for FAIL. Rows group the cells (wires, inverter, upper and lower majority
gate) so related cells sit side by side; all subplots share axis limits.
+y is DOWN in QCADesigner-E, so the y axis is inverted to match the layout.
OVERLAP rows were never simulated and are not drawn; generated cases without a
readable verdict are skipped with a warning.
Default output: <run dir>/displacement-overview.png.
"""
import argparse
import csv
import json
from pathlib import Path
import sys

# Reuse the graph component's desktop-backend selection, independent of the cwd.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'graph'))
from plot_traces import interactive_backend

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

PASS_COLOR = '#1f6fd1'
FAIL_COLOR = '#d0312d'
ROW_TITLES = {'wire': 'Celice vodila', 'inverter': 'Celica negatorja',
              'M0': 'Zgornja majoritetna vrata', 'M1': 'Spodnja majoritetna vrata'}


class VisualizationError(ValueError):
    pass


def row_key(cell_id, group):
    """Split majority cells by gate (M0*/M1*); other groups are one row each."""
    return cell_id[:2] if group == 'majority' else group


def load_runs(run_dir):
    """Return {cell_id: (group, [(dx, dy, passed), ...])} in manifest order."""
    manifest = run_dir / 'circuits' / 'manifest.csv'
    if not manifest.is_file():
        raise VisualizationError(f'manifest not found: {manifest}')
    cells = {}
    with manifest.open(newline='') as handle:
        for row in csv.DictReader(handle):
            if row['status'] != 'GENERATED':
                continue
            summary = run_dir / 'results' / row['case_id'] / 'full-summary.json'
            try:
                status = json.loads(summary.read_text())['status']
            except (OSError, ValueError, KeyError) as error:
                print(f'warning: skipping {row["case_id"]}: no readable verdict ({error})',
                      file=sys.stderr)
                continue
            if status not in ('PASS', 'FAIL'):
                print(f'warning: skipping {row["case_id"]}: unexpected status {status!r}',
                      file=sys.stderr)
                continue
            _, runs = cells.setdefault(row['cell_id'], (row['cell_group'], []))
            runs.append((float(row['dx_nm']), float(row['dy_nm']), status == 'PASS'))
    if not cells:
        raise VisualizationError(f'no analyzed generated cases in {run_dir}')
    return cells


def layout(cells):
    """Rows of cell ids, one row per group, preserving manifest order."""
    rows = {}
    for cell_id, (group, _) in cells.items():
        rows.setdefault(row_key(cell_id, group), []).append(cell_id)
    return list(rows.items())


def build_figure(cells, title=None):
    rows = layout(cells)
    ncols = max(len(ids) for _, ids in rows)
    figure, axes = plt.subplots(len(rows), ncols, squeeze=False, sharex=True, sharey=True, layout='constrained',
                                figsize=(3.2 * ncols, 3.4 * len(rows) + 0.8))
    limit = max(max(abs(dx), abs(dy)) for _, runs in cells.values() for dx, dy, _ in runs)
    limit = limit * 1.15 or 1
    for (key, ids), axis_row in zip(rows, axes):
        for column, axis in enumerate(axis_row):
            if column >= len(ids):
                axis.set_visible(False)
                continue
            cell_id = ids[column]
            runs = cells[cell_id][1]
            axis.axhline(0, color='0.75', linewidth=0.6, zorder=0)
            axis.axvline(0, color='0.75', linewidth=0.6, zorder=0)
            axis.plot([0], [0], marker='+', color='0.2', markersize=9, linestyle='none', zorder=1)
            for passed, color, marker in ((True, PASS_COLOR, 'o'), (False, FAIL_COLOR, 'X')):
                points = [(dx, dy) for dx, dy, ok in runs if ok is passed]
                if points:
                    xs, ys = zip(*points)
                    axis.scatter(xs, ys, c=color, marker=marker, s=46,
                                 edgecolors='white', linewidths=0.8, zorder=2)
            passes = sum(ok for *_, ok in runs)
            axis.set_title(f'{cell_id}  ({passes}/{len(runs)} pravilnih)', fontsize=10)
            axis.set_xlim(-limit, limit)
            axis.set_ylim(limit, -limit)  # +y is down in QCADesigner-E
            axis.set_aspect('equal')
            axis.grid(True, color='0.92', linewidth=0.5)
            axis.tick_params(labelsize=8, labelbottom=True, labelleft=True)
            if column == 0:
                axis.set_ylabel(f'{ROW_TITLES.get(key, key)}\ndy [nm] (+ navzdol)', fontsize=9)
            axis.set_xlabel('dx [nm]', fontsize=8)
    legend = [Line2D([], [], marker='o', color='w', markerfacecolor=PASS_COLOR,
                     markersize=8, label='pravilno (PASS)'),
              Line2D([], [], marker='X', color='w', markerfacecolor=FAIL_COLOR,
                     markersize=8, label='napačno (FAIL)'),
              Line2D([], [], marker='+', color='0.2', linestyle='none',
                     markersize=9, label='izvirni položaj')]
    figure.legend(handles=legend, loc='outside upper right', ncol=3, frameon=False)
    if title:
        figure.suptitle(title, parse_math=False)
    figure.get_layout_engine().set(h_pad=0.12, w_pad=0.08)
    return figure


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('run_dir', type=Path, help='workflow run directory (analysis_results/run.*)')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--view', action='store_true',
                      help='show the overview in an interactive window; save nothing')
    mode.add_argument('-o', '--output', type=Path,
                      help='PNG path (default: <run dir>/displacement-overview.png)')
    args = parser.parse_args(argv)
    output = args.output or args.run_dir / 'displacement-overview.png'
    title = f'Rezultati premikov posameznih celic: {args.run_dir.name}'
    try:
        cells = load_runs(args.run_dir)
        if args.view:
            interactive_backend()
            figure = build_figure(cells, title)
            try:
                figure.canvas.manager.set_window_title(title)
                plt.show(block=True)
            finally:
                plt.close(figure)
            return 0
        figure = build_figure(cells, title)
        try:
            output.parent.mkdir(parents=True, exist_ok=True)
            figure.savefig(output, format='png', dpi=150)
        finally:
            plt.close(figure)
    except (OSError, VisualizationError, ValueError, ImportError, RuntimeError) as error:
        print(f'error: {error}', file=sys.stderr)
        return 1
    print(f'Saved overview to {output}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
