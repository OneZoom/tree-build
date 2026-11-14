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
    pip install -e '.[dev]'

    # Set up git hooks including linting and DVC
    pre-commit install --hook-type pre-push --hook-type post-checkout --hook-type pre-commit

After the first time, you just need to run the `source .venv/bin/activate` each time you want to activate it in a new shell.

To be able to run the pipeline, you'll also need to install `wget`.

## Configuring an existing OneZoom installation

Tree-build can be installed anywhere, independently of OZtree. For database-backed
update commands, create a `config.ini` in the tree-build directory, for example
`~/tree-build/config.ini`. This file is ignored by git:

```ini
[onezoom]
appconfig = ~/www.onezoom.org/applications/OZtree/private/appconfig.ini
image_output_dir = ~/www.onezoom.org/applications/OZtree/static/FinalOutputs/img
```

These are examples: set the paths for your installation. Paths beginning with `~`
refer to the running user's home; relative paths in this file are relative to the
file's directory. The appconfig is the existing OneZoom INI file containing `[db]`
`uri` and, when using Azure cropping, `[azure_vision]` credentials. Keep credentials
in that file, not in tree-build's configuration or the repository. The image output
directory must already exist and be writable.

Run the commands from that directory to use its `config.ini`, for example:

```bash
get_wiki_vernaculars leaf "Panthera leo"
get_wiki_images leaf "Panthera leo" --no-azure-crop
process_image_bits all
```

These commands immediately modify the configured database; image harvesting also
writes images, including uncropped images and crop information, to the configured
directory. They are not an offline import workflow. Use an appropriately restricted
account and check the target before running them on production.

To run from another directory, set `TREE_BUILD_CONFIG` to the absolute path of the
file, for example `export TREE_BUILD_CONFIG="$HOME/tree-build/config.ini"`.
If set, this takes precedence over the current directory's `config.ini`.

`--conf-file` overrides `appconfig` for these commands, and `--output-dir` overrides
`image_output_dir` for image harvesting. The explicit options also work without a
local configuration file. For `get_wiki_images` and `get_wiki_vernaculars`, supply
these options after the `leaf` or `clade` subcommand; for `process_image_bits`,
supply `--conf-file` before its subcommand. If a required path is not configured,
the command fails rather than guessing an OZtree location. Scheduled jobs must
set the working directory or `TREE_BUILD_CONFIG` and use the intended `HOME`,
or pass explicit paths.

Tree building and JS generation do not require this configuration or a running
OZtree database. `make_js_treefiles` requires an explicit `--outdir`.

## Testing

Assuming you have installed the 'dev' dependencies, you should be able to run

    python -m pytest

By default the tests use an isolated temporary SQLite database and mocked APIs,
regardless of machine-local configuration. To test against another database, pass
`--conf-file /path/to/appconfig.ini` explicitly. Such tests modify that database;
use a non-production database. To use real APIs, add `--real-apis` and provide an
appconfig with a valid Azure image cropping key.

## Building the latest tree from OpenTree

This project uses [DVC](https://dvc.org/) to manage the pipeline. The build parameters are defined in `params.yaml` and the pipeline stages are declared in `dvc.yaml`.

### Quick start (using cached outputs)

You'll need to ask for the DVC remote credentials on the OneZoom Slack channel in order to pull cached results. To store the credentials locally, run the following commands:

```bash
dvc remote modify --local onezoom-r2 access_key_id '{ACCESS_KEY_ID}'
dvc remote modify --local onezoom-r2 secret_access_key '{SECRET_ACCESS_KEY}'
```

Then, if someone has already run the pipeline and pushed the results to the DVC remote, you can reproduce the build and any of the intermediate stages without downloading any of the massive source files:

```bash
source .venv/bin/activate
dvc repro --pull
```

DVC will pull only the cached outputs needed for stages that haven't changed. If all stages are cached, nothing needs to be re-run.

### Full build (first time / updating source data)

1. Set `ot_version` in `params.yaml` to the desired OpenTree synthesis version (e.g. `"v16.1"`). Available versions can be found in the [synthesis manifest](https://raw.githubusercontent.com/OpenTreeOfLife/opentree/master/webapp/static/statistics/synthesis.json). The OpenTree tree and taxonomy will be downloaded automatically by the `download_opentree` pipeline stage.

2. Some source files are unversioned so will use cached results unless forced. To force re-download them all with the latest upstream data:

   ```bash
   dvc repro --force download_eol discover_enwiki_sql_url discover_wikidata_url download_and_filter_pageviews
   ```

Note that download_and_filter_wikidata and download_and_filter_pageviews take several hours to run.

3. Run the pipeline and push results to the shared cache:

   ```bash
   dvc repro
   dvc push
   ```

   If you followed the instructions to install pre-commit hooks, the `dvc push` will happen automatically during your git push.

4. Commit `dvc.lock` to git.


## Uploading tree to server

1. A separate build machine can download the inputs and run the DVC pipeline without access
   to the production database. Transfer `data/output_files/` to the server for import.
   The pipeline writes versioned `completetree` and `cut_position_map` JS and gzip files
   to `data/js_output/`. Copy the appropriate files into an OZtree checkout's
   `static/FinalOutputs/data/`, commit them to an OZtree branch, and deploy that
   revision to the web server. Ensure the viewer and database use the same tree version.
   The current DVC JS stage does not generate `dates` files; check the target
   installation's requirements separately.

2. The generated `data/output_files/import_XXXXXX.sql` references the accompanying
   `.csv.mySQL` files by the paths used during the build (normally relative to the
   tree-build repository root). After transfer, run the MySQL client from a directory
   where those paths resolve, or carefully adjust the paths in the SQL. `LOAD DATA
   LOCAL INFILE` reads them on the machine running the client. The script **truncates
   and repopulates** the ordered tables: back up the target, verify the SQL and
   test the import on a staging database before a planned production deployment.

   ```bash
   # Example: from a directory containing the transferred data/output_files/
   echo "SET GLOBAL local_infile=ON;" | mysql -p OneZoom_dev
   mysql --local-infile --host localhost --user onezoom --password --database OneZoom_dev < data/output_files/import_XXXXXX.sql
   ```

3. Check for dups, and if any sponsors are no longer on the tree, using something like the following SQL command:

   ```
   select * from reservations left outer join ordered_leaves on reservations.OTT_ID = ordered_leaves.ott where ordered_leaves.ott is null and reservations.verified_name IS NOT NULL;
   select group_concat(id), group_concat(parent), group_concat(name), count(ott) from ordered_leaves group by ott having(count(ott) > 1)
   ```

### Fill in additional server fields

 11. (15 mins) create example pictures for each node by percolating up. This requires the most recent `images_by_ott` table, so either do this on the main server, or (if you are doing it locally) update your `images_by_ott` to the most recent server version.

    ```
    ${OZ_DIR}/OZprivate/ServerScripts/Utilities/picProcess.py -v
    ```

1. (5 mins) percolate the IUCN data up using

   ```
   ${OZ_DIR}/OZprivate/ServerScripts/Utilities/IUCNquery.py -v
   ```

   (note that this both updates the IUCN data in the DB and percolates up interior node info)

1. (10 mins) If this is a site with sponsorship (only the main OZ site), set the pricing structure using SET_PRICES.html (accessible from the management pages).
1. (5 mins - this does seem to be necessary for ordered nodes & ordered leaves). Make sure indexes are reset. Look at `OZprivate/ServerScripts/SQL/create_db_indexes.sql` for the SQL to do this - this may involve logging in to the SQL server (e.g. via Sequel Pro on Mac) and pasting all the drop index and create index commands.



For detailed step-by-step documentation, see [oz_tree_build/README.markdown](oz_tree_build/README.markdown).
