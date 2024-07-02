"""
Useful functions for getting database stuff when used as a standalone script
"""

import configparser
import logging
import os
import re
import sys
from pydal import DAL


logger = logging.getLogger(__name__)

def is_sqlite(db): 
    return db._adapter.driver_name.startswith("sqlite")

def connect_to_database(database=None, conf_file=None):
    if database is None:
        database = read_config(conf_file).get("db", "uri")
    db = DAL(database)
    if is_sqlite(db):
        # This is running using a test sqlite db, so we need to define the tables
        if not os.path.exists(db._adapter.dbpath):
            logger.info(f"Defining {database} tables.")
            db.executesql(
                'CREATE TABLE images_by_ott (id INTEGER PRIMARY KEY AUTOINCREMENT, '
                'ott INTEGER,  src INTEGER, src_id INTEGER, url TEXT, '
                'rating INTEGER, rating_confidence INTEGER, '
                'rights TEXT,  licence TEXT, updated TIMESTAMP, '
                'best_any INTEGER, overall_best_any INTEGER, '
                'best_verified INTEGER, overall_best_verified INTEGER, '
                'best_pd INTEGER, overall_best_pd INTEGER);'
            )
            db.executesql(
                'CREATE TABLE vernacular_by_ott (id INTEGER PRIMARY KEY AUTOINCREMENT, '
                'ott INTEGER, vernacular TEXT, lang_primary TEXT, lang_full TEXT, '
                'preferred INTEGER, src INTEGER, src_id INTEGER, updated TIMESTAMP);'
            )
            db.executesql(
                'CREATE TABLE ordered_leaves (id INTEGER PRIMARY KEY AUTOINCREMENT, '
                'parent INTEGER, real_parent INTEGER, name TEXT, extinction_date DOUBLE,'
                'ott INTEGER, wikidata INTEGER, wikipedia_lang_flag INTEGER, eol INTEGER, iucn TEXT, '
                'raw_popularity DOUBLE, popularity DOUBLE, popularity_rank INTEGER, '
                'ncbi INTEGER, ifung INTEGER, worms INTEGER, irmng INTEGER, gbif INTEGER, ipni INTEGER, price INTEGER);'
            )
    return db

def placeholder(db):
    return "?" if is_sqlite(db) else "%s"

# Delete all rows in a table for a given ott.
# It's usable for any table that has an ott column.
def delete_all_by_ott(db, table, ott):
    sql = f"DELETE FROM {table} WHERE ott={placeholder(db)};"
    db.executesql(sql, (ott, ))
    
def get_next_src_id_for_src(db, src):
    # Get the highest bespoke src_id, and add 1 to it for the new image src_id
    ph = placeholder(db)
    max_src_id = db.executesql(
        f"SELECT MAX(src_id) AS max_src_id FROM images_by_ott WHERE src={ph};",
        (src, ),
    )
    return max_src_id[0][0] + 1 if max_src_id[0][0] else 1


def read_config(conf_file=None):
    """
    Read the passed-in configuration file, defaulting to the standard appconfig.ini
    """

    if conf_file is None:
        conf_file = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "../../../OZtree/private/appconfig.ini",
        )
    if not os.path.exists(conf_file):
        raise ValueError(f"Appconfig file {conf_file} cannot be found.")
    config = configparser.ConfigParser()
    config.read(conf_file)
    return config
