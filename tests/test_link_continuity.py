import sys, os, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'core'))
import link_continuity
class C:
 def __init__(self): self.sent=[]
 def poslji_sync(self,*a): self.sent.append(a); return True
 def zahtevaj_sync(self,*a): self.sent.append(a); return True
class T(unittest.TestCase):
 def test_sanitize_secrets(self): self.assertNotIn('token',link_continuity.sanitize({'url':'https://x','token':'secret'}))
 def test_independent_items_and_resume(self):
  c=C(); a=link_continuity.Continuity(lambda:c)
  a.publish({'surface':'media','url':'https://a','media_position':10,'updated_at':10})
  a.publish({'surface':'browser','url':'https://b','title':'B','updated_at':20})
  self.assertEqual(len(a.items),2); self.assertEqual(a.resume_for({'surface':'media','url':'https://a'})['media_position'],10)
 def test_remote_is_passive_and_merges(self):
  got=[]; b=link_continuity.Continuity(lambda:C(),got.append)
  self.assertTrue(b.receive({'category':link_continuity.CATEGORY,'version':30,'data':{'items':{
   'x':{'surface':'media','url':'https://x','media_position':42,'updated_at':30},
   'y':{'surface':'media','url':'https://y','media_position':7,'updated_at':29}}}}))
  self.assertEqual(len(b.items),2); self.assertTrue(got[0]['passive'])
  self.assertEqual(b.resume_for({'surface':'media','url':'https://x'})['media_position'],42)
 def test_old_update_does_not_overwrite_newer_item(self):
  b=link_continuity.Continuity(lambda:C()); b.receive({'category':link_continuity.CATEGORY,'version':100,'data':{'items':{'x':{'surface':'media','url':'https://x','media_position':50,'updated_at':100}}}})
  b.receive({'category':link_continuity.CATEGORY,'version':101,'data':{'items':{'x':{'surface':'media','url':'https://x','media_position':5,'updated_at':90}}}})
  self.assertEqual(b.resume_for({'surface':'media','url':'https://x'})['media_position'],50)
if __name__=='__main__': unittest.main()
