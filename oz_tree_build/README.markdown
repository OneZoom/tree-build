# Introduction
Creating a bespoke OneZoom tree involves a number of steps, as documented below. These take an initial tree, map taxa onto Open Tree identifiers, add subtrees from the OpenTree of Life, resolve polytomies and delete subspecies, and calculate mappings to other databases together with creating wikipedia popularity metrics for all taxa. Finally, the resulting tree and database files are converted to a format usable by the OneZoom viewer. Mapping and popularity calculations require various large files to be downloaded e.g. from wikipedia, as [documented here](../data/README.markdown).

The instructions below are primarily intended for creating a full tree of all life on the main OneZoom site. If you are making a bespoke tree, you may need to tweak them slightly.

The output files created by the tree building process (database files and files to feed to the js,
and which can be loaded into the database and for the tree viewer) are saved in `output_files`.


## Settings

Assuming that the environment variables OT_VERSION and OT_TAXONOMY_VERSION have already
been set as described in the [main README file](../README.markdown), and the
appropriate data files downloaded as described [here](../data/README.markdown),
the instructions below only require the following environmental variable to be
set up:

```
OZ_TREE=AllLife #a tree directory in data/OZTreeBuild
```

# Preliminaries

Follow [these instructions](../data/README.markdown) to download all required files.

# Building a tree

The times given at the start of each of the following steps refer to the time taken to run the commands on the entire tree of life. 

If you already have your own newick tree with open tree ids on it already, and don't want to graft extra clades from the OpenTree, you can skip steps 1-4, and simply save the tree as `${OZ_TREE}_full_tree.phy` in your base directory. If you have a tree but it does not have ott numbers, then you can add them using step 1, and move the resulting tree in `BespokeTree/include_files` to `${OZ_TREE}_full_tree.phy` in your base directory.

## Create the tree


1. (20 secs) Use the [OpenTree API](https://github.com/OpenTreeOfLife/germinator/wiki/Synthetic-tree-API-v3) to add OTT ids to any non-opentree taxa in our own bespoke phylogenies (those in `*.phy` or `*.PHY` files). The new `.phy` and `.PHY` files will be created in a new directory within `data/OZTreeBuild/${OZ_TREE}/BespokeTree`, and a symlink to that directory will be created called `include_files` 
		
	```
	add_ott_numbers_to_trees \
	--savein data/OZTreeBuild/${OZ_TREE}/BespokeTree/include_OTT${OT_TAXONOMY_VERSION}${OT_TAXONOMY_EXTRA} \
	data/OZTreeBuild/${OZ_TREE}/BespokeTree/include_noAutoOTT/*.[pP][hH][yY]
	```

1. Copy supplementary OpenTree-like newick files (if any) to the `OpenTree_all` directory. These are clades referenced in the OneZoom phylogeny that are missing from the OpenTree, and whose subtrees thus need to be supplied by hand. If any are required, they should be placed in the `OT_required` directory within `data/OZTreeBuild/${OZ_TREE}`. For tree building, they should be copied into the directory containing OpenTree subtrees using

	```
	(cd data/OZTreeBuild/${OZ_TREE}/OpenTreeParts && \
	 cp -n OT_required/*.nwk OpenTree_all/)
	```
	If you do not have any supplementary `.nwk` subtrees in the  `OT_required` directory, this step will output a warning, which can be ignored.

1. (a few secs) Construct OpenTree subtrees for inclusion from the `draftversion${OT_VERSION}.tre` file. The subtrees to be extracted are specified by inclusion strings in the `.PHY` files created in step 1. The command for this is `getOpenTreesFromOneZoom.py`, and it needs to be run from within the `data/OZTreeBuild/${OZ_TREE}` directory, as follows:

	```
	(cd data/OZTreeBuild/${OZ_TREE} && get_open_trees_from_one_zoom \
	 ../../OpenTree/draftversion${OT_VERSION}.tre OpenTreeParts/OpenTree_all/ \
	 BespokeTree/include_files/*.PHY)
	```
	If you are not including any OpenTree subtrees in your final tree, you should have no `.PHY` files, and this step will output a warning, which can be ignored.
	
1. (1 sec) substitute these subtrees into the main tree, and save the resulting full newick file using the `build_oz_tree` script: 

	```
	(cd data/OZTreeBuild/${OZ_TREE} && \
	build_oz_tree BespokeTree/include_files/Base.PHY OpenTreeParts/OpenTree_all/ AllLife_full_tree.phy)
	```

	Now that we are not having to run this every sponsorship time, we should probably re-write this to actually know what tree structure looks like, maybe using Python/DendroPy (see https://github.com/jrosindell/OneZoomComplete/issues/340) and also to automatically create the list of DOIs at `static/FinalOutputs/refs.txt`. Note that any '@' signs in the `${OZ_TREE}_full_tree.phy` output file are indicative of OpenTree substitutions that have not been possible: it would be good to check to see if there are other sources (or old OpenTree versions) that have trees for these nodes, and place them as .phy files in `data/OZTreeBuild/${OZ_TREE}/OpenTreeParts/OT_required/`. You can check with

	```
	grep -o '.............@' data/OZTreeBuild/${OZ_TREE}/${OZ_TREE}_full_tree.phy
	```
	You may also want to save a zipped version of the full tree file in a place where users can download it for reference purposes, in which case you can do

	```
	gzip < data/OZTreeBuild/${OZ_TREE}/${OZ_TREE}_full_tree.phy > static/FinalOutputs/${OZ_TREE}_full_tree.phy.gz
	```

	## Create the base tree and table data
   
1. (5 to 7 hours) This is the long step. It generates filtered versions of the raw input files, which then makes them faster to work with. For example, for the massive wikimedia dump file (`latest-all.json.bz2`), it remove all entries that aren't taxons or vernaculars, and for each remaining entry, in only keeps the small subset of fields that we care about.

	The output files have the same names as the input files, but with a `OneZoom_` prefix, and without using compression (e.g. `OneZoom_latest-all.json` for `latest-all.json`.bz2). They are stored next to their matching input files.

	From the data folder:

	```
	(cd data && generate_filtered_files OZTreeBuild/AllLife/AllLife_full_tree.phy OpenTree/ott${OT_TAXONOMY_VERSION}/taxonomy.tsv EOL/provider_ids.csv.gz Wiki/wd_JSON/latest-all.json.bz2 Wiki/wp_SQL/enwiki-latest-page.sql.gz Wiki/wp_pagecounts/pagecounts*.bz2)
	```

1. (11 mins) On the basis of the `${OZ_TREE}_full_tree.phy` file, look for ID mappings between different datasets, calculate popularity measures via wikidata/pedia, refine the tree (remove subspecies, randomly break polytomies, remove unifurcations etc), and then create corresponding database tables together with `ordered_tree_XXXXX.nwk`, `ordered_tree_XXXXX.poly` (same file but with polytomies marked with curly braces), and `ordered_dates_XXXXX.js` files (where XXXXX is the version number, usually a timestamp).

    Additional flags can be given to override the OpenTree taxonomy in specific cases (using `--extra_source_file`), and to exclude certain taxa (e.g. dinosaurs) from the popularity calculations.

	If you do not have comprehensive tree of a clade, it probably doesn't make sense to calculate popularity measures, and you can run this script with the `-p` flag (or omit the references to the `wp_` wikipedia files).
	
	```
	CSV_base_table_creator \
	data/OZTreeBuild/${OZ_TREE}/${OZ_TREE}_full_tree.phy \
	data/OpenTree/ott${OT_TAXONOMY_VERSION}/taxonomy.tsv \
	data/EOL/OneZoom_provider_ids.csv \
	data/Wiki/wd_JSON/OneZoom_latest-all.json \
	data/Wiki/wp_SQL/OneZoom_enwiki-latest-page.sql \
	data/Wiki/wp_pagecounts/OneZoom_pagecounts* \
	-o data/output_files -v \
	--exclude Archosauria_ott335588 Dinosauria_ott90215 \
	--extra_source_file data/OZTreeBuild/${OZ_TREE}/BespokeTree/SupplementaryTaxonomy.tsv \
	2> data/output_files/ordered_output.log
	```

    Since round braces, curly braces, and commas are banned from the `simplified_ottnames` file, we can create minimal topology files by simply removing everything except these characters from the `.nwk` and `.poly` files. If the tree has been ladderised, with polytomies and unifurcations removed, the commas are also redundant, and can be removed. This is done in the next step, which saves these highly shortened strings into .js data files. 

1. (1 min) turn the most recently saved tree files (saved in the previous step as `data/output_files/ordered_tree_XXXXXX.poly` and `ordered_dates_XXXXXX.json`) into bracketed newick strings in `static/FinalOutputs/data/basetree_XXXXXX.js`, `static/FinalOutputs/data/polytree_XXXXXX.js`, a cutpoints file in `static/FinalOutputs/data/cut_position_map_XXXXXX.js`, and a dates file in `static/FinalOutputs/data/dates_XXXXXX.json` as well as their gzipped equivalents, using 
	
	```
	make_js_treefiles
	```

	This command assumes that you have the `tree-build` repo as a sibling to the `OZtree` repo. You can override this by specifying the `--outdir` flag, pointing it to wherever your `static/FinalOutputs/data` is.
    
    ## Upload data to the server and check it
    
1. If you are running the tree building scripts on a different computer to the one running the web server, you will need to push the `completetree_XXXXXX.js`, `completetree_XXXXXX.js.gz`, `cut_position_map_XXXXXX.js`, `cut_position_map_XXXXXX.js.gz`, `dates_XXXXXX.js`
, `dates_XXXXXX.js.gz` files onto your server, e.g. by pushing to your local Github repo then pulling the latest github changes to the server.
1. (15 mins) load the CSV tables into the DB, using the SQL commands printed in step 6 (the ones that start something like `TRUNCATE TABLE ordered_leaves; LOAD DATA LOCAL INFILE ...;` `TRUNCATE TABLE ordered_nodes; LOAD DATA LOCAL INFILE ...;`). Either do so via a GUI utility, or copy the `.csv.mySQL` files to a local directory on the machine running your SQL server (e.g. using `scp -C` for compression) and run your `LOAD DATA LOCAL INFILE` commands on the mysql command line (this may require you to start the command line utility using `mysql --local-infile`, e.g.:

   ```
   mysql --local-infile --host db.sundivenetworks.net --user onezoom --password --database onezoom_dev
   ```
1. Check for dups, and if any sponsors are no longer on the tree, using something like the following SQL command:

    ```
    select * from reservations left outer join ordered_leaves on reservations.OTT_ID = ordered_leaves.ott where ordered_leaves.ott is null and reservations.verified_name IS NOT NULL;
    select group_concat(id), group_concat(parent), group_concat(name), count(ott) from ordered_leaves group by ott having(count(ott) > 1)
    ```
    
    ## Fill in additional server fields

1. (15 mins) create example pictures for each node by percolating up. This requires the most recent `images_by_ott` table, so either do this on the main server, or (if you are doing it locally) update your `images_by_ott` to the most recent server version.

	```
	OZprivate/ServerScripts/Utilities/picProcess.py -v
	```
1. (5 mins) percolate the IUCN data up using 
	
	```
	OZprivate/ServerScripts/Utilities/IUCNquery.py -v
	```
	(note that this both updates the IUCN data in the DB and percolates up interior node info)
1. (10 mins) If this is a site with sponsorship (only the main OZ site), set the pricing structure using SET_PRICES.html (accessible from the management pages).
1. (5 mins - this does seem to be necessary for ordered nodes & ordered leaves). Make sure indexes are reset. Look at `OZprivate/ServerScripts/SQL/create_db_indexes.sql`  for the SQL to do this - this may involve logging in to the SQL server (e.g. via Sequel Pro on Mac) and pasting all the drop index and create index commands.
    
    ## at last
1. Have a well deserved cup of tea
