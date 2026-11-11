def pytest_addoption(parser):
    parser.addoption("--run-ptt-ui", action="store_true", default=False,
                     help="Run push-to-talk integration tests with real Tk widgets.")
