#!/usr/bin/env python3
"""Replace the legacy handling-envelope wording in the supplied vector PDF.

The original Visio source is unavailable.  This script keeps every vector
object and font resource intact, changes only five text-showing instructions,
and preserves each content-stream byte length before pdftk rebuilds the PDF.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "image" / "model_shuoming.pdf"
OUTPUT = ROOT / "CEP" / "model_shuoming.pdf"

REPLACEMENTS = {
    b"[(GGV)-14( )9(h)-5(an)-7(d)6(l)-10(in)7(g)-5(:)] TJ":
        b"[(Tire-force limit:)] TJ",
    b"[(s)3(u)-5(p)-5(er)] TJ": b"[(speed-dependent)] TJ",
    b"1 0 0 1 173.47 80.808 Tm\r\n0 g\r\n0 G\r\n[(-)] TJ":
        b"1 0 0 1 173.47 80.808 Tm\r\n0 g\r\n0 G\r\n[] TJ",
    b"[(ellip)-4(tic )-2(f)-3(r)-3(ictio)-4(n)] TJ": b"[] TJ",
    b"[(en)-7(v)6(elo)-6(p)-5(e )-4(\()8(E)-2(q)-5( )-2(1)6(8)-5(\))] TJ":
        b"[(envelope \(Eq. 20\))] TJ",
    b"[(Fric)-2(ti)-9(o)6(n)-5( )-2(lim)-2(it a)-2(t sp)-4(ee)-3(d)-5( )-2(V,)] TJ":
        b"[(Force limits at speed V,)] TJ",
}


def equal_length(old: bytes, new: bytes) -> bytes:
    if len(new) > len(old):
        raise ValueError(f"replacement is {len(new) - len(old)} bytes too long")
    return new + b" " * (len(old) - len(new))


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="model-pdf-relabel-") as tmp:
        unpacked = Path(tmp) / "unpacked.pdf"
        edited = Path(tmp) / "edited.pdf"
        subprocess.run(
            ["pdftk", str(SOURCE), "output", str(unpacked), "uncompress"],
            check=True,
        )
        payload = unpacked.read_bytes()
        for old, new in REPLACEMENTS.items():
            count = payload.count(old)
            if count != 1:
                raise RuntimeError(f"expected one match, found {count}: {old!r}")
            payload = payload.replace(old, equal_length(old, new), 1)
        edited.write_bytes(payload)
        subprocess.run(
            ["pdftk", str(edited), "output", str(OUTPUT), "compress"],
            check=True,
        )


if __name__ == "__main__":
    main()
