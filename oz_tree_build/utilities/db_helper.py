import configparser
import logging
import os
import re
import sys


logger = logging.getLogger(__name__)


class DbContext:
    def __init__(self, db_connection, datetime_now, subs):
        self.db_connection = db_connection
        self._datetime_now = datetime_now
        self._subs = subs
        self.db_curs = db_connection.cursor()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.db_connection.close()

    def execute(self, sql, args):
        self.db_curs.execute(sql.format(self._subs, self._datetime_now), args)

    def fetchall(self, sql, args):
        self.execute(sql, args)
        return self.db_curs.fetchall()

    def fetchone(self, sql, args):
        self.execute(sql, args)
        return self.db_curs.fetchone()


def connect_to_database(database=None):

    if database is None:
        database = read_config().get("db", "uri")

    if database.startswith(
        "mysql://"
    ):  # mysql://<mysql_user>:<mysql_password>@localhost/<mysql_database>
        import pymysql

        match = re.match(r"mysql://([^:]+):([^@]*)@([^/]+)/([^?]*)", database.strip())
        if match.group(2) == "":
            # Raise an error if the password is not given
            raise ValueError("No password found for mysql database")
        pw = match.group(2)
        db_connection = pymysql.connect(
            user=match.group(1),
            passwd=pw,
            host=match.group(3),
            db=match.group(4),
            port=3306,
            charset="utf8mb4",
        )
        datetime_now = "NOW()"
        subs = "%s"
    else:
        logger.error("No recognized database specified: {}".format(database))
        sys.exit()

    return DbContext(db_connection, datetime_now, subs)


# Delete all rows in a table for a given ott.
# It's usable for any table that has an ott column.
def delete_all_by_ott(db_context, table, ott):
    sql = f"DELETE FROM {table} WHERE ott={{0}};"
    db_context.execute(sql, ott)
    db_context.db_connection.commit()


def get_next_src_id_for_src(db_context, src):
    # Get the highest bespoke src_id, and add 1 to it for the new image src_id
    max_src_id = db_context.fetchone(
        "SELECT MAX(src_id) AS max_src_id FROM OneZoom.images_by_ott WHERE src={0};",
        src,
    )
    return max_src_id[0] + 1 if max_src_id[0] else 1


def read_config(config_file=None):
    """
    Read the passed-in configuration file, defaulting to the standard appconfig.ini
    """

    if config_file is None:
        config_file = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "../../../OZtree/private/appconfig.ini",
        )

    config = configparser.ConfigParser()

    config.read(config_file)
    return config
