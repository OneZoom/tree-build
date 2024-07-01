from pytest import fixture

def pytest_addoption(parser):
    parser.addoption(
        "--appconfig",
        action="store",
        help="A path to the appconfig.ini file, that contains the database location and password",
        default=None
    )
    parser.addoption(
        "--keep-rows",
        action="store_true",
        help="Keep test rows (with negative otts) in the database so we can chek them manually",
    )


@fixture(scope='session')
def appconfig(request):
    return request.config.getoption("--appconfig")

@fixture(scope='session')
def keep_rows(request):
    return request.config.getoption("--keep-rows")
