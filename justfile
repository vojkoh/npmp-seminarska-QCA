set dotenv-load

baseline := "qca-files/demultiplexer_12.qca"
analysis_python := "analysis/.venv/bin/python"
workflow_results := "analysis_results"

# Validate the original, generate one batch, then analyze every generated case.
[positional-arguments]
@run *args:
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p "{{workflow_results}}"
    run_dir=$(mktemp -d "{{workflow_results}}/run.XXXXXX")
    echo "Run directory: $run_dir"
    just --justfile "{{justfile()}}" validate-baseline "$run_dir/baseline"
    just --justfile "{{justfile()}}" generate "$run_dir/circuits" "$@"
    just --justfile "{{justfile()}}" analyze-generated "$run_dir/circuits" "$run_dir/results"

# Create local simulator configuration without overwriting existing settings.
env-init:
    #!/usr/bin/env sh
    set -eu
    if [ -e .env ]; then
        echo '.env already exists; leaving it unchanged.'
        exit 0
    fi
    set -C
    cat > .env <<EOF
    QCA_EXECUTABLE=""
    QCA_FILE="$(pwd)/qca-files/demultiplexer_12.qca"
    QCA_OPTIONS_FILE="$(pwd)/qca-files/bistable-options.txt"
    EOF
    echo 'Created .env; adjust QCA_EXECUTABLE for your installation.'

qca-run:
    just --justfile qca-files/justfile run

[positional-arguments]
analysis simulation output_dir="analysis_results":
    #!/usr/bin/env bash
    set -euo pipefail
    just --justfile analysis/justfile analysis-setup
    just --justfile analysis/justfile analysis-full "$1" "$2"

graph g:
    just -f graph/justfile graph-view {{g}}

graph-all:
    #!/usr/bin/env bash
    set -euo pipefail
    shopt -s nullglob
    files=(qca-files/simulation-000*.txt)
    if (( ${#files[@]} == 0 )); then
        echo "No files match qca-files/simulation-000*.txt" >&2
        exit 1
    fi
    for f in "${files[@]}"; do
        just --justfile graph/justfile graph-view "$f"
    done

# Install the existing generator and analyzer dependencies (no graph setup).
workflow-setup:
    just --justfile analysis/justfile analysis-setup
    just --justfile generator/justfile setup

# Remove only conventional output/cache directories; keep configuration and venvs.
clean:
    rm -rf -- analysis_results generator/generated
    rm -rf -- .pytest_cache analysis/__pycache__ generator/__pycache__ generator/.pytest_cache graph/__pycache__

# Simulate the unchanged original and require an actual complete PASS result.
validate-baseline output_dir: (_analyze-circuit baseline output_dir "true")

# Generate the entire requested batch once; output must be new or empty.
[positional-arguments]
generate output *args:
    #!/usr/bin/env bash
    set -euo pipefail
    output=$(realpath -m "$1")
    shift
    just --justfile generator/justfile generate "$@" --output "$output"

# Analyze only GENERATED entries in this batch's manifest, never a global glob.
[positional-arguments]
analyze-generated batch output_dir:
    #!/usr/bin/env bash
    set -euo pipefail
    batch="$1"
    output_dir="$2"
    test -f "$batch/manifest.csv" || { echo "ERROR: batch manifest not found: $batch/manifest.csv" >&2; exit 2; }
    mkdir -p "$(dirname "$output_dir")"
    mkdir "$output_dir" || { echo "ERROR: results directory must be new: $output_dir" >&2; exit 2; }
    {{analysis_python}} -c 'import csv, sys; rows = csv.DictReader(open(sys.argv[1], newline="")); print("\n".join(r["circuit_path"] for r in rows if r["status"] == "GENERATED"))' "$batch/manifest.csv" > "$output_dir/circuits.txt"
    count=0
    while IFS= read -r circuit; do
        [[ -n "$circuit" ]] || continue
        case_id=$(basename "$circuit" .qca)
        just --justfile "{{justfile()}}" _analyze-circuit "$batch/$circuit" "$output_dir/$case_id"
        # Enable after graph-setup: export this circuit's saved simulation traces.
        # just --justfile graph/justfile graph "$output_dir/$case_id/simulation-0000.txt" "$output_dir/$case_id/graphs"
        count=$((count + 1))
    done < "$output_dir/circuits.txt"
    [[ "$count" -gt 0 ]] || { echo "ERROR: no generated circuits in $batch/manifest.csv" >&2; exit 2; }
    echo "Analyzed $count generated circuits. Results: $output_dir"

# A complete FAIL is a successful experiment; missing/incomplete results are errors.
[positional-arguments]
_analyze-circuit circuit output_dir require_correct="false":
    #!/usr/bin/env bash
    set -euo pipefail
    label="circuit analysis"
    if [[ "$3" == true ]]; then
        label="baseline validation"
        echo "Validating baseline: $1"
    fi
    circuit=$(realpath "$1")
    mkdir -p "$(dirname "$2")"
    mkdir "$2" || { echo "ERROR: results directory must be new: $2" >&2; exit 2; }
    output_dir=$(realpath "$2")
    if ! just --justfile qca-files/justfile run "$circuit" "$output_dir" > "$output_dir/simulation.log" 2>&1; then
        echo "ERROR: $label: simulator failed for $1; see $output_dir/simulation.log" >&2
        exit 2
    fi
    simulation="$output_dir/simulation-0000.txt"
    test -s "$simulation" || { echo "ERROR: $label: no fresh simulation at $simulation; see $output_dir/simulation.log" >&2; exit 2; }
    status=0
    just --justfile analysis/justfile analysis-full "$simulation" "$output_dir" > "$output_dir/analysis-command.log" 2>&1 || status=$?
    if ! verdict=$({{analysis_python}} -c 'import json, sys; print(json.load(open(sys.argv[1]))["status"])' "$output_dir/full-summary.json"); then
        echo "ERROR: $label: analyzer exited $status without a readable verdict for $1; see $output_dir/analysis-command.log" >&2
        exit 2
    fi
    case "$status:$verdict" in
        0:PASS) echo "CORRECT: $1 (PASS)" ;;
        1:FAIL)
            echo "INCORRECT: $1 (FAIL; expected experimental outcome)"
            if [[ "$3" == true ]]; then
                echo "ERROR: baseline validation failed: the original circuit must PASS; generation has not run. See $output_dir/full-analysis.log" >&2
                exit 2
            fi
            ;;
        *)
            echo "ERROR: $label: analyzer exit $status, verdict $verdict for $1; see $output_dir/analysis-command.log" >&2
            exit 2
            ;;
    esac
