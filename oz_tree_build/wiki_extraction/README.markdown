# Wiki Extraction

This folder contains tools for building phylogenetic trees from Wikipedia data. The process extracts cladograms and taxonomy lists from Wikipedia pages, combines them into a single tree, and enriches the tree with date and species information.

## Overview

The pipeline has two main stages:

1. **Tree construction** (`newick_combiner`): Reads a `.wikiclades` file that defines how to assemble subtrees from various Wikipedia pages into a single combined tree in Newick format.

2. **Date and species enrichment** (`add_dates_and_species_to_tree`): Takes the Newick tree and walks each node, looking up its Wikipedia page to extract fossil date ranges (from taxoboxes) and species names. It uses these to set branch lengths based on geological dates.

## The .wikiclades format

A `.wikiclades` file defines the tree structure as a series of lines, each specifying a taxon and where to find its subtree on Wikipedia. The general format is:

```
TAXON FROM PageName@Location
```

- **Location** is either a number (the Nth cladogram on the page) or a string (a section header for a taxonomy bullet list).
- **Comments** start with `#` and are ignored.
- **Indentation** is for readability only and has no semantic meaning. The tree structure is determined by how subtrees get grafted together, not by indentation.

### Pinning a specific revision

By default, the latest revision of a Wikipedia page is used. To pin a specific revision (useful when a page changes in a way that breaks extraction), append the revision ID in parentheses:

```
Neosuchia FROM Neosuchia(1312892883)@2
```

The revision ID is the same as Wikipedia's `oldid` parameter, visible in page history URLs.

### Insertion operators

- `Taxon FROM Page@1` — Replaces the matching node in the parent tree with the subtree rooted at `Taxon`.
- `Child->Parent FROM Page@1` — Adds `Child` as a new child of `Parent` (no replacement).
- `Child=>Parent FROM Page@1` — Replaces `Parent` with the subtree rooted at `Child`.

### Excluding taxa

Append taxa to exclude with dashes:

```
Dinosauria-Unenlagiidae-Megaraptora FROM Dinosaur@Taxonomy
```

This extracts the `Dinosauria` subtree but removes `Unenlagiidae` and `Megaraptora` from it.

### Including other .wikiclades files

A source can reference another `.wikiclades` file instead of a wiki page:

```
Synapsida FROM Synapsida.wikiclades
```

The path is resolved relative to the current file.

## Building a tree

Using Amniota as an example, set the clade name and run the two stages:

```bash
CLADE=Amniota

# Stage 1: Build the tree structure from Wikipedia cladograms
newick_combiner data/OZTreeBuild/WikiExtraction/${CLADE}.wikiclades \
    --extraction_cache_folder data/OZTreeBuild/WikiExtraction/cache \
    --source_mapping_file source_mapping_file.md \
    > data/OZTreeBuild/WikiExtraction/${CLADE}_nodates.phy

# Stage 2: Add dates and species information
add_dates_and_species_to_tree data/OZTreeBuild/WikiExtraction/${CLADE}_nodates.phy \
    > data/OZTreeBuild/WikiExtraction/${CLADE}.phy
```

The `--source_mapping_file` flag produces a markdown file mapping each taxon to its source Wikipedia page, useful for debugging.

## Caching

There are three layers of caching to avoid redundant Wikipedia API calls:

### HTTP response cache (`http_cache.sqlite`)

An SQLite database (in the working directory) managed by `requests_cache`. All Wikipedia API responses are cached here, so repeated runs avoid re-fetching the same pages. Delete this file to force fresh API calls. If the API returns a 429 (rate limited), the request is retried with exponential backoff.

### Extraction cache (`data/OZTreeBuild/WikiExtraction/cache/`)

When `--extraction_cache_folder` is passed to `newick_combiner`, each extracted subtree is saved as a `.phy` (Newick) file. On subsequent runs, the subtree is loaded from this cache instead of re-parsing the Wikipedia page. This is faster than re-extracting from wikicode, and useful during development when iterating on tree assembly. Delete individual `.phy` files (or the whole folder) to force re-extraction of specific pages.

### Taxon data cache (`*.taxondatacache.json`)

`add_dates_and_species_to_tree` caches the date ranges and species data it retrieves for each taxon in a JSON file alongside the input tree file (e.g., `Amniota_nodates.phy.taxondatacache.json`). Delete this file to force re-fetching taxon data from Wikipedia.
