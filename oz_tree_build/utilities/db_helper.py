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
