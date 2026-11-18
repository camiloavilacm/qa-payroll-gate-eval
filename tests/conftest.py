import sys

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--disable-socket",
        action="store_true",
        help="Deny socket construction via Python audit hooks",
    )


def pytest_configure(config: pytest.Config) -> None:
    if config.getoption("--disable-socket"):

        def deny(event: str, args: tuple[object, ...]) -> None:
            if event == "socket.__new__":
                raise AssertionError("Network forbidden during offline checks")

        sys.addaudithook(deny)
