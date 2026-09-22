import unittest
from core.link_media_sync import sanitize, merge, MediaSync, CATEGORY
class C:
 def __init__(self):self.sent=[]
 def poslji_sync(self,*x):self.sent.append(x);return True
 def zahtevaj_sync(self,*x):return True
class T(unittest.TestCase):
 def test_sanitize(self):
  s=sanitize({'sources':[{'url':'https://e','updated':1},{'url':'file:///x'}],'progress':[{'id':'a','position':96,'duration':100},{'id':'b','position':20,'duration':100}]})
  self.assertEqual(len(s['sources']),1);self.assertEqual(len(s['progress']),1)
 def test_newer_item_wins(self):
  a={'favorites':[{'id':'1','url':'https://a','title':'old','updated':10}]};b={'favorites':[{'id':'1','url':'https://a','title':'new','updated':20}]}
  self.assertEqual(sanitize(merge(a,b,21))['favorites'][0]['title'],'new')
 def test_tombstone_wins(self):
  a={'favorites':[{'id':'1','url':'https://a','updated':10}]};b={'favorites':[{'id':'1','deleted':True,'updated':20}]}
  self.assertEqual(sanitize(merge(a,b,21))['favorites'],[])
 def test_concurrent_merge_even_old_envelope(self):
  c=C();m=MediaSync(lambda:c);m.publish({'favorites':[{'id':'a','url':'https://a','updated':100}]});m.version=999
  self.assertTrue(m.receive({'category':CATEGORY,'version':5,'data':{'favorites':[{'id':'b','url':'https://b','updated':200}]}}));self.assertEqual(len(m.state['favorites']),2)
if __name__=='__main__':unittest.main()
