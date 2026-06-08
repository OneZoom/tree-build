# Introduction

Creating a bespoke OneZoom tree involves a number of steps, as documented below. These take an initial tree, map taxa onto Open Tree identifiers, add subtrees from the OpenTree of Life, resolve polytomies and delete subspecies, and calculate mappings to other databases together with creating wikipedia popularity metrics for all taxa. Finally, the resulting tree and database files are converted to a format usable by the OneZoom viewer. Mapping and popularity calculations require various large files to be downloaded e.g. from wikipedia, as [documented here](../data/README.markdown).

The instructions below are primarily intended for creating a full tree of all life on the main OneZoom site. If you are making a bespoke tree, you may need to tweak them slightly.

The output files created by the tree building process (database files and files to feed to the js, and which can be loaded into the database and for the tree viewer) are saved in `data/output_files`.

## Using DVC (recommended)

The entire build is defined as a [DVC](https://dvc.org/) pipeline in `dvc.yaml`, with parameters in `params.yaml`. This means you can reproduce the full build with a single command:

```bash
source .venv/bin/activate
dvc repro
```

If the pipeline has already been run by someone else and the results pushed to the DVC remote, you can pull cached outputs without downloading any of the large source files:

```bash
dvc repro --pull --allow-missing
```

To run only up to a specific stage (e.g. just the JS generation):

```bash
dvc repro make_js
```

To visualize the pipeline graph:

```bash
dvc dag
```

After running the pipeline, copy the JS output from `data/js_output/` to the OZtree repo:

```bash
cp data/js_output/* ../OZtree/static/FinalOutputs/data/
```

Then see the section titled "Upload data to the server and check it" below.

### Updating parameters

Edit `params.yaml` to change the OpenTree version, taxonomy version, build version, etc. DVC will detect the parameter changes and re-run only the affected stages.

### At last

15. Have a well deserved cup of tea
