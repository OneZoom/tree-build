from pytest import fixture

def pytest_addoption(parser):
    parser.addoption(
        "--appconfig",
        action="store",
        help="A path to the appconfig.ini file, that contains the database location and password",
        default=None
    )

@fixture(scope='session')
def appconfig(request):
    return request.config.getoption("--appconfig")
