"""Masked, in-order layout of one ULB/eDisha certificate. No arguments needed:

  python -m analyser.probe_seq

Prints and also saves to store/probe_seq.txt. Values are masked (letters a, digits 9).
"""
import contextlib
import io
from pathlib import Path

from . import probe

OUT = Path(__file__).resolve().parent.parent / "store" / "probe_seq.txt"


def main():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        probe.sequence("ulb")
    text = "probe_seq v1 (masked output only)\n" + buf.getvalue()
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(text)
    print(text)
    print("saved to", OUT)


if __name__ == "__main__":
    main()
