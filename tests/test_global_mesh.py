import unittest
from core.global_mesh import Peer, MeshPolicy, Reachability as R, PresenceRecord, PresenceRegistry

class TestGlobalMesh(unittest.TestCase):
 def p(self,**kw):
  x=dict(device_id="d",paired=True,public_key_fingerprint="fp")
  x.update(kw); return Peer(**x)
 def test_routes(self):
  m=MeshPolicy(True,True)
  self.assertEqual(m.route(self.p(local_reachable=True,direct_internet_reachable=True,relay_reachable=True)),R.LOCAL)
  self.assertEqual(m.route(self.p(direct_internet_reachable=True,relay_reachable=True)),R.DIRECT_INTERNET)
  self.assertEqual(m.route(self.p(relay_reachable=True)),R.RELAY)
  self.assertEqual(MeshPolicy(False,True).route(self.p(relay_reachable=True)),R.OFFLINE)
  self.assertEqual(m.route(self.p(paired=False,relay_reachable=True)),R.OFFLINE)
 def test_presence_ttl(self):
  r=PresenceRegistry(); rec=PresenceRecord("d","fp",4102444800,["candidate"])
  r.announce(rec)
  self.assertIsNotNone(r.lookup("d",100))
  self.assertIsNone(r.lookup("d",4102444801))
