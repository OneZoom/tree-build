# Downloading required data files
 
To build a tree, you will first need to download various files from the internet. These are not provided by OneZoom directly as they are (a) very large and (b) regularly updated. The files you will need are:

* Open Tree of Life files, downloaded automatically by the `download_opentree` pipeline stage into `OpenTree/<version>/` (see [OpenTree/README.markdown](OpenTree/README.markdown))
	* `draftversion.tre` (processed synthesis tree)
	* `taxonomy.tsv` (OTT taxonomy)
* Wikimedia files, to be downloaded into directories within the `Wiki` directory (see [Wiki/README.markdown](Wiki/README.markdown))
	* `wd_JSON/latest-all.json.bz2`
	* `wp_SQL/enwiki-latest-page.sql.gz`
	* `wp_pagecounts/pageviews-YYYYMM-user.bz2` (several files for different months). Or download preprocessed files from a [release](https://github.com/OneZoom/tree-build/releases)
* EoL files, to be downloaded into the `EOL` directory (see [EOL/README.markdown](EOL/README.markdown))
	* `identifiers.csv`
