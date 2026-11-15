set dotenv-load

# Resolve recipe paths from the project root, not this justfile's directory.
@run:
    echo Specify a recipe...

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
