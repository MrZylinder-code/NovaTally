"""Tests für das eigene Fenster – mit einem nachgebauten pywebview (läuft überall, auch ohne Windows)."""

import sys
import time
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class FakeEvent:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self

    def fire(self, *args):
        return [h(*args) for h in self.handlers]


class FakeWindow:
    def __init__(self, title, url, **kw):
        self.title, self.url, self.kw = title, url, kw
        self.calls = []
        self.events = types.SimpleNamespace(closing=FakeEvent(), shown=FakeEvent())

    def show(self):
        self.calls.append("show")

    def restore(self):
        self.calls.append("restore")

    def hide(self):
        self.calls.append("hide")

    def destroy(self):
        self.calls.append("destroy")


def fake_webview():
    mod = types.ModuleType("webview")
    mod.settings = {}
    mod.windows = []
    mod.started = []

    def create_window(title, url, **kw):
        w = FakeWindow(title, url, **kw)
        mod.windows.append(w)
        return w

    def start(**kw):
        mod.started.append(kw)

    mod.create_window = create_window
    mod.start = start
    return mod


class WindowTest(unittest.TestCase):
    def setUp(self):
        self.mod = fake_webview()
        self._old = sys.modules.get("webview")
        sys.modules["webview"] = self.mod
        from novatally import window
        self.window = window

    def tearDown(self):
        if self._old is None:
            sys.modules.pop("webview", None)
        else:
            sys.modules["webview"] = self._old

    def make(self, **kw):
        return self.window.AppWindow("http://127.0.0.1:47815/", "/tmp/nt-webview", **kw)

    def test_fenster_wird_richtig_angelegt(self):
        self.assertTrue(self.window.available())
        w = self.make(hidden=True)
        fw = self.mod.windows[0]
        self.assertEqual(fw.title, "NovaTally")
        self.assertEqual(fw.url, "http://127.0.0.1:47815/")
        self.assertTrue(fw.kw["hidden"])
        self.assertEqual(fw.kw["min_size"], self.window.MIN_SIZE)
        self.assertTrue(self.mod.settings["ALLOW_DOWNLOADS"])  # CSV-Export
        self.assertTrue(self.mod.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"])
        w.run()
        self.assertEqual(self.mod.started, [{"gui": "edgechromium", "private_mode": False, "storage_path": "/tmp/nt-webview"}])

    def test_schliessen_versteckt_nur(self):
        hints = []
        w = self.make(on_first_hide=lambda: hints.append(1))
        fw = self.mod.windows[0]
        self.assertEqual(fw.events.closing.fire(), [False])  # Schließen abgebrochen …
        time.sleep(0.1)
        self.assertIn("hide", fw.calls)                       # … stattdessen versteckt
        self.assertFalse(w.visible)
        fw.events.closing.fire()
        self.assertEqual(hints, [1])                          # Hinweis nur beim ersten Mal

    def test_tray_oeffnen_zeigt_dasselbe_fenster(self):
        w = self.make(hidden=True)
        w.show()
        w.show()
        self.assertEqual(len(self.mod.windows), 1)            # nie ein zweites Fenster
        self.assertEqual(self.mod.windows[0].calls, ["show", "restore", "show", "restore"])
        self.assertTrue(w.visible)

    def test_beenden_schliesst_wirklich(self):
        w = self.make()
        fw = self.mod.windows[0]
        w.destroy()
        self.assertIn("destroy", fw.calls)
        self.assertEqual(fw.events.closing.fire(), [True])    # jetzt darf es schließen

    def test_ohne_pywebview(self):
        sys.modules["webview"] = None  # Import schlägt fehl
        self.assertFalse(self.window.available())


if __name__ == "__main__":
    unittest.main(verbosity=2)
