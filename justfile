# Resolve recipe paths from the project root, not this justfile's directory.
@run:
    echo Specify a recipe...

[positional-arguments]
analysis simulation:
    #!/usr/bin/env bash
    set -euo pipefail
    cd analysis
    just analysis-setup
    just analysis-full {{simulation}}

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
