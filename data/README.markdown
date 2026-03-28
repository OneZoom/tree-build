# Downloading required data files
 
To build a tree, you will first need various data files from the internet. These are not provided by OneZoom directly as they are (a) very large and (b) regularly updated.

All source files are downloaded automatically by DVC pipeline stages:

* **Open Tree of Life** files, downloaded by the `download_opentree` stage into `OpenTree/<version>/` (see [OpenTree/README.markdown](OpenTree/README.markdown))
* **EOL provider IDs**, downloaded by the `download_eol` stage into `EOL/provider_ids.csv.gz`
* **Wikipedia SQL dump**, downloaded by the `download_wikipedia_sql` stage into `Wiki/wp_SQL/enwiki-latest-page.sql.gz` (see [Wiki/README.markdown](Wiki/README.markdown))
* **Wikidata JSON dump**, streamed and filtered by the `download_and_filter_wikidata` stage (see [Wiki/README.markdown](Wiki/README.markdown))
* **Wikipedia pageviews**, streamed and filtered by the `download_and_filter_pageviews` stage (see [Wiki/README.markdown](Wiki/README.markdown))
