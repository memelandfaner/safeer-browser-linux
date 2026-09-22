from core.link_workspace import Workspaces, sanitize
class C:
 def __init__(self): self.sent=[]
 def poslji_sync(self,*a): self.sent.append(a); return True

def test_workspace_keeps_parallel_contexts():
 c=C(); w=Workspaces(lambda:c); wid=w.begin('Film research')
 assert w.attach('a-film',wid); assert w.attach('a-search',wid); assert w.attach('a-file',wid)
 assert w.activities_for(wid)==['a-film','a-search','a-file']

def test_remote_workspace_is_passive():
 got=[]; w=Workspaces(lambda:None,got.append)
 p={'category':'safeer.workspace.v1','version':2,'data':{'items':{'w':{'workspace_id':'w','title':'X','activity_ids':['a'], 'updated_at':2}}}}
 assert w.receive(p); assert got[-1]['passive'] is True

def test_limits_and_sanitize():
 x=sanitize({'workspace_id':'w','title':'x','activity_ids':['a']*30,'token':'no'})
 assert 'token' not in x and len(x['activity_ids'])==1


# unittest (tako jih pozene tudi `python3 -m unittest`, ne le pytest)
import unittest as _unittest


class Preizkusi(_unittest.TestCase):
    pass


for _ime, _f in list(globals().items()):
    if _ime.startswith("test_") and callable(_f):
        setattr(Preizkusi, _ime, (lambda f: lambda self: f())(_f))
