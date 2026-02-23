import os
import tempfile

import pytest

from eap.environment import ToolRegistry
from eap.protocol import StateManager


@pytest.fixture
def db_path():
    fd, path = tempfile.mkstemp(prefix="eap-tests-", suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def state_manager(db_path):
    return StateManager(db_path=db_path)


@pytest.fixture
def tool_registry():
    return ToolRegistry()

