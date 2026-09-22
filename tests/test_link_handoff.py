import unittest
from core import link_handoff
class T(unittest.TestCase):
 def test_clean(self):
  self.assertIsNone(link_handoff.clean_payload({'url':'file:///x'}))
  self.assertEqual(link_handoff.clean_payload({'url':'https://x','position':12})['position'],12)
 def test_target(self): self.assertEqual(link_handoff.message('tv',{'url':'https://x'})['target'],'tv')
if __name__=='__main__':unittest.main()
