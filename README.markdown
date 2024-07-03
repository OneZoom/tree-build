# OneZoom Tree Building repo

This repository contains everything that is needed to build the OneZoom tree and all the other files needed by the backend.

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

    pytest

This will look for a config file to specify the database to use for testing. By default this will look
in `../OZtree/private/appconfig.ini`, assuming that this repository is a sibling to a non-live
[OZtree](https://github.com/OneZoom/OZtree) installation, and that the database used by this OZtree
installation is active. Alternatively (e.g. if the plain `pytest` command is giving errors, or if you do not
wish to use your OneZoom database for unit testing purposes), a config file
that uses a SQLite database is provided in the `tests` directory, and the following command can be used
which should always work without error

    pytest --conf-file tests/appconfig.ini

## Building the latest tree from OpenTree

### Setup

We assume that you want to build a OneZoom tree based on the most recent online OpenTree version.
You can check the most recent version of both the synthetic tree (`synth_id`) and the taxonomy (`taxonomy_version`) via the
[API](https://github.com/OpenTreeOfLife/germinator/wiki/Open-Tree-of-Life-Web-APIs) e.g. by running `curl -X POST https://api.opentreeoflife.org/v3/tree_of_life/about`. Later in the build, we use specific environment variables set to these version numbers. Assuming you are in a bash shell or similar, you can set them as follows:

```
OT_VERSION=14_9 #or whatever your OpenTree version is
OT_TAXONOMY_VERSION=3.6
OT_TAXONOMY_EXTRA=draft1 #optional - the draft for this version, e.g. `draft1` if the taxonomy_version is 3.6draft1
```

### Download

Constructing the full tree of life requires various files downloaded from the internet. They should be placed within the appropriate directories in the `data` directory, as [documented here](data/README.markdown).

### Building the tree

Once data files are downloaded, you should be set up to actually build the tree and other backend files, by following [these instructions](oz_tree_build/README.markdown).
