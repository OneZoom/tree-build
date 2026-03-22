# OneZoom Tree Building repo

This repository contains everything that is needed to build the OneZoom tree and all the other files needed by the backend.
It also contains scripting libraries for harvesting information from wikidata and images from wikimedia commons that can
be used to populate a running OneZoom instance.

## Setting up the environment

The first step to using this repo is to create a Python virtual environment and activate it:

    # From the root of the repo, create a Python environment and activate it
    python3 -m venv .venv
    source .venv/bin/activate

    # Install it
    pip install -e .

After the first time, you just need to run the `source .venv/bin/activate` each time you want to activate it in a new shell.

If you want to run the test suite, make sure the test requirements are also installed, with:

    pip install -e '.[test]'

## Testing

Assuming you have installed the test requirements, you should be able to run

    python -m pytest --conf-file tests/appconfig.ini

Here we have used a basic conf file to create a fake OneZoom database. However, if you wish to test using the
real OneZoom database, you can specify a different path to an appconfig.ini file, or omit the `--conf-file`
option entirely, in which case the test suite will look for `../OZtree/private/appconfig.ini`, which assumes
hat this repository is a sibling to a non-live
[OZtree](https://github.com/OneZoom/OZtree) installation, and that the database used by this OZtree
installation is active.

    python -m pytest  # Uses the "real" OneZoom database - take care!

This uses mocked APIs. You can also run with the real APIs using the `--real-apis` swithc, in whcih case
you will need a valid Azure Image cropping key in your appconfig.ini.

## Building the latest tree from OpenTree

This project uses [DVC](https://dvc.org/) for a cached, repeatable data pipeline. The build parameters (OpenTree version, taxonomy version, etc.) are defined in `params.yaml` and the pipeline stages are declared in `dvc.yaml`.

### Quick start (using cached outputs)

If someone has already run the pipeline and pushed the results to the DVC remote, you can reproduce the build without downloading any of the massive source files:

```bash
source .venv/bin/activate
dvc repro --pull --allow-missing
```

DVC will pull only the cached outputs needed for stages that haven't changed. If all stages are cached, nothing needs to be re-run.

### Full build (first time / updating source data)

1. Update `params.yaml` with the desired OpenTree version numbers. You can check the latest version via the [API](https://github.com/OpenTreeOfLife/germinator/wiki/Open-Tree-of-Life-Web-APIs):

    ```bash
    curl -s -X POST https://api.opentreeoflife.org/v3/tree_of_life/about | grep -E '"synth_id"|"taxonomy_version"'
    ```

2. Download the required source files into `data/` as [documented here](data/README.markdown), then register them with DVC:

    ```bash
    dvc add data/OpenTree/labelled_supertree_simplified_ottnames.tre
    dvc add data/OpenTree/ott3.7.tgz
    dvc add data/Wiki/wd_JSON/latest-all.json.bz2
    dvc add data/Wiki/wp_SQL/enwiki-latest-page.sql.gz
    dvc add data/Wiki/wp_pagecounts/
    dvc add data/EOL/provider_ids.csv.gz
    ```

3. Run the pipeline and push results to the shared cache:

    ```bash
    dvc repro
    dvc push
    ```

4. Commit the `.dvc` files and `dvc.lock` to git.

### Pipeline stages

The pipeline is defined in `dvc.yaml`. Use `dvc dag` to visualize the DAG. Key stages include:

- **preprocess_opentree**, **unpack_taxonomy** -- prepare OpenTree data
- **add_ott_numbers**, **prepare_open_trees**, **build_tree** -- assemble the full newick tree
- **filter_eol**, **filter_wikidata**, **filter_sql**, **filter_pageviews** -- filter massive source files (parallelizable)
- **create_tables** -- map taxa, calculate popularity, produce DB-ready CSVs
- **make_js** -- generate JS viewer files

For detailed step-by-step documentation, see [oz_tree_build/README.markdown](oz_tree_build/README.markdown).
