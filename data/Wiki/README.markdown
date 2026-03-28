To allow mappings to wikipedia and popularity calculations, the following
files are downloaded and filtered automatically by pipeline stages:

* **`download_wikipedia_sql`** downloads the en.wikipedia SQL dump
  (`enwiki-latest-page.sql.gz`, ~2 GB) from
  <https://dumps.wikimedia.org/enwiki/latest/>. To re-download the latest
  version, run `dvc repro --force download_wikipedia_sql`.

* **`download_and_filter_wikidata`** streams the full Wikidata JSON dump
  (`latest-all.json.bz2`, ~90 GB) from
  <https://dumps.wikimedia.org/wikidatawiki/entities/>, filters it on the fly,
  and writes only the small filtered output. To re-download with a fresh dump,
  run `dvc repro --force download_and_filter_wikidata`.

* **`download_and_filter_pageviews`** streams monthly `-user` dumps from
  <https://dumps.wikimedia.org/other/pageview_complete/monthly/>, filters them
  against the wikidata titles, and caches the small filtered outputs. Only the
  most recent N months (configured via `--months` in the DVC stage) are
  processed. To pick up newly published months, run
  `dvc repro --force download_and_filter_pageviews`.

If someone has already run the pipeline and pushed results to the DVC remote,
you do not need to download these files yourself --
`dvc repro --pull --allow-missing` will pull the cached filtered outputs instead.
