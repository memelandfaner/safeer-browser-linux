import json, unittest, urllib.request

def beri(u):
    r = urllib.request.Request(u, headers={"User-Agent": "SafeerOS", "Accept": "application/json"})
    return json.loads(urllib.request.urlopen(r, timeout=30).read())

def poskusi(ime, f):
    try: print(ime, f())
    except Exception as e: print(ime, "NAPAKA", repr(e))

class T(unittest.TestCase):
    def test_vse(self):
        for s in ("tilvids.com", "framatube.org"):
            try:
                d = beri("https://%s/api/v1/search/videos?search=linux&sort=-views&nsfw=false&count=3&searchTarget=local" % s)["data"]
            except Exception as e:
                print(s, "ISKANJE NAPAKA", e); continue
            for v in d:
                gost = v["url"].split("/")[2]
                print(s, v["name"][:30], v["uuid"], gost)
                def izvor(): 
                    j = beri("https://%s/api/v1/videos/%s" % (gost, v["uuid"]))
                    return len(j.get("files", [])), [len(p.get("files", [])) for p in j.get("streamingPlaylists", [])]
                def lokalno():
                    j = beri("https://%s/api/v1/videos/%s" % (s, v["uuid"]))
                    f = j.get("files", []) + [x for p in j.get("streamingPlaylists", []) for x in p.get("files", [])]
                    return [x.get("fileUrl", "")[:60] for x in f][:2]
                poskusi("  IZVOR", izvor)
                poskusi("  LOKALNO", lokalno)
