import configparser
import logging
import os
import re
import sys
from pydal import DAL


logger = logging.getLogger(__name__)



def connect_to_database(database=None, appconfig=None):

    if database is None:
        database = read_config(appconfig).get("db", "uri")
    return DAL(database)


# Delete all rows in a table for a given ott.
# It's usable for any table that has an ott column.
def delete_all_by_ott(db, table, ott):
    sql = f"DELETE FROM {table} WHERE ott=%s;"
    db.executesql(sql, ott)


def get_next_src_id_for_src(db, src):
    # Get the highest bespoke src_id, and add 1 to it for the new image src_id
    max_src_id = db.executesql(
        "SELECT MAX(src_id) AS max_src_id FROM OneZoom.images_by_ott WHERE src=%s;",
        src,
    )
    return max_src_id[0][0] + 1 if max_src_id[0][0] else 1


def read_config(config_file=None):
    """
    Read the passed-in configuration file, defaulting to the standard appconfig.ini
    """

    if config_file is None:
        config_file = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "../../../OZtree/private/appconfig.ini",
        )
    if not os.path.exists(config_file):
        raise ValueError(f"Appconfig file {config_file} cannot be found.")
    config = configparser.ConfigParser()
    config.read(config_file)
    return config
