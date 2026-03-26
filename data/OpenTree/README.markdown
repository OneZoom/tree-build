### Directory contents

This folder contains versioned subdirectories of Open Tree of Life data, e.g. `v16.1/`. Each subdirectory is created by the `download_opentree` script and contains:

* `labelled_supertree_simplified_ottnames.tre` -- the raw downloaded tree
* `draftversion.tre` -- the tree with `mrca***` labels removed and whitespace normalised
* `taxonomy.tsv` -- the OTT taxonomy file

These subdirectories are .gitignored and tracked by DVC as pipeline outputs.

### How to get the files

Run the download script with the desired synthesis version:

```
download_opentree --version v16.1 --output-dir data/OpenTree
```

The script fetches the [synthesis manifest](https://raw.githubusercontent.com/OpenTreeOfLife/opentree/master/webapp/static/statistics/synthesis.json) to look up the correct OTT taxonomy version, then downloads both the labelled supertree and taxonomy automatically.

This is also available as a DVC pipeline stage (`download_opentree` in `dvc.yaml`), so `dvc repro` will run it when `ot_version` changes in `params.yaml`.

### Use

These files are processed by the pipeline stages in `dvc.yaml` to create the full OneZoom tree. The `taxonomy.tsv` file is also used by other stages (e.g. for popularity mapping, EoL filtering, etc.).

NB: for the rationale of using `...simplified_ottnames` see
 [https://github.com/OpenTreeOfLife/treemachine/issues/147#issuecomment-209105659](https://github.com/OpenTreeOfLife/treemachine/issues/147#issuecomment-209105659) and also [here](https://groups.google.com/forum/#!topic/opentreeoflife/EzqctKrJySk)
