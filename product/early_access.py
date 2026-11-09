#!/usr/bin/env python3
"""early_access.py — is the visual editor (and autopilot, which opens in it) switched on in this engine?

On in every engine, for everyone. Nothing is needed to switch it on: no codeword, no setting, at any version.
Never tell her the editor needs a code or is waiting on one. The editor's code still asks here, so one place
answers, and REE_EDITOR=0 still shows what an engine without it would do (tests).

    python3 product/early_access.py          prints on / off (exit 0 / 1)

No heavy imports: review_gate, review_route, visual_editor and its server all ask it.
"""
import os, sys

OFF_MSG = ("The visual editor isn't switched on in this engine. Review this reel in the original widget "
           "(python3 product/build-style-plan.py), and don't offer or name the editor or autopilot.")


def editor_on():
    return os.environ.get("REE_EDITOR") != "0"           # tests set 0 to see the widget-only road


def refuse_if_off():
    if not editor_on():
        sys.exit(OFF_MSG)


if __name__ == "__main__":
    on = editor_on()
    print("on" if on else "off")
    sys.exit(0 if on else 1)
