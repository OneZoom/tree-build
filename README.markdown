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

To be able to run the pipeline, you'll also need to install `wget`.

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

This project uses [DVC](https://dvc.org/) to manage the pipeline. The build parameters are defined in `params.yaml` and the pipeline stages are declared in `dvc.yaml`.

### Quick start (using cached outputs)

You'll need to ask for the DVC remote credentials on the OneZoom Slack channel in order to pull cached results.
Then, if someone has already run the pipeline and pushed the results to the DVC remote, you can reproduce the build and any of the intermediate stages without downloading any of the massive source files:

```bash
source .venv/bin/activate
dvc repro --pull --allow-missing
```

DVC will pull only the cached outputs needed for stages that haven't changed. If all stages are cached, nothing needs to be re-run.

### Full build (first time / updating source data)

1. Set `ot_version` in `params.yaml` to the desired OpenTree synthesis version (e.g. `"v16.1"`). Available versions can be found in the [synthesis manifest](https://raw.githubusercontent.com/OpenTreeOfLife/opentree/master/webapp/static/statistics/synthesis.json). The OpenTree tree and taxonomy will be downloaded automatically by the `download_opentree` pipeline stage.

2. Some source files are unversioned so will use cached results unless forced. To force re-download them all with the latest upstream data:

   ```bash
   dvc repro --force download_eol download_wikipedia_sql download_and_filter_wikidata download_and_filter_pageviews
   ```

Note that download_and_filter_wikidata and download_and_filter_pageviews take several hours to run.

3. Run the pipeline and push results to the shared cache:

   ```bash
   dvc repro
   dvc push
   ```

4. Commit `dvc.lock` to git.

For detailed step-by-step documentation, see [oz_tree_build/README.markdown](oz_tree_build/README.markdown).
