#!/usr/bin/env python3
"""Check that a Philips TV's JointSpace control API still answers, before and after a debloat.

    philips-api.py [tv ip]      the IP defaults to TV_HOST

Exits 0 when the API answers, 1 when neither port does, and 2 on a usage error.

Philips Android TVs are driven from Home Assistant (the built-in philips_js integration), openHAB and
the like over the JointSpace API. It is served by org.droidtv.xtv, which is in the DO NOT DISABLE block
of examples/philips-50pus8517; a TV that loses it drops out of Home Assistant, and nothing on the TV's
screen says why. Run this once before the first batch and again after the last.

Two things trip people up, and this handles both:

  * On Android TV sets the API is on port 1926 over HTTPS, not the 1925 that older guides name. 1925 may
    be open and answer nothing (a 77OLED806/12 on Android TV 11 does).
  * The certificate is self-signed, so it is not verified here, as Home Assistant does not verify it
    either. This only reads from a TV on your own network.

/6/system answers without pairing, so this needs no credentials and changes nothing on the TV. The other
endpoints answer 401 until a client has done the digest-auth pairing, and for this check a 401 is the good
answer: the endpoint is there.
"""
import json
import os
import ssl
import sys
import urllib.error
import urllib.request

PORTS = ((1926, "https"), (1925, "http"))
PROBE = ("ambilight/topology", "ambilight/power", "ambilight/mode", "ambilight/currentconfiguration",
         "powerstate")


def get(url, timeout=8):
    """(status, body); status is None when nothing answered, and body then says why."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with urllib.request.urlopen(url, timeout=timeout, context=ctx) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as failure:
        return None, str(failure)


def system_info(body):
    """The decoded /6/system object, or None when the body is not one (an HTML page, broken JSON, {})."""
    try:
        info = json.loads(body)
    except ValueError:
        return None
    if isinstance(info, dict) and isinstance(info.get("api_version"), dict):
        return info
    return None


def section(parent, key):
    """parent[key] when it is an object, else {}: optional metadata of the wrong type counts as unknown."""
    value = parent.get(key)
    return value if isinstance(value, dict) else {}


def find_api(host):
    """The base URL and decoded /6/system of the first port that answers as the API, or (None, None).
    Prints each port it tried."""
    for port, scheme in PORTS:
        base = f"{scheme}://{host}:{port}"
        status, body = get(f"{base}/6/system")
        info = system_info(body) if status == 200 else None
        if info is not None:
            return base, info
        why = status if status is not None else body
        print(f"  {base}/6/system -> {why}{' (not the API)' if status == 200 else ''}")
    return None, None


def main(argv):
    args = argv[1:]
    host = args[0] if args else os.environ.get("TV_HOST", "")
    if len(args) > 1 or not host or host.startswith("-"):
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 2

    base, info = find_api(host)
    if not base:
        print("\nNo JointSpace API. If this TV used to work with Home Assistant, check that\n"
              "org.droidtv.xtv is still enabled:\n"
              f"  TV_HOST={host} tools/tv.py 'pm list packages -d' | grep droidtv")
        return 1

    print(f"API on {base}")
    api = info["api_version"]
    feat = section(info, "featuring")
    ambilight = section(feat, "jsonfeatures").get("ambilight")
    print(f"  name           {info.get('name')}")
    print(f"  api_version    {api.get('Major')}.{api.get('Minor')}.{api.get('Patch')}")
    print(f"  pairing        {section(feat, 'systemfeatures').get('pairing_type')}")
    print(f"  ambilight      {ambilight}")
    if isinstance(ambilight, list) and "LoungeLight" in ambilight:
        print("                 (LoungeLight is Ambilight with the panel off. For it to answer while\n"
              "                  the TV is off, turn on Eco settings > Quick start.)")

    print("\nendpoints (401 = there, waiting for pairing):")
    for path in PROBE:
        status, _ = get(f"{base}/6/{path}")
        verdict = {200: "open", 401: "there", 404: "MISSING"}.get(status, str(status))
        print(f"  {path:32s} {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
