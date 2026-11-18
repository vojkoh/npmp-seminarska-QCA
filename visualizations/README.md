# Visualizations

## Displacement overview

One figure for a whole workflow run: every displaced cell gets its own subplot,
with **dx** on the x axis and **dy** on the y axis (nm). Each analyzed circuit is
one dot, **blue circle = PASS** and **red cross = FAIL**. A `+` marks the
original position. Rows group the cells (wires, negator, upper and lower
majority gate) side by side, and all subplots share their axis limits so they
can be compared directly. **+y is down in QCADesigner-E**, so the y axis is
inverted to match the circuit layout.

Input is a run directory created by `just run`
(`analysis_results/run.*`, containing `circuits/manifest.csv` and
`results/<case_id>/full-summary.json`). `OVERLAP` cases were never simulated
and are not drawn. Generated cases without a readable verdict are skipped with
a warning.

```sh
just --justfile visualizations/justfile viz-setup
just viz                                   # newest run -> <run>/displacement-overview.png
just viz analysis_results/run.XXXXXX       # a specific run
just viz-view                              # interactive window, nothing saved
just --justfile visualizations/justfile viz analysis_results/run.XXXXXX out.png
just --justfile visualizations/justfile viz-test
```

The interactive view reuses the graph component's backend selection and needs a
desktop session with Tk or Qt.

## Cell layout

`plot_layout.py` draws the unchanged `qca-files/demultiplexer_12.qca` and names
every displaced cell from `generator/cells.yaml` (it reuses the generator's
parser, so the names always match what is displaced). In each majority gate the
letters follow reading order: **a** top-left, **b** top-right, **c** the centre
(majority) cell, **d** bottom-left, **e** bottom-right. The fixed-polarization
inputs are M0a and M1d. Colours match QCADesigner: clock 0 green, 1 magenta,
2 cyan, 3 white, fixed orange, input blue, output yellow. Inputs/outputs show
their labels (S, D, Y0, Y1), and the small number in each cell is its clock zone.

```sh
just layout                    # -> analysis_results/cell-layout.png
just layout path/to/out.png
just layout-view               # interactive window, nothing saved
```

`analysis_results/` is removed by `just clean`; save the diagram elsewhere (e.g.
into the report's image directory) to keep it.
