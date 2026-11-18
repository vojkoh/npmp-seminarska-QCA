# Displacement overview

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
