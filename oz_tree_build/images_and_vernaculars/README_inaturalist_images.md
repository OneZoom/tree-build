# iNaturalist image harvesting for OneZoom

This directory now includes `get_inat_images.py`, a sibling of `get_wiki_images.py` for harvesting iNaturalist photos.

## Mapping strategy

The preferred mapping is:

```text
OneZoom leaf -> ordered_leaves.wikidata -> Wikidata P3151 -> iNaturalist taxon ID
```

`P3151` is the Wikidata property for the iNaturalist taxon ID. The existing Wikidata filtering code already keeps this property, so a filtered OneZoom Wikidata dump can be used in clade mode.

## License rule

The harvester **must only accept** iNaturalist photos whose license is one of:

- `CC0`
- `CC-BY`
- `CC-BY-SA`

The code enforces this with `ALLOWED_INAT_PHOTO_LICENSES = {"cc0", "cc-by", "cc-by-sa"}`. It rejects non-commercial (`NC`) and no-derivatives (`ND`) licenses.

## Image sources

The script has two modes.

### API mode

Use this for prototypes, small clades, and the "most voted" behavior:

```bash
python -m oz_tree_build.images_and_vernaculars.get_inat_images leaf "Xestospongia testudinaria" \
  --image-source api \
  --no-azure-crop \
  -o /path/to/OZtree/static/FinalOutputs/img \
  -c /path/to/appconfig.ini
```

API mode calls the iNaturalist v2 observations endpoint with:

```text
taxon_id=<P3151>
photos=true
quality_grade=research
photo_license=cc-by,cc-by-sa,cc0
order_by=votes
order=desc
```

Then it chooses the best usable photo from the returned observations. This is the only mode that can approximate "most voted," because vote totals are not included in the open-data metadata dump.

### Metadata mode

Use this for bulk harvesting from the iNaturalist Open Data metadata dump after loading it into a local database:

```bash
python -m oz_tree_build.images_and_vernaculars.get_inat_images clade OneZoom_latest-all.json Porifera \
  --image-source metadata \
  --inat-db-uri postgres://user:password@localhost/inaturalist-open-data \
  --no-azure-crop \
  -o /path/to/OZtree/static/FinalOutputs/img \
  -c /path/to/appconfig.ini
```

Metadata mode joins the dump tables:

```text
observations -> photos -> observers
```

It filters to research-grade observations and the three allowed licenses. Since the metadata dump has no vote columns, it chooses by:

1. lowest photo position, because the observer's first photo is usually the representative image;
2. largest pixel area;
3. lowest photo ID as a deterministic tie-breaker.

## Expected iNaturalist metadata database

The metadata database should contain the four iNaturalist Open Data tables named exactly as in the official documentation:

- `observations`
- `photos`
- `taxa`
- `observers`

The script currently needs these columns:

```text
observations: observation_uuid, taxon_id, quality_grade, observed_on
photos: photo_id, observation_uuid, observer_id, extension, license, width, height, position
observers: observer_id, login, name
```

Useful indexes for this workflow:

```sql
CREATE INDEX index_photos_observation_uuid ON photos USING btree (observation_uuid);
CREATE INDEX index_photos_observer_id ON photos USING btree (observer_id);
CREATE INDEX index_observers_observer_id ON observers USING btree (observer_id);
CREATE INDEX index_observations_taxon_id ON observations USING btree (taxon_id);
```

## Saved image layout

The new source flag is:

```python
src_flags["inat"] = 40
```

Files are saved like existing image harvesters:

```text
FinalOutputs/img/40/<last-three-digits>/<photo_id>.jpg
FinalOutputs/img/40/<last-three-digits>/<photo_id>_uncropped.jpg
FinalOutputs/img/40/<last-three-digits>/<photo_id>_cropinfo.txt
```

The database `images_by_ott` row uses:

- `src = 40`
- `src_id = iNaturalist photo_id`
- `url = iNaturalist photo page or observation URL`
- `rights = iNaturalist-style attribution string`
- `licence = CC0, CC-BY, or CC-BY-SA`

## Important limitation

The iNaturalist Open Data metadata dump is scalable, but it does not include vote totals. If you specifically need "most voted" photos, use API mode for candidate selection, then cache the selected photo IDs before downloading in bulk.
