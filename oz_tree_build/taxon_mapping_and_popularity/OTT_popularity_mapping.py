#!/usr/bin/env python3
"""
Routines for mapping OpenTree Taxonomy identifiers to wikidata/pedia, and
then calculating popularity indices from them.

Most of these routines can be called from other files: running this file as the main
python script will save popularity measures to a csv file. If you want to output
phylogenetic popularity measures, based on ancestors and descendants in a tree, you must
specify an --OpenTreeFile. Otherwise, the script will produce a csv output with basic
popularity measures which can be run through calc_phylogenetic_popularity.py to output
phylogenetic (ancestor / descendant summmed) popularities separately. This allows quick
popularity recalculation (NB: "ancestor" popularities include the popularity of self)

The routines work by taking an OpenTree taxonomy file and mapping
each line to wikidata Qid using source ids

    each source id is stored in a object, to which we add wiki info such as the qID, e.g.

    {"id":NCBIid, WikidataItem(Q=Qid)}

    the object is pointed to from two sources, a source_data 2D array & an OTT_ids array, e.g.

    source_ptrs["ncbi"][NCBIid] -> {"id":NCBIid} <- OTT_ptrs[OTTid]["sources"]["ncbi"]
    source_ptrs["worms"][WORMSid] -> {"id":WORMSid} <- OTT_ptrs[OTTid]["sources"]["worms"]

    this allows us to add Wikidata items to the object
    which can then be seen from the OTT_ids reference, i.e.

    source_ptrs["ncbi"][NCBIid] -> {"id":NCBIid, wd(Q=Qid1, l={"en","fr"}, iucn=IUCNid)} <- OTT_ptrs[OTTid]["sources"]["ncbi"]
    source_ptrs["worms"][WORMSid] -> {"id":WORMSid, "wd":{"Q":Qid2}} <- OTT_ptrs[OTTid]["sources"]["worms"]

    where "l" gives the sitelinks into the different language wikipedias

    We also create a wikipedia_title array of pointers into the same dataset

    enwikipedia_ptrs[enwiki_title] -> {"Q":Qid1}

    so that we can add e.g. page sizes & visits

== Wikidata parsing ==

Wikidata dump has one line per item or property, and there are millions of items
("type":"item") in the dump. We are only interested in taxon items (and possibly common
names that point to taxon items)

=== Taxon items ===
These must contain the strings Q16521, Q310890, Q23038290, or Q713623, since all taxon
items have property P31 ("instance of") set to taxon (Q16521) or a subclass of "taxon": monotypic taxon (Q310890),
fossil taxon (Q23038290), clade (Q713623), or similar see
https://www.wikidata.org/wiki/Wikidata:WikiProject_Taxonomy/Tutorial#Basic_properties, and all the subclasses of
taxon at http://bit.ly/2m1717d). These taxon items should be in the following format e.g.
==== Example ====
for Gorilla (Q36611) (simplified from the output via https://www.wikidata.org/wiki/Special:EntityData/Q737838.json
 or using `gzcat wikidata-20151005-all.json.gz | grep -A 200 ""id": "Q737838""`, with linebreaks added)

{"type":"item","id":"Q36611","labels":{"pl":{"language":"pl","value":"goryl"},"en":{"language":"en","value":"Gorilla"}...},
  "claims":{
    "P31":[
      {"mainsnak": {"datatype": "wikibase-item","datavalue":{"type": "wikibase-entityid","value":{"entity-type":"item","numeric-id":16521}},"property":"P31","snaktype":"value"},"rank":"normal","type":"statement"}],
    "P685":[
      {"mainsnak": {"datatype": "string","datavalue":{"type":"string","value":"9592"},"property": "P685","snaktype":"value"},"rank": "normal"}],
    ...},
  "sitelinks":{
    "arwiki":{"badges":[],"site":"arwiki","title":"\u063a\u0648\u0631\u064a\u0644\u0627"},
    "enwiki": {"badges":[],"site":"enwiki","title": "Gorilla"},...},...}

=== Common name items ===
Common name items must contain the string Q55983715, since all these have property P31 ("instance of") set to
organisms known by a particular common name (Q55983715) of (P642) [Taxon item]

==== Example ====
for Snake (Q2102) which points to the taxon page "Serpentes" (Q29540038)
{"type": "item","id":"Q2102","labels":{ "en": { "language": "en", "value": "snake" }, "sv": { "language": "sv", "value": "Ormar" }},
  "claims":{"P31":[{
    "mainsnak":{
      "snaktype":"value",
      "property":"P31",
      "datavalue":{
        "value": { "entity-type": "item", "numeric-id": 55983715, "id": "Q55983715" },
        "type": "wikibase-entityid"},
        "datatype":"wikibase-item"
      },
    "type":"statement",
    "qualifiers":{"P642":[{
        "snaktype": "value",
        "property": "P642",
        "hash": "2fde8becf289ba42ea01b3adfa2dfd4da65ba561",
        "datavalue": { "value": { "entity-type": "item", "numeric-id": 29540038, "id": "Q29540038" }, "type": "wikibase-entityid" },
        "datatype": "wikibase-item" }]},
      ...}]
    },
  "sitelinks":{
    "dewiki":{"site":"dewiki","title": "Schlangen", "badges":[],"url": "https://de.wikipedia.org/wiki/Schlangen"},
    "enwiki": { "site": "enwiki", "title": "Snake", "badges": [], "url": "https://en.wikipedia.org/wiki/Snake"}},
    ...}

=== Issues ===

A good example of problematic issues is Gazella/gazelle. The English word "gazelle"
applies to a number of antelope species, not all of which are in the genus Gazella.
The genus Gazella is present in WD at [[Q190858]], and the concept of a gazelle at
[[Q29001815]]. The gazelle item is (correctly) stated as an instance of a common name of
Gazella, Eudorcas, Nanger, and Antilopini. But there is no english wikipedia item for
Gazella (the genus), only for gazelles (the vernacular).

== Running the script ==

You can run this script to produce a raw output file using something like

ServerScripts/TaxonMappingAndPopularity/OTT_popularity_mapping.py data/OpenTree/ott/taxonomy.tsv data/Wiki/wd_JSON/*.bz2 data/Wiki/wp_SQL/*.gz  data/Wiki/wp_pagecounts/*.bz2 -o data/output_files/raw_pop -v > ServerScripts/TaxonMappingAndPopularity/ottmap.log

To get e.g. only the species in the current OpenTree, this raw_pop can be filtered by
first collecting a list of the OTT ids of interest, e.g.

grep -o "\\d\\+" opentree7.0_tree/labelled_supertree/labelled_supertree.tre | sort | uniq > tree_taxa
grep "|\\s*species\\s*|" ott/taxonomy.tsv | cut -f 1 | sort > ot_species
comm -12 tree_taxa ot_species > tree_species
grep ",\\d" raw_pop | cut -f 1 -d, | sort > wiki_taxa

== the number of wiki : total taxa
wc -l raw_pop wiki_taxa # 1492679/3452152 = 43%

the number of wiki : total taxa for those only in tree_species
perl -e "open(F1, q|<tree_taxa|);open(F2, q|<raw_pop|); %foo = map {$_ => 1} <F1>; while(<F2>) {print if(exists($foo{(split(/,/,$_,2))[0].q|\n|}));};" > raw_species
grep ",\\d" raw_species | cut -f 1 -d, | sort > wiki_species
wc -l raw_species wiki_species # 1429835/2335500 = 43%

Note: a few organisms like Dog and Cat do not have the wikipedia pages linked from the taxon item, but
from another more generic page. For example, Canis lupus familiaris (Q26972265) is not linked to
the "dog" wikipedia items. Instead, these are linked from Q144 (dog) which is an
"instance of (P31) common name (Q55983715) of (P642) Canis lupus familiaris (Q26972265)"
we can find these (very few) examples by the wikidata query at https://w.wiki/enx

"""  # noqa E501

import csv
import json
import logging
import os.path
import re
import sys
from collections import OrderedDict, defaultdict
from statistics import StatisticsError, mean

from oz_tree_build._OZglobals import wikiflags
from oz_tree_build.utilities.file_utils import open_file_based_on_extension

__author__ = "Yan Wong"
__license__ = """This is free and unencumbered software released into the public domain by the author, Yan Wong, for OneZoom CIO.

Anyone is free to copy, modify, publish, use, compile, sell, or distribute this software, either in source code form or as a compiled binary, for any purpose, commercial or non-commercial, and by any means.

In jurisdictions that recognize copyright laws, the author or authors of this software dedicate any and all copyright interest in the software to the public domain. We make this dedication for the benefit of the public at large and to the detriment of our heirs and successors. We intend this dedication to be an overt act of relinquishment in perpetuity of all present and future rights to this software under copyright law.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

For more information, please refer to <http://unlicense.org/>"""  # noqa E501


def wikidata_value(wd_json, err=False):
    """
    used to get the value dict out of a wd parsed object
    If err==False, do not error out (allows use in a list comprehension)
    """
    try:
        return wd_json["datavalue"]["value"]
    except (KeyError, TypeError):
        return {}


def label(json_item, lang="en"):
    try:
        return json_item["labels"][lang]["value"]
    except LookupError:
        return f"no name for lang = {lang}"


def Qid(json_item):
    return int(json_item["id"].replace("Q", "", 1))


LANG_FLAGS = {lang: 2**bit for lang, bit in wikiflags.items()}


class WikidataItem:
    # sitelinks can contain wikispecies & wikimedia commons links: exclude these

    exclude_langs = frozenset(("species", "commons"))

    def __init__(self, json_item):
        """
        Create a basic item with an (integer) 'Q' attribute and an 'l' for sitelinks.
        Other attributes such as EoL ids, page size, visit count, etc are added later.
        """
        self.Q = Qid(json_item)
        self.l = set()

    def __getitem__(self, attribute):
        """
        Allow attributes to be accessed like a dict, e.g. wd_instance['l']. This
        is useful for outputting to CSV
        """
        try:
            return getattr(self, attribute)
        except AttributeError as err:
            raise KeyError from err

    def get(self, attribute, default=None):
        try:
            return getattr(self, attribute)
        except AttributeError:
            return default

    def add_sitelinks_and_get_title(self, json_item, return_wikilang=None):
        """
        Add an 'l' for the set of links in the form {'fr' ,'en', ...}
        If wikilang is not None, but e.g. 'en', return the sitelink name for
        that language
        """
        ret = None
        for sitelink, data in json_item["sitelinks"].items():
            if sitelink.endswith("wiki"):
                lang = sitelink[:-4]
                self.l.add(lang)
                if lang == return_wikilang:
                    # canonical form has underscores not spaces
                    ret = data["title"].replace(" ", "_")
        return ret

    def set_raw_popularity(self, trim_highest=2):
        """
        Set raw popularities for wikidata entries, based on page size & page views.
        The highest n viewing figures can be trimmed, to avoid spikes. Trimming 2 months
        removes spikes that crosses from the end of one month to the beginning of another

        Currently the function is calculated by (sqrt(pagesize * trimmed_mean_pageviews))
        The popularity is then rounded to 2 decimal places

        Return True if a valid raw popularity was set
        """
        self.raw_popularity = 0
        try:
            trMeanViews = mean(sorted([x for x in self.pageviews if x is not None])[:-trim_highest])
            self.raw_popularity = round((self.pagesize * trMeanViews) ** 0.5, 2)
            return True
        except (StatisticsError, ValueError, AttributeError):
            # perhaps data is absent, a number is NA or we are trying to take a mean
            # of an empty list - if so, ignore
            pass
        return False

    @property
    def wikipedia_lang_flag(self):
        """
        Return a wikipedia lang flag, for outputting to csv files
        Languages are sorted roughly according to active users on
        https://en.wikipedia.org/wiki/List_of_Wikipedias
        """
        tot = 0
        for lang in self.l:
            tot += LANG_FLAGS.get(lang) or 0  # add together as bit fields
        return tot

    def merge_and_overwrite(self, other, overwrite=None, label=None):
        """
        Take attributes in copy and merge them into self (mostly Q, links, & pop metrics)
        If `overwrite` is False then do not overwrite any attributes. If True, then
        all attributes in copy overwrite the originals. If None (default) then only
        overwrite if "copy" has an attribute named 'raw_popularity', and that raw
        popularity is greater than the self.raw_popularity.

        'label' is simply used for output

        Return True if anything overwritten
        """
        ret = False
        for v in vars(other):
            if hasattr(self, v):
                if overwrite is False:
                    continue
                if overwrite is None and self.raw_popularity > other.raw_popularity:
                    continue
                if getattr(self, v) == getattr(other, v):
                    continue
                ret = True
                if v == "l":
                    lost_links = self.l - other.l - self.exclude_langs
                    if len(lost_links):
                        logging.warning(" x Sitelinks lost in these languages: " + str(lost_links))
            setattr(self, v, getattr(other, v))
        return ret


def JSON_contains_known_dbID(json_item, known_items):
    """
    Return a dict of the source types and ids for this json_item, (e.g.
    {'ncbi': 1234, 'gbif': 4567}, etc.
    """
    wikidata_db_props = {
        "P685": "ncbi",
        "P846": "gbif",
        "P850": "worms",
        "P1391": "if",
        "P5055": "irmng",
    }
    ret = {}
    for taxon_id_prop, source in wikidata_db_props.items():
        if taxon_id_prop in json_item["claims"]:
            claim = json_item["claims"][taxon_id_prop]
            if source in ret:
                logging.warning(
                    f"Multiple {source} IDs for Q{Qid(json_item)} ({label(json_item)}); " "taking the last one"
                )
            try:
                src_id = wikidata_value(claim[0]["mainsnak"], err=True)
            except (KeyError, ValueError, TypeError):
                logging.warning(  # Lots of wikidata items may not be in
                    f"Can't find a value for {source} for Q{Qid(json_item)} " f"({label(json_item)}) in wikidata"
                )
                continue
            if src_id:
                try:
                    if int(src_id) in known_items[source]:
                        ret[source] = int(src_id)
                except ValueError:
                    if src_id in known_items[source]:
                        ret[source] = src_id
    return ret


def mem():
    import resource

    rusage_denom = 1024.0
    if sys.platform == "darwin":
        # ... it seems that in OSX the output is different units ...
        # perhaps update to try psutils instead
        rusage_denom = rusage_denom * rusage_denom
    mem = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / rusage_denom
    return mem


def create_from_taxonomy(OTTtax_filename, sources, OTT_ptrs, extra_taxonomy_file=None):
    """
    Creates object data and a source_ptrs array pointing to elements within it.
    Also fills out the OTT_ptrs array to point to the right place. OTT_ptrs can be
    partially filled: new OTT numbers are simply appended OTT id in the taxonomy.

    src ids are ints where possible, although can be strings if they contain characters

    "extra_taxonomy_map" allows us to inject mappings that are missing from the OpenTree
    e.g.
    """

    unused_sources = set()
    source_ptrs = {s: {} for s in sources}

    # hack for NCBI_via_silva
    # (see https://groups.google.com/d/msg/opentreeoflife/L2x3Ond16c4/CVp6msiiCgAJ)
    silva_regexp = re.compile(r"ncbi:(\d+),silva:([^,$]+)")
    # keep ncbi_id as ncbi_silva, but chop off the silva ID as it's not used in wikidata/EoL
    silva_sub = r"ncbi_silva:\1"

    data_files = [OTTtax_filename]
    if extra_taxonomy_file is not None:
        try:
            data_files.append(extra_taxonomy_file)
        except FileNotFoundError:
            logging.warning(f" Extra taxonomy file '{extra_taxonomy_file}' not found, so ignored")

    used = 0
    for fn in data_files:
        with open(fn, encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter="\t")
            for OTTrow in reader:
                # first 2 lines are header & blank in taxonomy.tsv
                if ((reader.line_num - 2) % 1000000 == 0) and reader.line_num > 2:
                    logging.info(
                        f"Reading taxonomy file {fn}: {reader.line_num-2} rows read, "
                        f"{used} identifiers used,  mem usage {mem():.1f} Mb"
                    )
                try:
                    OTTid = int(OTTrow["uid"])
                except ValueError:
                    OTTid = OTTrow["uid"]
                    logging.warning(f" Found an ott value which is not an integer: {OTTid}")

                sourceinfo = silva_regexp.sub(silva_sub, OTTrow["sourceinfo"])
                ncbi = False
                for srcs in reversed(sourceinfo.split(",")):
                    # look at sources in reverse order, overwriting, so 1st ones take priority
                    src, src_id = srcs.split(":", 1)
                    if src == "ncbi":
                        ncbi = True
                    elif (src == "ncbi_silva") and (not ncbi):
                        # only use the ncbi_via_silva id if no 'normal' ncbi already set
                        src = "ncbi"
                    if src not in source_ptrs:
                        if src not in unused_sources:
                            logging.info(f" New and unused source: {src} (in '{srcs}')")
                        unused_sources.update([src])
                        continue
                    used += 1
                    if src_id.isdigit():
                        src_id = int(src_id)
                    source_ptrs[src][src_id] = {"id": src_id}
                    try:
                        OTT_ptrs[OTTid]["sources"][src] = source_ptrs[src][src_id]
                        OTT_ptrs[OTTid]["rank"] = OTTrow["rank"]
                    except LookupError:
                        pass

    logging.info(
        f"✔ created {used} source pointers for {len(source_ptrs)} sources "
        f"{list(source_ptrs.keys())}. Mem usage {mem():.1f} Mb"
    )
    return source_ptrs


# P31 (instance of) values to search for
# See https://en.wikipedia.org/wiki/Template:Taxonbar/whitelist for the full list
match_taxa = {
    16521: "taxon",
    310890: "monotypic taxon",
    47487597: "monotypic fossil taxon",
    2568288: "ichnotaxon",
    23038290: "fossil taxon",
    59278506: "ootaxon",
    98961713: "extinct taxon",
    58051350: "paraphyletic group",
    42621: "hybrid",
    235536: "incertae sedis",
    713623: "clade",
    848328: "serotype",
    857968: "Candidatus",
    17487588: "unavailable combination",
    124477390: "taxon hypothesis",
}
match_vernacular = {
    502895: "common name",
    55983715: "group of organisms known by one particular common name",
}
match_synonym = {
    1040689: "synonym",
}


def wikidata_info(
    wikidata_json_dump_file,
    source_ptrs,
    wikilang,
    EOLid_property_id="P830",
    IUCNid_property_id=("P141", "P627"),
    IPNIid_property_id="P961",
):
    """
    Returns 3 dicts, ***_to_WD that all point to the same set of WikidataLinks instances,
    plus a dict of replacements, and a
    (1) Q_to_WD: A dict mapping Wikidata Qids to .
    (2) WPname_to_WD: An alterative dict mapping names in the wikilang Wikipedia to some
            of the same WikidataLinks instances as (1)
    (3) src_to_WD: A dict of dicts based on the source_ptrs in source_ptrs_filename such
            that src_to_WD[SRC][ID] -> some of the same WikidataLinks instances as (1)
    (4) replace_Q: A dict of taxon item Q to (Q, label) replacement, where the
            replacement is usually the QID of a wikidata item that is a common-name
            alternative to the official taxon item
    (5) info: a dict containing 'bytes_read' (the total number of bytes read, so we can
        check we have everything), and if EOLid_property_id is given, 'n_eol' (the number
        of WD items with EoL ids), and likewise for IUCN / IPNI
    From these we can set up a global dict mapping QIDs to links + popularity stats

    Note that titles could be unicode, e.g. 'Günther's dwarf burrowing skink',
    'Gölçük toothcarp', 'Galium × pomeranicum'. We replace underscores with spaces so
    that they match against page size & page counts (views).

    If a wikilang is present, also store the wikipedia page title for that language.

    If an EOLid_property_id, IUCN id, or IPNI id exists, save these too (NB: the IUCN id
    is present as Property:P627 of claim P141. It may also be overwritten by an ID
    subsequently extracted from the EOL identifiers list)

    Some taxa (especially common ones) have most sitelinks in a 'common name' item, e.g.
    cattle (Q830) contains most language sitelinks for the taxon items
    Q46889 (Bos primigenius indicus), Q20747320 (Bos primigenius taurus),
    Q20747334 (Bos taurus *+), Q20747712, Q20747726, etc.
    (* marks the name used in OneZoom, + for OpenTree).
    These 'common name' pages point to the taxon by having a property P31 ('instance of') set
    to 'organisms known by a particular common name' (Q55983715) of (P642)
    (locate them at https://w.wiki/enx).
    To spot these, we look for wikidata items that are common names, and link to items
    that are taxa. If the taxon has no wikipedia link in the specified language, we
    should use the common name WD item instead.

    Additionally, taxa like Homo sapiens might have *two* wikipedia pages,
    https://en.wikipedia.org/wiki/Homo_sapiens and https://en.wikipedia.org/wiki/Human.
    I code around these by hand (yuck).

    For each taxon line in the dump, we store the relevant information in a dict which
    contains the Qid and identifiers for EoL, IPNI, and IUCN, and an array of languages
    in the 'l' field e.g. wikidata_taxon_info[Qid] = {'Q':Qid, 'l':['en','fr'],
    'EoL':EoLid, 'IUCN': IUCNid, 'IPNI':IPNIid}

    We map it to NCBI etc identifiers using the function JSON_contains_known_dbID(), and
    if the mapping is successful (i.e. we may be using this taxon), we store it in
    wikidata_taxon_info[Qid]

    We also store the few common-name wikidata pages in a separate variable,
    wikidata_cname_info. Then, if the equivalent taxon exists, and it has no
    `wikilang`.wikipedia.org sitelink (or is a special case), we set 'Q' and 'l' to the new
    """  # noqa: RUF002
    Q_to_WD = {}
    WPname_to_WD = {}
    replace_Q = {}
    src_to_WD = defaultdict(dict)
    info = {"bytes_read": 0}

    regexp_match = "|".join([str(v) for v in list(match_taxa) + list(match_vernacular)])
    quick_byte_match = re.compile(rf'numeric-id":(?:{regexp_match})\D')
    with open_file_based_on_extension(wikidata_json_dump_file, "rt") as WDF:
        for line_num, line in enumerate(WDF):
            if line_num % 100000 == 0:
                more_info = ""
                if EOLid_property_id:
                    more_info += f", {info.get('n_eol', 0)} with EoL ids"
                if IUCNid_property_id:
                    more_info += f", {info.get('n_iucn', 0)} with IUCN ids"
                if IPNIid_property_id:
                    more_info += f", {info.get('n_ipni', 0)} with IPNI ids"
                logging.info(
                    f"{line_num} of wikidata JSON dump read. " f"relevant items{more_info}. Mem usage {mem():.1f} Mb"
                )
            # this file is in byte form, so must match byte strings
            if not (line.startswith('{"type":"item"') and quick_byte_match.search(line)):
                continue

            # done fast match, now check by parsing JSON (slower)
            json_item = json.loads(line.rstrip().rstrip(","))
            try:
                is_taxon = False
                alternate_Qs = set()
                claims = json_item["claims"]
                instance_of = claims["P31"]
            except KeyError:
                continue
            for i in instance_of:
                nid = wikidata_value(i.get("mainsnak")).get("numeric-id")
                if nid is None:
                    continue
                assert nid == nid + 0  # Check it's an int
                if nid in match_taxa:
                    is_taxon = True
                elif nid in match_vernacular or nid in match_synonym:
                    for alt in i.get("qualifiers", {}).get("P642", []):
                        alternate_Qs.add(wikidata_value(alt).get("numeric-id"))
                    if not alternate_Qs:
                        logging.debug(
                            " Found a common name property without any qualifiers for "
                            f"Q{Qid(json_item)} ({label(json_item)}). The name may be "
                            "poly/paraphyletic (e.g. 'slugs', 'coral', 'rabbit', "
                            "'whale') or a name corresponding to a clade with no "
                            "official taxonomic name (e.g. the 2 spp of minke whales "
                            "within a larger genus, or the 2 genera of peafowl), or "
                            "something else (e.g. the 'mysterious bird of Bobairo')"
                        )

            # Also process taxon synonyms as potential alternate Qs
            # It's a different type of synonyms from the P642 above
            if "P1420" in json_item["claims"]:
                for i in json_item["claims"]["P1420"]:
                    alternate_Qs.add(wikidata_value(i["mainsnak"])["numeric-id"])

            if is_taxon or len(alternate_Qs):
                item_instance = WikidataItem(json_item)
                wikipedia_name = item_instance.add_sitelinks_and_get_title(json_item, wikilang)
                if wikipedia_name:
                    WPname_to_WD[wikipedia_name] = item_instance
                for src, src_id in JSON_contains_known_dbID(json_item, source_ptrs).items():
                    src_to_WD[src][src_id] = item_instance
                Q_to_WD[item_instance.Q] = item_instance

                if EOLid_property_id:
                    try:
                        eolid = wikidata_value(claims[EOLid_property_id][0]["mainsnak"])
                        if eolid:
                            item_instance.EoL = int(eolid)
                            info["n_eol"] = info.get("n_eol", 0) + 1
                    except LookupError:
                        pass  # no EOL id
                    except ValueError:
                        logging.warning(
                            f" Cannot convert EoL property {eolid} to integer"
                            f" in Q{item_instance.Q} ({label(json_item)})."
                        )
                if IUCNid_property_id:
                    try:
                        # IUCN number is stored as a reference
                        for ref in claims[IUCNid_property_id[0]][0]["references"]:
                            try:
                                iucn = wikidata_value(ref["snaks"][IUCNid_property_id[1]][0])
                                if iucn:
                                    item_instance.iucn = int(iucn)
                                    info["n_iucn"] = info.get("n_iucn", 0) + 1
                                    break
                            except LookupError:
                                pass  # no IUCN id value
                    except LookupError:
                        pass  # no IUCN property
                    except ValueError:
                        logging.warning(
                            f" Cannot convert IUCN property {iucn} to integer"
                            f" in Q{item_instance.Q} ({label(json_item)})."
                        )
                if IPNIid_property_id:
                    try:
                        ipni = wikidata_value(claims[IPNIid_property_id][0]["mainsnak"])
                        # convert e.g. 391732-1 to 3917321, assume last digit prefixed by dash
                        if ipni:
                            item_instance.ipni = ipni.replace("-", "")
                            info["n_ipni"] = info.get("n_ipni", 0) + 1
                    except LookupError:
                        pass  # no IPNI id
                    except ValueError:
                        logging.warning(
                            f" Cannot convert IPNI property {ipni} to integer"
                            f" in Q{item_instance.Q} ({label(json_item)})."
                        )
                try:
                    # Save the ott coming from the wikidata item, if any
                    item_instance.wd_ott = int(claims["P9157"][0]["mainsnak"]["datavalue"]["value"])
                except (KeyError, ValueError):
                    pass

                # Only map alternate Qs if current item has a main language link
                # Otherwise, it's likely not an interesting item to map to, and it may
                # end up overridding a better existing mapping
                if wikilang in item_instance.l:
                    for original_taxon_QID in alternate_Qs:
                        replace_Q[original_taxon_QID] = (
                            item_instance.Q,
                            label(json_item),
                        )
            # Check for matching instances that don't seem to be taxa
            elif 13406463 in instance_of:
                # this is a "Wikimedia list article" (Q13406463), which explains why a taxon
                # Qid might be present (e.g. "List of Lepidoptera that feed on Solanum" which
                # is a "list of" taxon): ignore it without printing a message
                pass
            elif 4167836 in instance_of:
                # this is a "Wikimedia category" (Q4167836), which explains why a taxon Qid
                # might be present e.g. "Category:Species described in 2016", which is a
                # "category combines topics" taxon: ignore it without printing a message
                pass
            elif 19887878 in instance_of:
                # a wikimedia template (Q19887878): ignore it without printing a message
                pass
            else:
                # possibly flag up problems here, in case there are taxa which are instances
                # of more specific types, e.g. ichnotaxon, etc etc.
                logging.debug(
                    f" Possible problem with wikidata item Q{Qid(json_item)} "
                    f" ({label(json_item)}): might be a taxon but cannot get taxon data"
                )
    return Q_to_WD, WPname_to_WD, src_to_WD, replace_Q, info


def overwrite_wd(Q_to_WD, Q_replacements, only_if_more_popular, check_lang=None):
    """
    Overwrite Q items in Q_to_WD with replacement values (this includes overwriting
    the sitelinks and the popularity values). If check_lang is given, we only consider
    overwriting if there is a sitelink in the replacement Q item in that language. If
    only_if_more_popular=True, only replace if the replacement raw_popularity is greater
    """
    changed = set()
    for origQ, (newQ, label) in Q_replacements.items():
        if origQ not in Q_to_WD:
            continue  # Could be a mistake in the JSON, pointing to the wrong Qid
        force_overwrite = True
        if only_if_more_popular:
            force_overwrite = None
        if check_lang is None or check_lang in Q_to_WD[newQ].l:
            if force_overwrite:
                logging.info(f" Updating Q{origQ} with Qid and sitelinks from Q{newQ} ({label}).")
            else:
                logging.info(f" Checking Q{origQ} for possible replacement with Q{newQ} ({label}).")
            Qchanged = Q_to_WD[origQ].merge_and_overwrite(Q_to_WD[newQ], force_overwrite, label)
            if Qchanged:
                if newQ in changed:
                    logging.warning(
                        f"The common name wikidata item Q{newQ} has been used for more "
                        f"than one taxon item (last was {origQ}): this may cause "
                        "duplicate use of the same popularity measure."
                    )
                changed.add(newQ)
    return


def identify_best_wikidata(OTT_ptrs, lang, order_to_trust):
    """
    Each OTT number may point to several wiki entries, one for the NCBI number, another
    for the WORMS number, etc etc. Hopefully these will point to the same entry, but they
    may not. If they are different we need to choose the best one to use. We set
    OTT_ptrs[OTTid]['wd'] to the entry with the most numbers supporting this entry. In
    the case of a tie, if only one has a wikipedia entry in 'lang', we pick that one or
    otherwise we pick the one associated with the lowest (nearest 0) order_to_trust value
    """
    OTTs_with_wd = allOTTs = 0
    for OTTid, data in OTT_ptrs.items():
        try:
            if OTTid < 0:
                logging.warning(f" Skipped negative ott {OTTid} (unlabelled node) during wikidata map")
                continue
        except TypeError:
            pass
        allOTTs += 1
        choose = OrderedDict()
        for src in order_to_trust:
            try:
                Q = data["sources"][src]["wd"].Q
                choose[Q] = [*choose.get(Q, []), src]
            except KeyError:
                pass
        if len(choose) == 0:
            data["wd"] = {}  # for future referencing, it is helpful to have a blank array here
        else:
            OTTs_with_wd += 1
            # Sort by presence of wikipedia link in the given lang, keeping order if tied
            linked_src = sorted(  # items for a Q should point to the same wd => take x[0]
                choose.values(),
                key=lambda x: lang in data["sources"][x[0]]["wd"].l,
                reverse=True,
            )
            # re-sort so the list with more srcs comes first, keeping order if tied
            best_src = sorted(linked_src, key=len, reverse=True)[0][0]
            data["wd"] = data["sources"][best_src]["wd"]
            if len(choose) > 1:
                logging.info(
                    f"  More than one wikidata ID {list(choose.keys())} for ott {OTTid}," f" chosen {data['wd'].Q}"
                )
    logging.info(
        f" ✔ {allOTTs} final OpenTree taxa of which {OTTs_with_wd} "
        f"({OTTs_with_wd/allOTTs*100:.2f}%) have wikidata entries. Mem usage {mem():.1f} Mb"
    )


def add_pagesize_for_titles(wiki_title_ptrs, wikipedia_SQL_filename):
    """
    looks through the sql insertion file for page sizes. This file has extremely long lines
    with each csv entry brace-delimited within a line, e.g.

    INSERT INTO `page` VALUES (45286,0,'Bonobo',0,0,0.7789633346525611,'20221229182135',\
        '20230101050331',1129925767,107184,'wikitext',NULL),(15133411,3,'Chimpanzee',0,0,\
        0.850488449808,'20221102052637','20221102054547',1036955110,8862,'wikitext',NULL)

    The second entry (column 2) within each brace gives the namespace (we need namespace=0 for
    'normal' pages). Column 3 gives the title (in unicode). e.g. 'Bonobo' in the first example
    The page length is in Column 10. e.g. 107184 in the first example

    Note that titles have had spaces replaced with underscores

    See https://www.mediawiki.org/wiki/Manual:Page_table for a description of all entries.
    Note that when using the latest dump version, entries marked as deprecated are absent
    (e.g. page_counter)
    """
    used = 0
    # the column numbers for each datum are specified in the SQL file, and hardcoded here.
    page_table_namespace_column = 2
    page_table_title_column = 3
    page_table_pagelen_column = 10
    # use csv reader as it copes well e.g. with escaped SQL quotes in fields etc.
    with open_file_based_on_extension(wikipedia_SQL_filename, "rt") as file:
        pagelen_file = csv.reader(file, quotechar="'", escapechar="\\", doublequote=False)
        match_line = "INSERT INTO `page` VALUES"
        for fields in filter(
            lambda x: False if len(x) == 0 else x[0].startswith(match_line),
            pagelen_file,
        ):
            if pagelen_file.line_num % 500 == 0:
                logging.info(
                    "Reading page details from SQL dump to find page sizes: "
                    f"{pagelen_file.line_num} lines ({pagelen_file.line_num*1000} pages)"
                    f" read. Mem usage {mem():.1f} Mb"
                )
            field_num = 0
            # the records are all on the same line, separated by '),(',
            # so we need to count fields into the line.
            for f in fields:
                try:
                    if f.lstrip()[0] == "(":
                        field_num = 0
                        namespace = None
                        title = None
                except IndexError:
                    pass
                field_num += 1
                if field_num == page_table_namespace_column:
                    namespace = f
                if field_num == page_table_title_column:
                    title = f
                elif field_num == page_table_pagelen_column and namespace == "0":
                    if title in wiki_title_ptrs:
                        wiki_title_ptrs[title].pagesize = int(f)
                        used += 1
    n_titles = len(wiki_title_ptrs)
    logging.info(
        f" ✔ Of {n_titles} taxon page names, found page size data for {used} "
        f"({(used/n_titles * 100):.2f}%). Mem usage {mem():.1f} Mb"
    )


def pageviews_for_titles(
    filename,
    wiki_titles,
    wikilang,
    wiki_suffix="z",
):
    """
    Return a dict mapping wiki_title => monthly pageview

    wiki_suffix taken from https://dumps.wikimedia.org/other/pagecounts-ez/
    [
        b (wikibooks),
        k (wiktionary),
        n (wikinews),
        o (wikivoyage),
        q (wikiquote),
        s (wikisource),
        v (wikiversity),
        z (wikipedia)
    ]

    In more recent files, missing values indicate <5 hits in that month, so wset these to 0

    NB: see https://dumps.wikimedia.org/other/pagecounts-ez/ for format.
    Pageviews totals files have a wikicode project name in ascii followed by .z for wikipedias
    (e.g. en.z) followed by space, followed by uri-escaped title, followed by space, followed
    by integer. The format is a very difficult one to parse, as it varies e.g. there are
    multiple differently quoted version of the same title, sometime with spaces not
    underscores, unicode encoding sometimes fails, the bzip file sometimes appears truncated,
    etc etc. I've found that the best way to do this is to unquote_to_bytes first
    (to remove uri-encoding), then convert to unicode.
    In fact, the encoding is unclear, and sometimes utf-8 encoding seems to fail, so we
    pass on any utf-8 conversion errors. Hopefully this should only affect a few taxa where
    the page title has odd accents that have not been either uri-escaped, or properly encoded
    in utf-8.
    """
    pageviews = defaultdict(int)

    with open_file_based_on_extension(filename, "rt") as PAGECOUNTfile:
        for n, line in enumerate(PAGECOUNTfile):
            if n % 10000000 == 0:
                logging.info(
                    f"read {n} lines of pageviews file " f"{os.path.basename(filename)}. Mem usage {mem():.1f} Mb"
                )

            info = line.split(" ")
            title = info[0]
            views = info[1]
            if title in wiki_titles:
                # We should not have duplicates in the preprocessed pageviews file
                assert title not in pageviews
                pageviews[title] = int(views)

    return pageviews


def sum_popularity_over_tree(tree, OTT_ptrs=None, exclude=None, pop_store="pop", verbosity=0):
    """
    Add popularity indices for branch lengths based on a phylogenetic tree (and return the
    tree, or the number of root descendants).
    We might want to exclude some names from the popularity metric (e.g. exclude archosaurs,
    to ensure birds don't gather popularity intended for dinosaurs). This is done by passing
    an array such as ['Dinosauria_ott90215', 'Archosauria_ott335588'] as the exclude argument.

    'tree' can be the name of a tree file or a dendropy tree object

    'pop_store' is the name of the attribute in which to store the popularity. If you wish to
    create a tree with popularity on the branches, you can pass in pop_store='edge_length'

    NB: if OTT_ptrs is given, then the raw popularity is stored in the object pointed to by
    OTT_ptrs[OTTid]['wd'], where OTTid can be extracted from the node label in the tree.
    If OTT_ptrs is None, then the popularity is stored in the node object itself, in
    Node.data['wd']['pop'].

    Popularity summed up and down the tree depends on the OpenTree structure, and is stored in
    OTT_ptrs[OTTid]['pop_ancst'] (popularity summed upwards for all ancestors of this node)
    and OTT_ptrs[OTTid]['pop_dscdt'] (popularity summed over all descendants). To get a
    measure of the sum of both ancestor and descendant popularity, just add these together

    We also count up the *number* of edges above each node to the root and the number of those
    that have a popularity measure. These are stored in

    OTT_ptrs[OTTid]['n_ancst'] and OTT_ptrs[OTTid]['n_pop_ancst']

    we also flag up the poor seed plants (Spermatophyta_ott1007992) - we could add a little
    to their pop value later
    """
    from dendropy import Tree

    if exclude is None:
        exclude = []
    if not isinstance(tree, Tree):
        tree = Tree.get(
            file=tree,
            schema="newick",
            suppress_edge_lengths=True,
            preserve_underscores=True,
            suppress_leaf_node_taxa=True,
        )

    logging.info(f" Tree read for phylogenetic popularity calc: mem usage {mem():.1f} Mb")

    # put popularity into the pop_store attribute
    for node in tree.preorder_node_iter():
        if node.label in exclude:
            node.pop_store = 0
            node.has_pop = False
        else:
            try:
                node.pop_store = node.data["wd"].raw_popularity
                node.has_pop = True
            except (LookupError, AttributeError):
                node.pop_store = 0
                node.has_pop = False

    # go up the tree from the tips, summing up the popularity indices beneath and
    # adding the number of descendants
    for node in tree.postorder_node_iter():
        if node.is_leaf():
            node.descendants_popsum = 0
            node.n_descendants = 0
        try:
            node._parent_node.n_descendants += 1 + node.n_descendants
            node._parent_node.descendants_popsum += node.pop_store + node.descendants_popsum
        except AttributeError:  # could be the first time we have checked the parent
            try:
                node._parent_node.n_descendants = 1 + node.n_descendants
                node._parent_node.descendants_popsum = node.pop_store + node.descendants_popsum
            except AttributeError:  # this could be the root, with node._parent_node = None
                pass
                # root_descendants = node.n_descendants

    # go down the tree from the root, summing up the popularity indices above,
    # and summing up numbers of nodes
    for node in tree.preorder_node_iter():
        if node.parent_node is None:
            # this is the root.
            node.seedplant = False
            node.n_ancestors = 0
            node.n_pop_ancestors = 0
            node.ancestors_popsum = 0.0
        else:
            node.n_ancestors = node._parent_node.n_ancestors + 1
            node.ancestors_popsum = node._parent_node.ancestors_popsum + node.pop_store
            if getattr(node, "has_pop", None):
                node.n_pop_ancestors = node._parent_node.n_pop_ancestors + 1
            else:
                node.n_pop_ancestors = node._parent_node.n_pop_ancestors
            if node.label and node.label == "Spermatophyta":
                node.seedplant = True
                logging.info("Found plant root")
            else:
                node.seedplant = node._parent_node.seedplant

    # place these values into the OTT_ptrs structure
    if OTT_ptrs:
        for node in tree.preorder_node_iter():
            try:
                OTT_ptrs[int(node.label.rsplit("_ott", 1)[1])]["pop_self"] = node.pop_store
                OTT_ptrs[int(node.label.rsplit("_ott", 1)[1])]["pop_ancst"] = (
                    node.ancestors_popsum
                )  # nb, this includes popularity of self
                OTT_ptrs[int(node.label.rsplit("_ott", 1)[1])]["pop_dscdt"] = node.descendants_popsum
                OTT_ptrs[int(node.label.rsplit("_ott", 1)[1])]["n_ancst"] = node.n_ancestors
                OTT_ptrs[int(node.label.rsplit("_ott", 1)[1])]["n_dscdt"] = node.n_descendants
                OTT_ptrs[int(node.label.rsplit("_ott", 1)[1])]["n_pop_ancst"] = node.n_pop_ancestors
                OTT_ptrs[int(node.label.rsplit("_ott", 1)[1])]["is_seed_plant"] = node.seedplant
            except (LookupError, AttributeError):
                pass
    return tree
