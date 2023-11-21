# Downloading required data files
 
To build a tree, you will first need to download various files from the internet. These are not provided by OneZoom directly as they are (a) very large and (b) regularly updated. The files you will need are:

* Open Tree of Life files, to be downloaded into the `OpenTree` directory (see [OpenTree/README.markdown](OpenTree/README.markdown)
	* `labelled_supertree_simplified_ottnames.tre` (subsequently converted to `draftversionXXX.tre`, as detailed in the instructions)
	* `ottX.Y/taxonomy.tsv` (where X.Y is the OT_TAXONOMY_VERSION)
* Wikimedia files, to be downloaded into directories within the `Wiki` directory (see [Wiki/README.markdown](Wiki/README.markdown))
	* `wd_JSON/latest-all.json.bz2`
	* `wp_SQL/enwiki-latest-page.sql.gz`
	* `wp_pagecounts/pagecounts-YYYY-MM-views-ge-5-totals.bz2` (several files for different months)
* EoL files, to be downloaded into the `EOL` directory (see [EOL/README.markdown](EOL/README.markdown))
	* `identifiers.csv`
