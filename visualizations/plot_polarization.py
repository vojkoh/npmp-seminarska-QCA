"""Plot output polarization strength for every displaced cell: one figure per output.

Install: python -m pip install -r visualizations/requirements.txt
Usage: python visualizations/plot_polarization.py analysis_results/run.XXXXXX [-o OUTPUT_DIR]
View only: python visualizations/plot_polarization.py analysis_results/run.XXXXXX --view
Or: just -f visualizations/justfile polarization analysis_results/run.XXXXXX

Creates two figures, one for Y0 and one for Y1, in the same grid as the PASS/FAIL
overview (one subplot per cell, dx/dy in nm, +y down). Each run is one circle;
its colour is the absolute output polarization |P| of the weakest hold window of
that output in the run (min over windows of |mean polarization|), from blue
(strongest) to red (weakest). Both figures share one colour scale spanning only
the observed range (not 0..1), so their colours are directly comparable.
The sign (correct/wrong logic value) is not shown; see the PASS/FAIL overview.
The baseline (unchanged circuit) is drawn at the origin when available.
Default output: <run dir>/polarization-Y0.png and <run dir>/polarization-Y1.png.
"""
import argparse
import csv
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plot_displacements import VisualizationError, cell_grid, interactive_backend

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
from matplotlib.lines import Line2D

CMAP = plt.get_cmap('coolwarm_r')  # high |P| blue, low |P| red; neutral middle
OUTPUTS = ('Y0', 'Y1')
MARKER_SIZE = 70


def weakest_outputs(measurements):
    """Return {'Y0': min |mean|, 'Y1': min |mean|} over all hold windows of a run."""
    weakest = {}
    with Path(measurements).open(newline='') as handle:
        for row in csv.DictReader(handle):
            label = row['trace_label']
            if label in OUTPUTS:
                value = abs(float(row['mean']))
                weakest[label] = min(weakest.get(label, value), value)
    if set(weakest) != set(OUTPUTS):
        raise VisualizationError(f'{measurements}: missing Y0 or Y1 measurements')
    return weakest


def load_polarization(run_dir):
    """Return ({cell_id: (group, [(dx, dy, {'Y0':…, 'Y1':…}), ...])}, baseline or None)."""
    manifest = run_dir / 'circuits' / 'manifest.csv'
    if not manifest.is_file():
        raise VisualizationError(f'manifest not found: {manifest}')
    cells = {}
    with manifest.open(newline='') as handle:
        for row in csv.DictReader(handle):
            if row['status'] != 'GENERATED':
                continue
            path = run_dir / 'results' / row['case_id'] / 'full-measurements.csv'
            try:
                values = weakest_outputs(path)
            except (OSError, ValueError, KeyError) as error:
                print(f'warning: skipping {row["case_id"]}: {error}', file=sys.stderr)
                continue
            _, runs = cells.setdefault(row['cell_id'], (row['cell_group'], []))
            runs.append((float(row['dx_nm']), float(row['dy_nm']), values))
    if not cells:
        raise VisualizationError(f'no analyzed generated cases in {run_dir}')
    baseline = None
    try:
        baseline = weakest_outputs(run_dir / 'baseline' / 'full-measurements.csv')
    except (OSError, ValueError, KeyError) as error:
        print(f'warning: baseline not drawn: {error}', file=sys.stderr)
    return cells, baseline


def shared_norm(cells, baseline=None):
    """One colour scale for both outputs, covering only the observed |P| range."""
    values = [v for _, runs in cells.values() for *_, pol in runs for v in pol.values()]
    if baseline:
        values += list(baseline.values())
    low, high = min(values), max(values)
    if high - low < 1e-6:  # flat data still needs a valid scale
        low, high = low - 0.005, high + 0.005
    return Normalize(low, high)


def slovene(value, digits=3):
    return f'{value:.{digits}f}'.replace('.', ',')


def build_figure(cells, output, norm, baseline=None, title=None):
    figure, by_cell = cell_grid(cells, origin_marker=baseline is None, extra_width=1.0)
    for cell_id, axis in by_cell.items():
        points = [(dx, dy, pol[output]) for dx, dy, pol in cells[cell_id][1]]
        if baseline:
            points.append((0.0, 0.0, baseline[output]))
        xs, ys, cs = zip(*points)
        axis.scatter(xs, ys, c=cs, cmap=CMAP, norm=norm, marker='o', s=MARKER_SIZE,
                     edgecolors='0.25', linewidths=0.5, zorder=2)
        weakest = min(pol[output] for *_, pol in cells[cell_id][1])
        axis.set_title(f'{cell_id}  (min |P| = {slovene(weakest)})', fontsize=10)
    mappable = plt.cm.ScalarMappable(norm=norm, cmap=CMAP)
    colorbar = figure.colorbar(mappable, ax=list(by_cell.values()), shrink=0.6, pad=0.01,
                               aspect=40)
    colorbar.set_label(f'|P| izhoda {output} (najšibkejše okno)', fontsize=10)
    colorbar.ax.yaxis.set_major_formatter(lambda value, _: slovene(value, 2))
    if baseline:
        # A legend entry (not free text) so constrained layout reserves room for it.
        figure.legend(handles=[Line2D([], [], linestyle='none',
                                      label='v izhodišču: nespremenjeno vezje')],
                      loc='outside lower center', frameon=False, handlelength=0,
                      fontsize=9, labelcolor='0.3')
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
                      help='show both figures in interactive windows; save nothing')
    mode.add_argument('-o', '--output-dir', type=Path,
                      help='directory for polarization-Y0.png and polarization-Y1.png '
                           '(default: the run directory)')
    args = parser.parse_args(argv)
    output_dir = args.output_dir or args.run_dir
    figures = []
    try:
        cells, baseline = load_polarization(args.run_dir)
        norm = shared_norm(cells, baseline)
        if args.view:
            interactive_backend()
        for output in OUTPUTS:
            title = f'Moč polarizacije izhoda {output} ob premikih posameznih celic: {args.run_dir.name}'
            figure = build_figure(cells, output, norm, baseline, title)
            figures.append(figure)
            if args.view:
                figure.canvas.manager.set_window_title(title)
                continue
            path = output_dir / f'polarization-{output}.png'
            path.parent.mkdir(parents=True, exist_ok=True)
            figure.savefig(path, format='png', dpi=150)
            print(f'Saved {output} polarization overview to {path}')
        if args.view:
            plt.show(block=True)
    except (OSError, VisualizationError, ValueError, ImportError, RuntimeError) as error:
        print(f'error: {error}', file=sys.stderr)
        return 1
    finally:
        for figure in figures:
            plt.close(figure)
    return 0


if __name__ == '__main__':
    sys.exit(main())
