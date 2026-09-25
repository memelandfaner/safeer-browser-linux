import subprocess
import tempfile
import os
import unittest


class Probe(unittest.TestCase):
    def test_openssl_version(self):
        r = subprocess.run(["openssl", "version"], capture_output=True, text=True)
        print("OPENSSL VERSION:", r.stdout, r.stderr)

    def test_ecdh_derive(self):
        d = tempfile.mkdtemp()
        k1 = os.path.join(d, "k1.pem")
        k2 = os.path.join(d, "k2.pem")
        pub2 = os.path.join(d, "pub2.pem")
        subprocess.run(["openssl", "ecparam", "-name", "prime256v1", "-genkey", "-noout", "-out", k1], check=True, capture_output=True)
        subprocess.run(["openssl", "ecparam", "-name", "prime256v1", "-genkey", "-noout", "-out", k2], check=True, capture_output=True)
        subprocess.run(["openssl", "pkey", "-in", k2, "-pubout", "-out", pub2], check=True, capture_output=True)
        r = subprocess.run(["openssl", "pkeyutl", "-derive", "-inkey", k1, "-peerkey", pub2], capture_output=True)
        print("DERIVE rc:", r.returncode, "stderr:", r.stderr, "secret_len:", len(r.stdout))

    def test_aead_gcm_enc(self):
        d = tempfile.mkdtemp()
        pt = os.path.join(d, "pt.bin")
        ct = os.path.join(d, "ct.bin")
        with open(pt, "wb") as f:
            f.write(b"hello world" * 10)
        key_hex = "00" * 32
        iv_hex = "00" * 12
        r = subprocess.run(
            ["openssl", "enc", "-aes-256-gcm", "-e", "-K", key_hex, "-iv", iv_hex,
             "-in", pt, "-out", ct],
            capture_output=True,
        )
        print("GCM enc rc:", r.returncode, "stderr:", r.stderr)


if __name__ == "__main__":
    unittest.main()
