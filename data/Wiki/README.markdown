To allow mappings to wikipedia and popularity calculations, the following files
should be uploaded to their respective directories (NB: these could be symlinks to
versions on external storage)

* The `wd_JSON` directory should contain the wikidata JSON dump, as `latest-all.json.bz2`
(download from <http://dumps.wikimedia.org/wikidatawiki/entities/>)
* The `wp_SQL` directory should contain the en.wikipedia SQL dump file, as `enwiki-latest-page.sql.gz`
(download from <http://dumps.wikimedia.org/enwiki/latest/>)

Wikipedia pageview files are downloaded and filtered automatically by the
`download_and_filter_pageviews` pipeline stage. It streams monthly `-user` dumps
from <https://dumps.wikimedia.org/other/pageview_complete/monthly/>, filters them
against the wikidata titles, and caches the small filtered outputs. Only the most
recent N months (configured via `--months` in the DVC stage) are processed. To
pick up newly published months, run `dvc repro --force download_and_filter_pageviews`.

These files are used as inputs to the DVC pipeline's filtering stages. If someone
has already run the pipeline and pushed results to the DVC remote, you do not need
to download these files yourself -- `dvc repro --pull --allow-missing` will pull
the cached filtered outputs instead.
