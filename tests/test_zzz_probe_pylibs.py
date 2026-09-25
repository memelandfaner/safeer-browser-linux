import unittest


class Probe(unittest.TestCase):
    def test_libs(self):
        found = {}
        for name in ("cryptography", "Crypto", "nacl", "cryptg"):
            try:
                mod = __import__(name)
                found[name] = getattr(mod, "__version__", "?")
            except Exception as e:
                found[name] = f"MISSING: {e}"
        print("LIBS:", found)

        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            k = AESGCM.generate_key(bit_length=256)
            a = AESGCM(k)
            ct = a.encrypt(b"\x00" * 12, b"hello", b"aad")
            pt = a.decrypt(b"\x00" * 12, ct, b"aad")
            print("AESGCM cryptography works:", pt == b"hello")
        except Exception as e:
            print("AESGCM cryptography FAILED:", e)

        import sys
        print("PYTHON:", sys.version)


if __name__ == "__main__":
    unittest.main()
