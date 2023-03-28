from prepare.config import Config


def test_singleton():
    a = Config()
    b = Config()
    assert a is b
