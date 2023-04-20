# OneZoom Tree Building repo

This repository contains everything that is needed to build the OneZoom tree and  all the other files needed by the backend.

## Setting up the environment

The first step to using this repo is to create a Python virtual environment and activate it:

    # From the root of the repo, create a Python environment and activate it
    python3 -m venv .venv
    source .venv/bin/activate

    # Install it
    pip install -e .

## Downloading all required files

You then need to download various files from the internet, as [documented here](data/README.markdown).

## Building the tree

Now you are set up to actually build the tree and other backend files, by following [these instructions](oz_tree_build/README.markdown)