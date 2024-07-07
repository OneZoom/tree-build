import pytest

from oz_tree_build.utilities.db_helper import connect_to_database


def pytest_addoption(parser):
    parser.addoption(
        "--conf-file",
        action="store",
        help="A path to the appconfig.ini file containing the database location and pw",
        default=None,
    )
    parser.addoption(
        "--keep-rows",
        action="store_true",
        help="Keep test rows (with negative otts) in the database for manual checking",
    )
    parser.addoption(
        "--real-apis",
        action="store_true",
        help="Make real internet requests to APIs, instead of mocking the responses",
    )


@pytest.fixture(scope="session")
def conf_file(request):
    return request.config.getoption("--conf-file")


@pytest.fixture(scope="session")
def keep_rows(request):
    return request.config.getoption("--keep-rows")


@pytest.fixture(scope="session")
def real_apis(request):
    return request.config.getoption("--real-apis")


@pytest.fixture(scope="class", autouse=True)
def db(conf_file):
    db = connect_to_database(conf_file=conf_file)
    yield db
    db.close()


def pytest_collection_modifyitems(config, items):
    if config.getoption("--real-apis"):
        skip_real_api = pytest.mark.skip(
            reason="skipped because testing against real APIs"
        )
        for item in items:
            if "skip_real_api" in item.keywords:
                item.add_marker(skip_real_api)
