from pytest import fixture
from oz_tree_build.utilities.db_helper import connect_to_database

def pytest_addoption(parser):
    parser.addoption(
        "--conf-file",
        action="store",
        help="A path to the appconfig.ini file, that contains the database location and password",
        default=None
    )
    parser.addoption(
        "--keep-rows",
        action="store_true",
        help="Keep test rows (with negative otts) in the database so we can chek them manually",
    )
    parser.addoption(
        "--real-apis",
        action="store_true",
        help="Actually make requests to the online APIs, instead of using the mock responses.",
    )


@fixture(scope='session')
def conf_file(request):
    return request.config.getoption("--conf-file")

@fixture(scope='session')
def keep_rows(request):
    return request.config.getoption("--keep-rows")

@fixture(scope='session')
def real_apis(request):
    return request.config.getoption("--real-apis")

@fixture(scope='class', autouse=True)
def db(conf_file):
    db = connect_to_database(conf_file=conf_file)
    yield db
    db.close()

