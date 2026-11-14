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
