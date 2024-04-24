To allow mappings to wikipedia and popularity calculations, the following three files
should be uploaded to their respective directories (NB: these could be symlinks to
versions on external storage)

* The `wd_JSON` directory should contain the wikidata JSON dump, as `latest-all.json.bz2`
(download from <http://dumps.wikimedia.org/wikidatawiki/entities/>)
* The `wp_SQL` directory should contain the en.wikipedia SQL dump file, as `enwiki-latest-page.sql.gz`
(download from <http://dumps.wikimedia.org/enwiki/latest/>)
* The `wp_pagecounts` directory should contain the wikipedia pagevisits dump files:
multiple files such as `wp_pagecounts/pageviews-202403-user.bz2` etc... 
(download from <https://dumps.wikimedia.org/other/pageview_complete/monthly/>)
