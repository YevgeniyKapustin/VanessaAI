from prepare.connection import Connection


def test_singleton():
    a = Connection()
    b = Connection()
    assert a is b


def test_init():
    i = Connection()
    assert i.longpoll and i.vk and i.upload and i.vk_admin
