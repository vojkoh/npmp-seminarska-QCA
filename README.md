# npmp-seminarska-QCA

This it the repo containing files for a QCA seminar at NPMP course at University of Ljubljana, Faculty of computer science. 
Authors: Vojko Hysz, Matic Poženel, Gašper Suhadolnik

## Circuit generation and analysis

Use the root [justfile](justfile) with Bash, Python 3.10+, and `just` installed.
Configure the native simulator using the existing environment setup, then install
the existing analyzer (NumPy) and generator (PyYAML) dependencies:

```sh
just env-init
# Set QCA_EXECUTABLE and QCA_OPTIONS_FILE in .env for your installation.
just workflow-setup
just run
# Or simply: just
```

Both `just` and `just run` execute the same complete workflow, creating a fresh,
ignored directory under `analysis_results/`:

1. Simulate the unchanged [original circuit](qca-files/demultiplexer_12.qca)
   using the configured BISTABLE options, one simulation, and zero radial tolerance.
   Run the full analyzer on that fresh simulation and require its actual `PASS`.
   An incorrect, incomplete, or failed baseline stops the workflow before generation.
2. Invoke the [generator](generator/README.md) **once** for the entire batch.
   By default this uses all currently permitted cells, directions, and distances.
   Overlapping geometries are recorded in the manifest but do not produce circuits.
3. Simulate and analyze every `GENERATED` entry in this run's manifest. Neither
   previous runs nor unrelated circuit files are included. Each circuit prints
   `CORRECT` or `INCORRECT`; a complete analyzer `FAIL` is an expected experimental
   outcome and does not stop later cases. Simulator failures, missing reports,
   incomplete data, or other execution errors stop with an explicit `ERROR`.

The printed run directory contains `baseline/`, `circuits/manifest.csv`, and
`results/<case_id>/`. Each analyzed circuit retains its fresh `simulation-0000.txt`,
simulator log, full analysis log, measurements CSV, and summary JSON. Existing
results are never reused or overwritten. Analyzer exit codes and JSON verdicts
must agree: 0/`PASS` and 1/`FAIL` are valid results; other combinations are errors.
See the [analyzer documentation](analysis/README.md) for the correctness criteria.

Generator selection flags can narrow a complete workflow without changing its
baseline-first ordering:

```sh
just run --cells W1 --distances 1,5
```

The stages can also be run independently (output paths are relative to the root):

```sh
just validate-baseline analysis_results/baseline-check
just generate analysis_results/manual/circuits --cells W1 --distances 1,5
just analyze-generated analysis_results/manual/circuits analysis_results/manual/results
just analysis analysis_results/baseline-check/simulation-0000.txt
```

Generation requires a new or empty circuit directory; baseline and batch-analysis
result directories must be new. Independent batch analysis does not revalidate the
baseline. To repeat an analysis, choose a different results directory.

**Graphs are disabled.** The batch-analysis loop includes a commented invocation
of the existing [graph export recipe](graph/justfile). To enable it, first run
`just --justfile graph/justfile graph-setup`, then uncomment that invocation.
It uses the same saved simulation as the analyzer and exports into that case's
`graphs/` directory; normal workflow execution neither sets up nor invokes graphs.

### Displacement overview

`just run` does not plot. Afterwards, `just viz [RUN_DIR]` (default: newest run)
plots every displaced cell's results as PASS/FAIL dots on a dx/dy grid and saves
`<run dir>/displacement-overview.png`; `just viz-view [RUN_DIR]` opens it in a
window without saving. `just layout` saves a labelled diagram of which cell is
W1, N1, M0a, ... (`analysis_results/cell-layout.png`). Dependencies are
installed by `just workflow-setup`. See the [visualization documentation](visualizations/README.md).

### Cleanup

Run `just clean` from the repository root to remove `analysis_results/` (including
workflow runs and temporary verification logs/files), `generator/generated/`, and
the root/component Python and pytest caches. Cleanup is safe to repeat when those
directories are absent and handles output names containing spaces. It preserves
source files, configuration, virtual environments and installed dependencies, and
tracked fixtures such as `qca-files/demux12-results`. Custom output directories
outside these conventional locations are left untouched; remove those explicitly
when no longer needed. No component currently provides a separate cleanup recipe.
