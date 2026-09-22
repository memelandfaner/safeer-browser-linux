from core import link_daljinec

class Z:
    def __init__(self, tece=True): self.tece=tece; self.events=[]; self.released=0
    def stanje(self): return {'tece':self.tece}
    def oddaljeni_plosek(self,e): self.events.append(e); return True
    def sprosti_oddaljeni_plosek(self): self.released+=1

def call(action,p,z):
    out=[]
    link_daljinec.izvedi_control(action,p,lambda u:None,out.append,zaslon=z)
    return out[0]

def test_gamepad_is_optional_and_scoped_to_active_session():
    z=Z(False); assert not call('gamepad.button',{'button':'a','down':True},z)['ok']
    assert z.events==[]

def test_gamepad_button_axis_and_release():
    z=Z()
    assert call('gamepad.button',{'button':'a','down':True},z)['ok']
    assert z.events[-1]=={'vrsta':'plosek_gumb','gumb':'a','dol':True}
    assert call('gamepad.axis',{'axis':'leva_x','value':2},z)['ok']
    assert z.events[-1]['vrednost']==1.0
    assert call('gamepad.release',{},z)['ok'] and z.released==1

def test_gamepad_allowlist():
    z=Z(); assert not call('gamepad.button',{'button':'shell','down':True},z)['ok']; assert z.events==[]


# unittest (tako jih pozene tudi `python3 -m unittest`, ne le pytest)
import unittest as _unittest


class Preizkusi(_unittest.TestCase):
    pass


for _ime, _f in list(globals().items()):
    if _ime.startswith("test_") and callable(_f):
        setattr(Preizkusi, _ime, (lambda f: lambda self: f())(_f))
