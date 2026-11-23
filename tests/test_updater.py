"""Tests für Updates (nur Standardbibliothek, ohne Netzwerk)."""

import hashlib
import json
import os
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from novatally import updater  # noqa: E402
from novatally.updater import UpdateError  # noqa: E402

EXE = b"MZ-neue-version" * 100
PREFIX = updater.DOWNLOAD_PREFIX + "v9.9.9/"


SETUP = b"Inno-Setup" * 100


def fake_release(tag="v9.9.9", exe_url=PREFIX + "NovaTally.exe", sha=None, body=None):
    sha = sha if sha is not None else hashlib.sha256(EXE).hexdigest() + "  NovaTally.exe\n"
    files = {
        updater.LATEST_API: json.dumps({
            "tag_name": tag,
            "html_url": "https://github.com/MrZylinder-code/NovaTally/releases/tag/" + tag,
            "body": body or "- Neue Funktion\n- Fehler behoben\n\n### Installation\n1. Herunterladen …",
            "assets": [
                {"name": "NovaTally.exe", "browser_download_url": exe_url},
                {"name": "NovaTally.exe.sha256", "browser_download_url": PREFIX + "NovaTally.exe.sha256"},
                {"name": "NovaTally-Setup.exe", "browser_download_url": PREFIX + "NovaTally-Setup.exe"},
                {"name": "NovaTally-Setup.exe.sha256", "browser_download_url": PREFIX + "NovaTally-Setup.exe.sha256"},
            ],
        }).encode(),
        exe_url: EXE,
        PREFIX + "NovaTally.exe.sha256": sha.encode(),
        PREFIX + "NovaTally-Setup.exe": SETUP,
        PREFIX + "NovaTally-Setup.exe.sha256": (hashlib.sha256(SETUP).hexdigest() + "  NovaTally-Setup.exe").encode(),
    }

    def fetch(url, timeout=15):
        if url not in files:
            raise OSError("kein Netz: " + url)
        return files[url]
    return fetch


class VersionTest(unittest.TestCase):
    def test_versionen_vergleichen(self):
        self.assertEqual(updater.parse_version("v1.2.3"), (1, 2, 3))
        self.assertTrue(updater.is_newer("v1.0.10", "1.0.9"))
        self.assertTrue(updater.is_newer("1.1", "1.0.5"))
        self.assertFalse(updater.is_newer("v1.0.1", "1.0.1"))
        self.assertFalse(updater.is_newer("1.0", "1.0.0"))
        self.assertFalse(updater.is_newer("quatsch", "1.0.0"))

    def test_release_text_ohne_installationsteil(self):
        self.assertEqual(updater.release_notes("- A\r\n- B\r\n\r\n### Installation\r\n1. x"), "- A\n- B")


class ReleaseTest(unittest.TestCase):
    def test_neue_version_gefunden(self):
        info = updater.check_release("1.0.1", fetch=fake_release())
        self.assertTrue(info["newer"])
        self.assertEqual(info["latest"], "9.9.9")
        self.assertEqual(info["notes"], "- Neue Funktion\n- Fehler behoben")
        self.assertTrue(info["installable"])

    def test_keine_neue_version(self):
        info = updater.check_release("9.9.9", fetch=fake_release())
        self.assertFalse(info["newer"])

    def test_fremde_download_adresse_wird_abgelehnt(self):
        with self.assertRaises(UpdateError):
            updater.check_release("1.0.0", fetch=fake_release(exe_url="https://boese.example/NovaTally.exe"))

    def test_kein_netz(self):
        def offline(url, timeout=15):
            raise urllib.error.URLError(socket.gaierror(11001, "getaddrinfo failed"))
        with self.assertRaises(UpdateError) as cm:
            updater.check_release("1.0.0", fetch=offline, resolve=offline)
        self.assertIn("Internetverbindung", str(cm.exception))

    def test_ausweichweg_ohne_api(self):
        def api_gesperrt(url, timeout=15):
            raise urllib.error.HTTPError(url, 403, "rate limit", {}, None)

        def resolve(url, timeout=15):
            self.assertEqual(url, updater.RELEASES_URL + "/latest")
            return updater.RELEASES_URL + "/tag/v9.9.9"
        info = updater.check_release("1.0.0", fetch=api_gesperrt, resolve=resolve)
        self.assertTrue(info["newer"])
        self.assertEqual(info["exe_url"], updater.DOWNLOAD_PREFIX + "v9.9.9/NovaTally.exe")
        self.assertTrue(info["installable"])

    def test_verstaendliche_fehlergruende(self):
        d = updater.describe
        self.assertIn("begrenzt", d(urllib.error.HTTPError("u", 403, "x", {}, None)))
        self.assertIn("HTTP 500", d(urllib.error.HTTPError("u", 500, "x", {}, None)))
        self.assertIn("Sicherheitszertifikat", d(urllib.error.URLError(
            ssl.SSLCertVerificationError(1, "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed"))))
        self.assertIn("Zeitüberschreitung", d(urllib.error.URLError(socket.timeout("timed out"))))
        self.assertIn("nicht gefunden", d(urllib.error.URLError(socket.gaierror(11001, "getaddrinfo failed"))))
        self.assertIn("abgelehnt", d(urllib.error.URLError(ConnectionRefusedError(10061, "refused"))))

    def test_zertifikate_werden_geladen(self):
        ctx = updater.ssl_context()
        self.assertTrue(ctx.check_hostname)
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)
        self.assertGreater(len(ctx.get_ca_certs()) + ctx.cert_store_stats()["x509_ca"], 0)

    def test_download_mit_richtiger_pruefsumme(self):
        fetch = fake_release()
        info = updater.check_release("1.0.0", fetch=fetch)
        with tempfile.TemporaryDirectory() as tmp:
            path = updater.download_verified(info, tmp, fetch=fetch)
            self.assertEqual(path.read_bytes(), EXE)

    def test_falsche_pruefsumme_wird_nicht_installiert(self):
        fetch = fake_release(sha="0" * 64 + "  NovaTally.exe")
        info = updater.check_release("1.0.0", fetch=fetch)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(UpdateError) as cm:
                updater.download_verified(info, tmp, fetch=fetch)
            self.assertIn("Prüfsumme", str(cm.exception))
            self.assertEqual(os.listdir(tmp), [])

    def test_installer_herunterladen(self):
        fetch = fake_release()
        info = updater.check_release("1.0.0", fetch=fetch)
        self.assertEqual(info["setup_url"], PREFIX + "NovaTally-Setup.exe")
        with tempfile.TemporaryDirectory() as tmp:
            path = updater.download_verified(info, tmp, fetch=fetch, kind="setup")
            self.assertEqual(path.name, "NovaTally-Setup.exe")
            self.assertEqual(path.read_bytes(), SETUP)

    def test_modus_je_installation(self):
        m = updater.select_mode
        self.assertEqual(m(True, True, True, False), "exe")       # EXE in beschreibbarem Ordner
        self.assertEqual(m(True, True, False, False), "setup")    # z. B. C:\\Program Files
        self.assertEqual(m(True, False, True, False), "manual")   # gebaut, aber kein Windows
        self.assertEqual(m(False, True, True, True), "git")       # Quellcode mit Git
        self.assertEqual(m(False, True, True, False), "manual")
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(updater.is_writable(tmp))
        self.assertFalse(updater.is_writable(os.path.join(tempfile.gettempdir(), "gibt-es-nicht-xyz")))

    def test_alte_update_reste_wegraeumen(self):
        with tempfile.TemporaryDirectory() as tmp:
            alt, neu, fremd = Path(tmp, "novatally-update-alt"), Path(tmp, "novatally-update-neu"), Path(tmp, "anderes")
            for d in (alt, neu, fremd):
                d.mkdir()
                (d / "NovaTally-Setup.exe").write_bytes(b"x")
            old_time = time.time() - 3 * 86400
            os.utime(alt, (old_time, old_time))
            self.assertEqual(updater.cleanup_temp(temp_dir=tmp), 1)
            self.assertFalse(alt.exists())
            self.assertTrue(neu.exists())    # frisch – könnte gerade laufen
            self.assertTrue(fremd.exists())  # nicht von NovaTally

    def test_exe_austauschen_und_aufraeumen(self):
        with tempfile.TemporaryDirectory() as tmp:
            cur, new = Path(tmp, "NovaTally.exe"), Path(tmp, "NovaTally.new.exe")
            cur.write_bytes(b"alt")
            new.write_bytes(b"neu")
            old = updater.swap_exe(cur, new)
            self.assertEqual(cur.read_bytes(), b"neu")
            self.assertEqual(old.read_bytes(), b"alt")
            self.assertFalse(new.exists())
            updater.cleanup_old(cur)
            self.assertEqual(sorted(os.listdir(tmp)), ["NovaTally.exe"])


@unittest.skipUnless(sys.platform == "win32", "nur unter Windows")
class WindowsSwapTest(unittest.TestCase):
    def test_laufende_exe_laesst_sich_austauschen(self):
        """Grundlage des Updates: Windows erlaubt das Umbenennen einer laufenden EXE."""
        with tempfile.TemporaryDirectory() as tmp:
            cur = Path(tmp, "NovaTally.exe")
            shutil.copy(os.path.join(os.environ["SystemRoot"], "System32", "ping.exe"), cur)
            proc = subprocess.Popen([str(cur), "-n", "8", "127.0.0.1"], stdout=subprocess.DEVNULL)
            try:
                new = Path(tmp, "NovaTally.new.exe")
                new.write_bytes(b"neu")
                updater.swap_exe(cur, new)  # während die alte Datei noch läuft
                self.assertEqual(cur.read_bytes(), b"neu")
                self.assertTrue(Path(tmp, "NovaTally.old.exe").exists())
                updater.cleanup_old(cur)  # läuft noch -> darf nicht abstürzen
            finally:
                proc.kill()
                proc.wait()
            updater.cleanup_old(cur)  # jetzt beendet -> wird gelöscht
            self.assertFalse(Path(tmp, "NovaTally.old.exe").exists())


@unittest.skipUnless(shutil.which("git"), "git nicht installiert")
class GitTest(unittest.TestCase):
    def git(self, *args, cwd):
        subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                        "-c", "init.defaultBranch=main", *args], cwd=cwd, check=True, capture_output=True)

    def test_git_pruefen_und_holen(self):
        with tempfile.TemporaryDirectory() as tmp:
            origin, a, b = Path(tmp, "origin.git"), Path(tmp, "a"), Path(tmp, "b")
            self.git("init", "--bare", str(origin), cwd=tmp)
            self.git("clone", str(origin), str(a), cwd=tmp)
            Path(a, "datei.txt").write_text("1")
            self.git("add", ".", cwd=a)
            self.git("commit", "-m", "Erster Stand", cwd=a)
            self.git("push", "origin", "HEAD", cwd=a)
            self.git("clone", str(origin), str(b), cwd=tmp)
            self.assertFalse(updater.check_git("1.0.0", cwd=b)["newer"])
            Path(a, "datei.txt").write_text("2")
            self.git("commit", "-am", "Neue Funktion", cwd=a)
            self.git("push", "origin", "HEAD", cwd=a)
            info = updater.check_git("1.0.0", cwd=b)
            self.assertTrue(info["newer"])
            self.assertEqual(info["notes"], "- Neue Funktion")
            self.assertEqual(info["latest"], "1 neue Änderung")
            updater.pull_git(cwd=b)
            self.assertEqual(Path(b, "datei.txt").read_text(), "2")
            self.assertFalse(updater.check_git("1.0.0", cwd=b)["newer"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
