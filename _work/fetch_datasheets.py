#!/usr/bin/env python3
"""
Fetch the datasheets that analog.com will not serve to this machine.

analog.com times out (60 s, repeatedly) and the usual mirrors answer 403/410,
which for a long time left the AD9523, AD9253, AD9767 and ADCLK944 symbols and
power figures unverifiable. The Internet Archive holds copies of analog.com's
OWN URLs. With the `id_` suffix the Wayback Machine returns the archived bytes
unmodified - no toolbar, no rewriting - so the file is what analog.com served
on the snapshot date.

Two practical traps, both handled here:

  * Downloads on this machine are cut at exactly 1 MiB (1 048 576 bytes). A
    datasheet larger than that arrives truncated, with no error. So files are
    fetched in HTTP Range chunks of 1 000 000 bytes and reassembled.
  * A truncated PDF still starts with %PDF and still half-renders. The check
    that matters is the END: a complete file ends in %%EOF.

The AD9767 has no datasheet of its own: it is published jointly as
AD9763_9765_9767.pdf, and the Archive has no copy of an "AD9767.pdf" URL.

Output goes to _work/datasheets/, which is git-ignored - the PDFs are
Analog Devices' copyright and are not redistributed here. This script and the
hashes it prints are the record.

Usage:  py _work/fetch_datasheets.py [file.pdf ...]   (default: all)
"""

import hashlib
import http.cookiejar
import os
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "_work", "datasheets")
CHUNK = 1_000_000
UA = {"User-Agent": "Mozilla/5.0"}

# The Wayback Machine sometimes answers 302 to the very same URL while setting
# a cookie; without a cookie jar urllib sees an infinite redirect loop.
OPENER = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

WAYBACK = "https://web.archive.org/web/{ts}id_/{url}"
ADI = "https://www.analog.com/media/en/technical-documentation/data-sheets/"
XLNX = "https://www.xilinx.com/support/documentation/"

# local name, snapshot timestamp(s), original URL, revision as printed on the PDF.
# Several timestamps = alternates, tried in order. Some snapshots are stuck in a
# redirect loop on the Archive's side (ADCLK948.pdf of 2024 redirects to the
# adclk948.pdf capture, which redirects straight back); an older capture of
# the same URL is then used, and the output says which one.
SHEETS = [
    ("AD9523.pdf",   ("20240716170710", "20220119021345"), ADI + "AD9523.pdf", "Rev. D"),
    ("AD9253.pdf",   "20250701080623", ADI + "ad9253.pdf", "Rev. D"),
    ("AD9767.pdf",   "20160402045243",
     "http://www.analog.com/media/en/technical-documentation/data-sheets/AD9763_9765_9767.pdf",
     "Rev. G"),
    ("ADCLK944.pdf", "20250113092642", ADI + "ADCLK944.pdf", "Rev. 0"),
    # Clock sheet, 23 September: 2-input LVPECL fan-out and the programmable XO.
    ("ADCLK948.pdf", "20220119015656", ADI + "ADCLK948.pdf", "Rev. B"),
    ("Si549.pdf",    "20240712105249",
     "https://www.skyworksinc.com/-/media/SkyWorks/SL/documents/public/data-sheets/si549-datasheet.pdf",
     "Revision H"),
    # CONTROL sheet, 25 September: the XC7A50T's own documents. docs.amd.com
    # serves only a JavaScript portal to scripts, but the Archive holds the
    # old xilinx.com PDF URLs.
    ("UG483.pdf", "20220302131111", XLNX + "user_guides/ug483_7Series_PCB.pdf", "PCB design"),
    ("UG470.pdf", "20220315025443", XLNX + "user_guides/ug470_7Series_Config.pdf", "Config"),
    ("UG471.pdf", "20220315025334", XLNX + "user_guides/ug471_7Series_SelectIO.pdf", "SelectIO"),
    ("UG480.pdf", "20220324041335", XLNX + "user_guides/ug480_7Series_XADC.pdf", "XADC"),
    ("DS181.pdf", "20220315025345", XLNX + "data_sheets/ds181_Artix_7_Data_Sheet.pdf", "Artix-7 DC"),
    ("DS593.pdf", "20220303040011", XLNX + "data_sheets/ds593.pdf", "JTAG cable"),
    # Vivado's list of configuration flashes it can program (Appendix C).
    ("UG908.pdf", "20220302140110",
     XLNX + "sw_manuals/xilinx2020_2/ug908-vivado-programming-debugging.pdf", "2020.2"),
    ("MT25QL128.pdf", "20210507044858",
     "https://www.micron.com/-/media/client/global/documents/products/data-sheet/nor-flash/"
     "serial-nor/mt25q/die-rev-a/mt25q_qlhs_l_128_aba_0.pdf", "Rev. ?"),
    # Layout (25 Sep): the package guide (DXP/DXN, pin types) and Xilinx's own
    # machine-readable ball list for the exact device, to check the symbol by.
    ("UG475.pdf", ("20221223103143", "20220315023512"),
     "https://www.xilinx.com/content/dam/xilinx/support/documents/user_guides/"
     "ug475_7Series_Pkg_Pinout.pdf", "Pkg pinout"),
    ("xc7a50tftg256pkg.txt", ("20230208072858", "20221223103953"),
     "https://www.xilinx.com/content/dam/xilinx/support/packagefiles/a7packages/"
     "xc7a50tftg256pkg.txt", "pkg file"),
    # Housekeeping (2 Oct): st.com does not answer scripts; the Archive does.
    ("M24C02.pdf", ("20241116070424", "20240430160457"),
     "https://www.st.com/resource/en/datasheet/m24c02-r.pdf", "DS9398 Rev 8"),
]


# ti.com serves its PDFs to this machine directly (checked 25 Sep 2026), so
# TI parts need no archive: (file, URL).
DIRECT = [
    ("LMR33630.pdf", "https://www.ti.com/lit/ds/symlink/lmr33630.pdf"),
    ("SN74LVC1G07.pdf", "https://www.ti.com/lit/ds/symlink/sn74lvc1g07.pdf"),
    # the LDOs' exposed pad, checked at layout (26 Sep)
    ("TPS7A8300.pdf", "https://www.ti.com/lit/ds/symlink/tps7a8300.pdf"),
    # housekeeping devices (2 Oct). The AT24CS02 was considered and rejected:
    # its output low is specified for 0.15 mA at 1.7 V (CONTROL_SPEC §2).
    ("TMP1075.pdf", "https://www.ti.com/lit/ds/symlink/tmp1075.pdf"),
    ("AT24CS02.pdf", "https://ww1.microchip.com/downloads/aemDocuments/documents/MPD/"
                     "ProductDocuments/DataSheets/20006330A.pdf"),
    # Layout (25 Sep): Mini-Circuits serves directly too - the balun and the
    # land patterns (PL-xxx) its datasheets point to.
    ("ADT2-1T.pdf", "https://www.minicircuits.com/pdfs/ADT2-1T+.pdf"),
    ("PL-052.pdf", "https://www.minicircuits.com/pcb/98-pl052.pdf"),
    ("PL-768.pdf", "https://www.minicircuits.com/pcb/98-pl768.pdf"),
    ("DQ3005.pdf", "https://www.minicircuits.com/case_style/DQ3005.pdf"),   # M3SWA2 package
    ("CD542.pdf", "https://www.minicircuits.com/case_style/CD542.pdf"),     # ADT2-1T package
    # the power inductors and the reverse-polarity MOSFET, chosen at layout
    ("SRP7028A.pdf", "https://www.bourns.com/docs/Product-Datasheets/SRP7028A.pdf"),
    ("DMP3013SFV.pdf", "https://www.diodes.com/assets/Datasheets/DMP3013SFV.pdf"),
]


def fetch_direct(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=120).read()


def fetch(url):
    """Download `url` in Range chunks; return the bytes."""
    data = b""
    while True:
        req = urllib.request.Request(url, headers=dict(
            UA, Range=f"bytes={len(data)}-{len(data) + CHUNK - 1}"))
        # The Archive answers 503 when busy, and sometimes a 302 loop between
        # snapshots; both are transient, so retry.
        for attempt in range(5):
            try:
                with OPENER.open(req, timeout=120) as r:
                    part = r.read()
                    status = r.status
                break
            except urllib.error.HTTPError as e:
                if e.code == 416:      # asked past the end: we are done
                    return data
                if e.code not in (302, 429, 502, 503, 504) or attempt == 4:
                    raise
            except (urllib.error.URLError, TimeoutError):
                if attempt == 4:
                    raise
            time.sleep(10 * (attempt + 1))
        data += part
        # 200 means the server ignored Range and sent everything it would;
        # a short 206 means that was the last chunk.
        if status == 200 or len(part) < CHUNK:
            break
    return data


def main():
    os.makedirs(OUT, exist_ok=True)
    bad = 0
    only = set(sys.argv[1:])
    for name, stamps, url, rev in SHEETS:
        if only and name not in only:
            continue
        path = os.path.join(OUT, name)
        if isinstance(stamps, str):
            stamps = (stamps,)
        blob, err = None, None
        for ts in stamps:
            src = WAYBACK.format(ts=ts, url=url)
            try:
                blob = fetch(src)
                break
            except Exception as e:                  # noqa: BLE001
                err = e
            # Some captures answer a Range request with a 302 to another
            # capture, which answers with a 302 back (M24C02.pdf, 2 Oct 2026),
            # yet serve the whole file to a plain GET. The completeness check
            # below still applies.
            try:
                blob = fetch_direct(src)
                break
            except Exception as e:                  # noqa: BLE001
                err = e
        if blob is None:
            print(f"  FAIL {name:14s} {err}")
            bad += 1
            continue
        if name.endswith(".pdf"):
            complete = blob.startswith(b"%PDF") and b"%%EOF" in blob[-1024:]
        else:                                       # Xilinx package file
            complete = b"Total Number of Pins" in blob[-512:]
        with open(path, "wb") as fh:
            fh.write(blob)
        tag = "ok  " if complete else "TRUNCATED"
        print(f"  {tag} {name:14s} {len(blob):>9,} B  {rev:7s} "
              f"sha256 {hashlib.sha256(blob).hexdigest()[:16]}")
        print(f"       {src}")
        bad += 0 if complete else 1
    for name, url in DIRECT:
        if only and name not in only:
            continue
        try:
            blob = fetch_direct(url)
        except Exception as e:                      # noqa: BLE001
            print(f"  FAIL {name:14s} {e}")
            bad += 1
            continue
        complete = blob.startswith(b"%PDF") and b"%%EOF" in blob[-1024:]
        with open(os.path.join(OUT, name), "wb") as fh:
            fh.write(blob)
        print(f"  {'ok  ' if complete else 'TRUNCATED'} {name:14s} {len(blob):>9,} B  direct   "
              f"sha256 {hashlib.sha256(blob).hexdigest()[:16]}")
        print(f"       {url}")
        bad += 0 if complete else 1
    print()
    print("All complete." if not bad else f"{bad} file(s) missing or truncated.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
