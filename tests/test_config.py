from prepare.config import Config


def test_singleton():
    assert Config() is Config()
