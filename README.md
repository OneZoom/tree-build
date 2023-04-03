# OneZoom Tree Building repo

This repository contains all the logic to build the OneZoom tree, as well as all the
other files needed by the backend.

## Setting up the environment

Your first step to using this repo is to create a Python virtual environment and activate it:

    # Create a Python environment and activate it
    python3 -m venv .venv
    source .venv/bin/activate

    # Install it
    pip install -e .

    # Set an environment variable pointing to the data folder
    export OZDATA="$(dirname "$VIRTUAL_ENV")/data"

TODO: add more to this