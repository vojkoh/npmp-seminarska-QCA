# Demultiplexer simulation analyzer

Python 3.10+ and NumPy are required. All implementation, fixtures and documentation
are confined to this directory. No displacement or simulator automation is included.

## Commands (from repository root)

```sh
just analysis-setup
just analysis-test
just analysis-benchmark
# Only after saving a real simulation file:
just analysis simulation-results.txt
just analysis-full simulation-results.txt
```

Setup creates the local `analysis/.venv` and installs dependencies there, without
modifying the system Python (compatible with PEP 668). Run setup once, or again
after dependency changes. No activation is needed. Tests and the synthetic
benchmark need no simulation file. Analysis requires an explicit file path;
quote paths containing spaces. Recipes stop on errors and preserve analyzer
exit codes through logging. Each run overwrites its corresponding output files.

For custom CLI options, use `analysis/.venv/bin/python analysis/analyze.py`
followed by the simulation path and options.

Recipes display logs in the terminal. Generated exports and logs live in `analysis_results/` at repository
root (ignored by Git). Delete that directory to clear results; `just clean`
also removes it and the virtual environment, along with other ignored files;
rerun setup afterward. The input simulation stays
outside this directory. Explicit CLI export paths remain user-configurable.

Options include `--threshold` (0.5), `--clock-low` (3.8e-23),
`--clock-high` (9.8e-22), and `--clock-tolerance` (1e-6, a **fraction of
HIGH minus LOW**, never NumPy's default absolute tolerance). `--debug` aliases
`--verbose`. Warnings and timing diagnostics go to stderr; tables go to stdout;
CSV and JSON go only to their specified files.
JSON includes the explicit overall `status` (PASS, FAIL or INCOMPLETE_DATA),
alongside row statuses, coverage, metrics and timings. Fatal input errors return
2 with a stderr diagnostic; they do not produce a JSON error report.

Exit codes: **0** complete passing experiment; **1** complete experiment showing
circuit failure; **2** malformed/unreadable input, unreliable clock, invalid
configuration, or incomplete truth table/delayed measurements. Incomplete analyses
that have some aligned measurements still produce tables and exports, with overall
`INCOMPLETE_DATA`. No aligned measurements is an analysis error.

## Format and parser

The format was inspected in the simulator writer at
[`simulation_data_serialize`](../QCADesignerE/src/fileio.c:567) and
[`serialize_trace`](../QCADesignerE/src/fileio.c:584). Simulation output contains
simulation data, signal traces and four separately stored clock traces; the declared
trace count excludes clocks. Labels are unquoted metadata. Numerical blocks contain
whitespace-separated scientific-notation values, terminated by matching hash tags.
Bus-layout and other tags are structurally checked but not interpreted.

The parser reads the file once. Numerical text is buffered so counts, labels,
sections and traces may occur in arbitrary order. Full numeric lexical validation
precedes NumPy conversion, preventing silent truncation. Counts, missing/duplicate
labels, missing data, tag nesting and finite values are checked for all traces.
Core simulation sections reject unexpected children and stray content; nested
tags cannot hide invalid numerical tokens. The clock section must contain exactly
Clock 0 through Clock 3, and those labels cannot appear as signal traces.
If supplied, drawtrace must be TRUE/FALSE and trace_function must be an integer.
Ignored clocks are validated but their arrays are not retained. Additional signal
traces get statistics at the input hold, without an implicit propagation delay.
This implementation buffers the file's numerical text in memory; it is not a
bounded-memory streaming parser. Whole-block NumPy allocation uses the validated
declared count rather than repeated resizing.

## Clock and alignment

Clock 3 is normalized to LOW=0 and HIGH=1. Contiguous samples within the low
tolerance form half-open hold intervals, including both plateau endpoints but
excluding transitions. Boundary holds lacking either edge are reported as partial
and excluded. Their indices are retained, not renumbered, so alignment never bridges
an excluded interval. The complete first input hold is **not** dropped.
Outputs Y0/Y1 use exactly the next indexed hold; no wraparound occurs.
Inclusive tolerance comparisons allow eight machine epsilons in normalized units
for arithmetic roundoff, including in out-of-range diagnostics.
The callable analysis API accepts an internal nonnegative integer delay.

Validation reports out-of-range samples, transition reversals, missing plateaus,
unexpected sequences, one-sample holds and length/period variation exceeding
the larger of one sample or 5% of the median. Minor anomalies warn rather than
discarding a simulation. No LOW, no HIGH or no complete holds is fatal.
Boundary transitions need not start at HIGH. Detection is sample-based: transitions
shorter than the sampling interval cannot be reconstructed. Completely absent
cycles cannot be unambiguously reconstructed from the saved waveform; period
inconsistency warns and requires research review before trusting alignment.
Separated LOW plateaus without an intervening sampled HIGH are fatal: counting
a brief LOW excursion as another cycle could silently shift delayed alignment.

## Logic, results and metrics

Per-window signed minimum, maximum, median, mean and count are reported.
Means at or beyond +/-threshold classify as 1/0; other means are undefined.
Stability requires **every** sample to remain beyond the same threshold as its
mean. Undefined means are not stable. Mean logic and stability are exported
separately, including for input and extra traces.

Expected outputs are Y0 = D AND NOT S and Y1 = D AND S. Status precedence is
INVALID_INPUT, UNDEFINED_OUTPUT, WRONG_LOGIC, UNSTABLE_OUTPUT, PASS; individual
statistics retain other concurrent issues. Unstable inputs are invalid even if
their means classify. Only valid input measurements establish coverage.
The default retains repeats and failures until all four inputs and their delayed
outputs have been measured. `--full` processes all available aligned pairs.

Mean absolute output polarization weights each analyzed output measurement
equally (including retained repeats), not each sample or distinct combination.
Minimum signed mean and worst signed sample multiply by the expected output sign;
negative values indicate wrong direction. Invalid-input rows have no expected
output or signed metrics. Output totals include these rows, but correctness does
not. Correct outputs require both correct mean logic and stability. A combination
is correct only when every retained measurement for it passes. Circuit pass
requires all four combinations and all retained rows passing.

## Verification and benchmark limitations

No supplied saved simulation was found, including hidden/ignored contents of this
directory and a workspace-wide saved-output-marker search. Therefore **no real
baseline verification, alignment verification, or real-file benchmark is claimed**.
Run a known-correct unmodified demultiplexer simulation before research use.

The independent review checked the documented analysis contract against the
analyzer, tests and actual serialization source. The original full parent request
is not present in this review's conversation, so exhaustive conformance to any
requirements omitted from this document cannot be certified.

The original 18 synthetic tests passed in **0.063 seconds** before review fixes.
The expanded **28 tests passed in 0.099 seconds** on the review machine. They cover
the original scenarios plus late
metadata/reordered sections, malformed/non-finite numbers, duplicate/missing
metadata and labels, signed metrics, unknown traces, preserved index gaps, CLI
exports and exit codes, hidden nested content, misplaced clock labels, exact
tolerance boundaries, false cycles, partial end holds, retained failing repeats,
invalid-input aggregates, status precedence and parsed machine-readable exports.
Fixtures use the inspected writer's format, not simulator execution.

The exact benchmark command above creates and removes a synthetic 1,674,350-byte
file containing 12,807 samples and eight traces, two truth tables plus a drain
cycle. The default analysis stops after the first exhaustive table. Across ten
review runs, median parsing was **0.050919 s** (range 0.049528–0.083370 s),
analysis **0.001356 s** (range 0.001121–0.008059 s), and combined **0.052308 s**
(range 0.050874–0.091429 s).
Combined time excludes fixture generation, interpreter/import startup and report
serialization. CLI verbose timings likewise cover parsing and numerical analysis,
not process startup or exports. No multiprocessing is used.
