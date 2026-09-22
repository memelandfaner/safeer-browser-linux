from core.link_continuity import Continuity, sanitize, activity_id_for
class C:
 def __init__(self): self.sent=[]
 def poslji_sync(self,*x): self.sent.append(x); return True
 def zahtevaj_sync(self,*x): return True

def test_parallel_activities_do_not_replace_each_other():
 c=C(); x=Continuity(lambda:c)
 assert x.publish_browser("https://example.com/a","A")
 assert x.publish_search("pink floyd")
 assert x.publish_file("safeer:file:123","notes.txt")
 assert x.publish_remote_app("org.videolan.vlc","VLC")
 assert len(x.items)==4
 assert x.resume_for({"kind":"browser","url":"https://example.com/a"})["title"]=="A"

def test_remote_merge_is_passive_and_per_item():
 events=[]; x=Continuity(lambda:None,events.append)
 a={"kind":"browser","url":"https://a","title":"A","updated_at":10}
 b={"kind":"search","query":"B","updated_at":11}
 payload={"category":"safeer.continuity.v3","version":12,"data":{"items":{"x":a,"y":b}}}
 assert x.receive(payload); assert len(x.items)==2; assert events[-1]["passive"] is True

def test_secrets_and_local_paths_never_sync():
 s=sanitize({"kind":"file","file_id":"id","local_path":"/home/me/x","token":"x","url":"file:///x"})
 assert "local_path" not in s and "token" not in s and "url" not in s

def test_stable_activity_id():
 assert activity_id_for({"kind":"search","query":"abc"})==activity_id_for({"kind":"search","query":"abc"})


# unittest (tako jih pozene tudi `python3 -m unittest`, ne le pytest)
import unittest as _unittest


class Preizkusi(_unittest.TestCase):
    pass


for _ime, _f in list(globals().items()):
    if _ime.startswith("test_") and callable(_f):
        setattr(Preizkusi, _ime, (lambda f: lambda self: f())(_f))
