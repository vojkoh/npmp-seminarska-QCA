# Single-cell QCA displacement generator

Moves **one cell per circuit**, always independently from the fixed original
[`demultiplexer_12.qca`](../qca-files/demultiplexer_12.qca). No simulation,
random sampling, simultaneous displacement, or result analysis is performed.

## Run from this directory

Requires Python 3.10+ and PyYAML. With just installed:

```sh
just setup
just generate --dry-run
just generate --output generated/systematic
just test
```

Without just, create the environment and install the single dependency:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install 'PyYAML>=6.0'
.venv/bin/python generate.py --dry-run
```

Select a subset, or a single specific displacement:

```sh
just generate --cells W1,N1,M0c --distances 1,2,3 --output generated/test
just generate --cells W1 --directions +x --distances 1 --output generated/manual
just generate --cells W1 --directions=-x --distances 1 --output generated/left
```

Use an equals sign when a direction argument starts with a minus sign.
The default distances are **0.5, 1, 1.5, 2, 3, 4, 5 nm**. All paths supplied
on the command line are relative to the current directory; just always runs
here. The original and configuration paths are relative to the script, not
the current directory. Direct invocation from the repository root also works:

```sh
generator/.venv/bin/python generator/generate.py --cells W1 --directions +x --distances 1 --output generated/manual
```

## Cell configuration and geometry

[`cells.yaml`](cells.yaml) contains the previous generator's verified 15-cell
mapping: four wire cells, one inverter cell, and five cells in each majority
gate. External inputs/outputs are excluded; both fixed-polarization gate cells
are included. Each entry has its semantic identifier, original coordinates in
nm, group, and permitted directions. Edit its direction list to restrict a
cell. Coordinates must uniquely match the original; duplicate physical-cell
assignments and explicitly requested forbidden directions are rejected.

**+x moves right, -x left, +y down, -y up** in QCADesigner-E. The reference
image did not specify directional restrictions, so all four directions are
initially enabled; this does not imply every distance is geometrically valid.

Only the selected cell's center, physical bounding-box position, four quantum
dots, and attached label geometry are translated. All other serialized content
is preserved verbatim, including dimensions, clock zones, orientation, fixed
polarization charges, layers, and the other 26 cells.

The moved rectangle is checked against the other physical cells on its layer,
using dimensions read from the original. Interior overlap on both axes is
rejected; boundary contact is allowed, with a **1e-9 nm** numerical tolerance.
Labels are not obstacles. Each case starts from the original, never a variant.

## Outputs and manifest

The output directory must be new or empty; existing files are never
overwritten. Valid circuits have deterministic names such as
**W1_px_0p5nm**; direction tokens are **px, nx, py, ny**.

[`manifest.csv`](generated/systematic/manifest.csv) is the only accompanying
file: one baseline reference row and one row per attempted configuration.
Its columns are:

```text
case_id,cell_id,cell_group,direction,displacement_nm,dx_nm,dy_nm,original_x_nm,original_y_nm,new_x_nm,new_y_nm,status,circuit_path
```

- **BASELINE** references the unchanged original; displacement fields are empty.
- **GENERATED** identifies a valid circuit and its exact displacement.
- **OVERLAP** records a rejected geometry; its circuit path is empty, and no
  circuit is written. It is not a functional failure.

All circuit paths are relative to the manifest's directory, including the
baseline reference. With the supplied configuration, the default grid has
**420 candidates: 378 valid and 42 overlaps**. Dry-run computes those same
counts without creating directories, circuits, or a manifest.

## Validation before simulation

The tests check all 15 mappings, complete translations (including fixed-cell
labels), single-cell-only changes, unchanged unrelated text, touching/overlap,
manifest accuracy, and original-file preservation. Run **just test**.

The existing native simulator successfully loaded and simulated a baseline
copy and 1 nm leftward displacements of W1, M0a, and M1d, using BISTABLE,
one run, and displacement tolerance zero. This checks file acceptance, not
functional fault tolerance. Interactive editor appearance was not checked;
visually inspect representative variants before the full study. The generator
does not invoke or modify the runner or analyzer.
