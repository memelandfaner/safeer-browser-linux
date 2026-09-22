from core.link_multi_vnos import MultiInputRouter, EV_KEY, EV_ABS, EV_REL, ABS_X, REL_WHEEL

def test_opt_in_and_three_input_types():
    sent=[]; r=MultiInputRouter(lambda a,p: sent.append((a,p)) or True, '/ne-obstaja/*')
    assert not r.feed(EV_KEY,304,1)
    r.enabled=True
    assert r.feed(EV_KEY,304,1) and r.feed(EV_KEY,304,0)       # gamepad A
    assert r.feed(EV_KEY,17,1)                                 # keyboard W/up
    assert r.feed(EV_REL,REL_WHEEL,1)                           # mouse wheel
    assert r.feed(EV_ABS,ABS_X,16384)                           # analog stick
    assert [x[0] for x in sent] == ['gamepad.button','gamepad.button','input.key','input.scroll','gamepad.axis']

def test_release_is_explicit_and_idempotent():
    sent=[]; r=MultiInputRouter(lambda a,p: sent.append((a,p)) or True)
    r.enabled=True; r.sprosti_vse(); r.sprosti_vse()
    assert sent == [('gamepad.release',{}),('gamepad.release',{})]


# unittest (tako jih pozene tudi `python3 -m unittest`, ne le pytest)
import unittest as _unittest


class Preizkusi(_unittest.TestCase):
    pass


for _ime, _f in list(globals().items()):
    if _ime.startswith("test_") and callable(_f):
        setattr(Preizkusi, _ime, (lambda f: lambda self: f())(_f))
