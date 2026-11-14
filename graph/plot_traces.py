"""Plot selected signals and clocks in a QCADesigner simulation save file.

Install: python -m pip install -r graph/requirements.txt
Usage: python graph/plot_traces.py qca-files/demux12-results [-o OUTPUT_DIR] [--include-clocks]
View only: python graph/plot_traces.py qca-files/demux12-results --view [--include-clocks]
Or: just -f graph/justfile graph-view qca-files/demux12-results --include-clocks
Export via just: just -f graph/justfile graph qca-files/demux12-results "" --include-clocks
Clocks 0, 1, and 2 are excluded by default; Clock 3 remains selected.
View mode stacks one graph per row in a single window.
Viewing requires a desktop session and a GUI toolkit (e.g. Tk or Qt).
MPLBACKEND can select the interactive backend. No graph files are saved.
Default output: <input filename>-graphs beside the input file.
Empty traces are skipped with a warning; malformed files exit unsuccessfully.
"""
import argparse
import os
from pathlib import Path
import re
import sys

# Reuse the repository's validated save-file parser, independent of the cwd.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'analysis'))
from analyze import AnalysisError, parse_simulation_file

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def trace_filename(index, name):
    """Ordinal prefixes disambiguate labels that sanitize to the same name."""
    safe = re.sub(r'[^A-Za-z0-9_-]+', '_', name).strip('_')[:100] or 'trace'
    return f'{index:04d}_{safe}.png'


def selected_traces(simulation, include_clocks=False):
    """Retain original ordering and labels, filtering only clocks 0 through 2."""
    excluded = {f'{prefix} {i}' for prefix in ('CLOCK', 'Clock') for i in range(3)}
    return [(name, values) for name, values in simulation.traces.items()
            if include_clocks or name not in excluded]


def label_axis(axis, name):
    """Use horizontal labels, padded signal limits, and a subtle zero guide."""
    axis.set_xlabel('Sample index')
    axis.set_ylabel(name, rotation=0, labelpad=35, va='center', parse_math=False)
    if not re.fullmatch(r'(?:CLOCK|Clock) \d+', name):
        axis.set_ylim(-1.1, 1.1)
        axis.axhline(0, color='0.5', linewidth=0.6, alpha=0.3, zorder=0)


def plot_traces(simulation, output, include_clocks=False):
    output.mkdir(parents=True, exist_ok=True)
    saved = []
    for index, (name, values) in enumerate(selected_traces(simulation, include_clocks)):
        if not len(values):
            print(f'warning: skipping empty trace {name!r}', file=sys.stderr)
            continue
        figure, axis = plt.subplots()
        try:
            axis.plot(range(len(values)), values)
            label_axis(axis, name)
            figure.tight_layout()
            path = output / trace_filename(index, name)
            figure.savefig(path, format='png')
            saved.append(path)
        finally:
            plt.close(figure)
    return saved


def interactive_backend():
    """Try installed desktop backends, never silently display through Agg."""
    requested = os.environ.get('MPLBACKEND')
    candidates = [requested] if requested else ['QtAgg', 'TkAgg', 'GTK3Agg', 'MacOSX']
    for backend in candidates:
        try:
            # Reject noninteractive backends, including inline/notebook modes.
            if backend.lower() not in {'qtagg', 'qt5agg', 'tkagg', 'gtk3agg',
                                       'gtk4agg', 'wxagg', 'macosx'}:
                continue
            plt.switch_backend(backend)
            return
        except (ImportError, RuntimeError, ValueError):
            continue
    raise ValueError('interactive view unavailable: use a desktop session with '
                     'a Matplotlib GUI toolkit (Tk or Qt); check MPLBACKEND. '
                     'Omit --view for headless PNG export.')


def view_traces(simulation, include_clocks=False):
    """Show one window and block until closed; never save graph files."""
    traces = []
    for name, values in selected_traces(simulation, include_clocks):
        if len(values):
            traces.append((name, values))
        else:
            print(f'warning: skipping empty trace {name!r}', file=sys.stderr)
    if not traces:
        print('warning: no nonempty traces to view', file=sys.stderr)
        return
    interactive_backend()
    figure, axes = plt.subplots(len(traces), 1, squeeze=False,
                                figsize=(10, 2.5 * len(traces)))
    try:
        for axis, (name, values) in zip(axes.flat, traces):
            axis.plot(range(len(values)), values)
            label_axis(axis, name)
        figure.tight_layout()
        plt.show(block=True)
    finally:
        plt.close(figure)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('simulation', type=Path, help='simulation save file')
    parser.add_argument('--include-clocks', action='store_true',
                        help='include clocks 0, 1, and 2 (excluded by default; Clock 3 is always selected)')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--view', action='store_true',
                      help='show selected traces stacked vertically in one interactive window; save nothing')
    mode.add_argument('-o', '--output-dir', type=Path,
                        help='default: <input filename>-graphs beside input')
    args = parser.parse_args(argv)
    output = args.output_dir or args.simulation.with_name(args.simulation.name + '-graphs')
    try:
        simulation = parse_simulation_file(args.simulation, for_plotting=True)
        if args.view:
            view_traces(simulation, include_clocks=args.include_clocks)
            return 0
        plt.switch_backend('Agg')
        saved = plot_traces(simulation, output, include_clocks=args.include_clocks)
    except (OSError, UnicodeError, AnalysisError, ValueError, ImportError, RuntimeError) as error:
        print(f'error: {error}', file=sys.stderr)
        return 1
    if not saved:
        print('warning: no nonempty traces to plot', file=sys.stderr)
    print(f'Saved {len(saved)} graphs to {output}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
