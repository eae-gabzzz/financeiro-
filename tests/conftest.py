import pytest

from tests.fakes import FakeFirestore


@pytest.fixture
def db():
    return FakeFirestore()
