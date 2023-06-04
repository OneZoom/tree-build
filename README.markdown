# OneZoom Tree Building repo

This repository contains everything that is needed to build the OneZoom tree and  all the other files needed by the backend.

## Setting up the environment

The first step to using this repo is to create a Python virtual environment and activate it:

    # From the root of the repo, create a Python environment and activate it
    python3 -m venv .venv
    source .venv/bin/activate

    # Install it
    pip install -e .

After the first time, you just need to run the `source .venv/bin/activate` each time you want to activate it in a new shell.

## Testing

To run the test suite, from the root of the repo, and from your activated environment, run

    python -m pytest

## Downloading required files

To actually build a full tree of life, you first need to download various files from the internet, as [documented here](data/README.markdown).

## Building the tree

Once data files are downloaded, you should be set up to actually build the tree and other backend files, by following [these instructions](oz_tree_build/README.markdown)