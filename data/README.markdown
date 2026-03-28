# Downloading required data files
 
To build a tree, you will first need various data files from the internet. These are not provided by OneZoom directly as they are (a) very large and (b) regularly updated.

Most source files are downloaded automatically by pipeline stages. The only file that must be downloaded manually is:

* Wikipedia SQL dump: `Wiki/wp_SQL/enwiki-latest-page.sql.gz` (see [Wiki/README.markdown](Wiki/README.markdown))

The following are handled by DVC pipeline stages:

* **Open Tree of Life** files, downloaded by the `download_opentree` stage into `OpenTree/<version>/` (see [OpenTree/README.markdown](OpenTree/README.markdown))
* **EOL provider IDs**, downloaded by the `download_eol` stage into `EOL/provider_ids.csv.gz`
* **Wikidata JSON dump**, streamed and filtered by the `download_and_filter_wikidata` stage (see [Wiki/README.markdown](Wiki/README.markdown))
* **Wikipedia pageviews**, streamed and filtered by the `download_and_filter_pageviews` stage (see [Wiki/README.markdown](Wiki/README.markdown))
