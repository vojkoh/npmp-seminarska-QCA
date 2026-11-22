"""Plot the cumulative percentage of failing scenarios against absolute displacement.

Install: python -m pip install -r visualizations/requirements.txt
Usage: python visualizations/plot_cumulative.py analysis_results/run.XXXXXX [-o OUTPUT_PNG]
View only: python visualizations/plot_cumulative.py analysis_results/run.XXXXXX --view
Or: just -f visualizations/justfile cumulative analysis_results/run.XXXXXX

Every analyzed GENERATED case of the run counts once, all cells and directions
together. At offset d the plot shows the percentage of cases with |offset| <= d
that failed; each point is also labelled with failures/all cases up to that offset.
Default output: <run dir>/cumulative-failures.png.
"""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plot_displacements import FAIL_COLOR, VisualizationError, interactive_backend, load_runs

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def cumulative_failures(cells):
    """Return [(offset, failed with |offset| <= offset, all with |offset| <= offset)]."""
    failed, total = {}, {}
    for _, runs in cells.values():
        for dx, dy, passed in runs:
            offset = max(abs(dx), abs(dy))  # one axis moves per case
            total[offset] = total.get(offset, 0) + 1
            failed[offset] = failed.get(offset, 0) + (not passed)
    points, fails, runs = [], 0, 0
    for offset in sorted(total):
        fails += failed[offset]
        runs += total[offset]
        points.append((offset, fails, runs))
    return points


def percent(failed, total):
    return 100 * failed / total


def slovene(value, digits=1):
    return f'{value:.{digits}f}'.replace('.', ',')


def build_figure(points, title=None):
    figure, axis = plt.subplots(figsize=(7, 4.2), layout='constrained')
    offsets = [p[0] for p in points]
    shares = [percent(failed, total) for _, failed, total in points]
    axis.plot(offsets, shares, color=FAIL_COLOR, linewidth=2, marker='o', markersize=7,
              markeredgecolor='white', markeredgewidth=1.2, zorder=3)
    for (offset, failed, total), share in zip(points, shares):
        axis.annotate(f'{slovene(share)} %\n({failed}/{total})', (offset, share),
                      textcoords='offset points', xytext=(0, 8), ha='center', va='bottom',
                      fontsize=8, color='0.25')
    axis.set_xticks(offsets, [f'{o:g}'.replace('.', ',') for o in offsets])
    axis.set_xlim(0, max(offsets) + 0.3)
    axis.set_ylim(0, max(shares) * 1.25 + 1)
    axis.yaxis.set_major_formatter(lambda value, _: f'{value:.0f} %')
    axis.set_xlabel('Absolutna velikost premika [nm]')
    axis.set_ylabel('Delež neuspešnih scenarijev\n(kumulativno)')
    axis.grid(True, axis='y', color='0.9', linewidth=0.6)
    for side in ('top', 'right'):
        axis.spines[side].set_visible(False)
    if title:
        axis.set_title(title, fontsize=11, parse_math=False)
    return figure


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('run_dir', type=Path, help='workflow run directory (analysis_results/run.*)')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--view', action='store_true',
                      help='show the plot in an interactive window; save nothing')
    mode.add_argument('-o', '--output', type=Path,
                      help='PNG path (default: <run dir>/cumulative-failures.png)')
    args = parser.parse_args(argv)
    output = args.output or args.run_dir / 'cumulative-failures.png'
    title = 'Kumulativni delež neuspešnih scenarijev (vse celice)'
    try:
        points = cumulative_failures(load_runs(args.run_dir))
        if args.view:
            interactive_backend()
        figure = build_figure(points, title)
        try:
            if args.view:
                figure.canvas.manager.set_window_title(title)
                plt.show(block=True)
                return 0
            output.parent.mkdir(parents=True, exist_ok=True)
            figure.savefig(output, format='png', dpi=200)
        finally:
            plt.close(figure)
    except (OSError, VisualizationError, ValueError, ImportError, RuntimeError) as error:
        print(f'error: {error}', file=sys.stderr)
        return 1
    print(f'Saved cumulative plot to {output}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
