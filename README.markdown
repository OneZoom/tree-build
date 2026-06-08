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

## Testing

Assuming you have installed the 'dev' dependencies, you should be able to run

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

1. If you are running the tree building scripts on a different computer to the one running the web server, you will need to push the `completetree_XXXXXX.js`, `completetree_XXXXXX.js.gz`, `cut_position_map_XXXXXX.js`, `cut_position_map_XXXXXX.js.gz`, `dates_XXXXXX.js`, `dates_XXXXXX.js.gz` files onto your server, e.g. by pushing to your local Github repo then pulling the latest github changes to the server.

2. (15 mins) load the CSV tables into the DB. Use the script generated in `data/output_files/import_XXXXXX.sql` to truncate and repopulate ordered_leaves/nodes/etc.

   ```
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
