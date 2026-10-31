"""tools/philips-api.py finds the JointSpace API on 1926 before 1925, and says which package to check.

On a 77OLED806/12 (Android TV 11) port 1925 is open and answers nothing, while
https://<tv>:1926/6/system answers without pairing. The tool must report the API from 1926, count a 401
on the other endpoints as present (they wait for pairing), and exit 1 naming org.droidtv.xtv when
neither port answers. No TV and no network: the HTTP calls are replaced with a fake.

Run from the repository root: python3 -m unittest discover -s tests -v
"""
import contextlib
import importlib.util
import io
import json
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("philips_api", ROOT / "tools" / "philips-api.py")
philips_api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(philips_api)

SYSTEM = json.dumps({
    "name": "77OLED806/12",
    "api_version": {"Major": 6, "Minor": 1, "Patch": 0},
    "featuring": {"systemfeatures": {"pairing_type": "digest_auth_pairing"},
                  "jsonfeatures": {"ambilight": ["LoungeLight", "Hue", "Ambilight", "HueStreaming"]}},
})


def run(answers, argv=("philips-api.py", "192.168.1.50")):
    """Exit code and output, with get() answering from {url: (status, body)}; anything else is unreachable."""
    asked = []

    def fake_get(url, timeout=8):
        asked.append(url)
        return answers.get(url, (None, "timed out"))

    out = io.StringIO()
    with mock.patch.object(philips_api, "get", fake_get), contextlib.redirect_stdout(out), \
            contextlib.redirect_stderr(io.StringIO()):
        code = philips_api.main(list(argv))
    return code, out.getvalue(), asked


class PhilipsApi(unittest.TestCase):
    def test_the_api_on_1926_is_found_and_401_counts_as_there(self):
        base = "https://192.168.1.50:1926/6/"
        answers = {base + "system": (200, SYSTEM)}
        answers.update({base + p: (401, "") for p in philips_api.PROBE})
        code, out, asked = run(answers)
        self.assertEqual(code, 0)
        self.assertIn("API on https://192.168.1.50:1926", out)
        self.assertIn("6.1.0", out)
        self.assertIn("LoungeLight", out)
        self.assertNotIn("MISSING", out)
        self.assertFalse([u for u in asked if ":1925/" in u], "1925 was tried although 1926 answered")

    def test_an_empty_1925_is_not_taken_for_the_api(self):
        answers = {"http://192.168.1.50:1925/6/system": (200, "")}
        code, out, _ = run(answers)
        self.assertEqual(code, 1)
        self.assertIn("org.droidtv.xtv", out)

    def test_a_page_that_is_not_the_api_falls_back_to_1925(self):
        base = "http://192.168.1.50:1925/6/"
        answers = {"https://192.168.1.50:1926/6/system": (200, "<html>login</html>"),
                   base + "system": (200, SYSTEM)}
        answers.update({base + p: (401, "") for p in philips_api.PROBE})
        code, out, _ = run(answers)
        self.assertEqual(code, 0)
        self.assertIn("API on http://192.168.1.50:1925", out)
        self.assertIn("(not the API)", out)

    def test_json_that_is_not_a_system_object_is_no_api(self):
        for body in ("{}", "null", "[]", '{"api_version": "6"}', "{broken"):
            with self.subTest(body=body):
                code, out, _ = run({"https://192.168.1.50:1926/6/system": (200, body)})
                self.assertEqual(code, 1)
                self.assertIn("org.droidtv.xtv", out)

    def test_wrong_typed_feature_metadata_counts_as_unknown(self):
        system = json.dumps({"api_version": {"Major": 6, "Minor": 1, "Patch": 0},
                             "featuring": {"systemfeatures": [], "jsonfeatures": {"ambilight": 5}}})
        code, out, _ = run({"https://192.168.1.50:1926/6/system": (200, system)})
        self.assertEqual(code, 0)
        self.assertIn("6.1.0", out)
        self.assertNotIn("LoungeLight", out)

    def test_no_address_is_a_usage_error(self):
        with mock.patch.dict("os.environ", {"TV_HOST": ""}):
            code, _, asked = run({}, argv=("philips-api.py",))
        self.assertEqual(code, 2)
        self.assertEqual(asked, [])


if __name__ == "__main__":
    unittest.main()
