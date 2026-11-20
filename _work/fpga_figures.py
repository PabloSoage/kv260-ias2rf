#!/usr/bin/env python3
"""
The one source for the FPGA utilisation and timing figures: reads the Vivado reports of the two builds of record
and writes the same table into every document that shows it, between the markers

    <!-- fpga-figures:begin -->  ...  <!-- fpga-figures:end -->

  artix_top              fpga/artix/build_rev06.tcl -> fpga/artix/reports_rev06/
  ias2rf_k26_bd_wrapper  fpga/kria/bd.tcl           -> fpga/kria/reports/

Other mentions link to docs/FPGA_GATEWARE.md#fpga-figures instead of repeating the numbers.

Usage:  python _work/fpga_figures.py          (rewrite the tables)
        python _work/fpga_figures.py --check  (exit 1 if a table is stale)
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILDS = [
    ("artix_top", "XC7A50T-FTG256-2", "fpga/artix/reports_rev06", "fpga/artix/build_rev06.tcl",
     {"lut": 32600, "ff": 65200, "bram": 75, "dsp": 120, "uram": 0}),
    ("ias2rf_k26_bd_wrapper", "XCK26-SFVC784-2LV-c", "fpga/kria/reports", "fpga/kria/bd.tcl",
     {"lut": 117120, "ff": 234240, "bram": 144, "dsp": 1248, "uram": 64}),
]
TARGETS = ["README.md", "docs/FPGA_GATEWARE.md", "fpga/README.md"]
BEGIN, END = "<!-- fpga-figures:begin -->", "<!-- fpga-figures:end -->"
HIER_DOC = "docs/FPGA_GATEWARE.md"
HBEGIN, HEND = "<!-- fpga-artix-hier:begin -->", "<!-- fpga-artix-hier:end -->"
# artix_top's first-level instances, grouped as FPGA_GATEWARE 2.4 describes them
ARTIX_GROUPS = [
    (["u_sdr_ddc"], "Dual-channel wideband SDR DDC (62.5 / 50.0 MSPS)"),
    (["u_ddc"], "400 -> 100 -> 25 MSPS AERIS-10 radar DDC, tunable NCO (G-4), anti-alias half-bands and CPI mark (G-8)"),
    (["u_d2", "u_d2_peak"], "Rev08 G-7 D2: the 500 MSPS AD9484 path (four-lane NCO, mixer, pruned CIC5, `ddc_hb4`) and its "
                            "AGC peak detector"),
    (["u_dbg_uart"], "G-1 8N1 debug UART monitor, banner, 1 Hz `STAT` and the fourth CSR master"),
    (["u_ul_pcs_tx"], "2-lane `64b/66b` IAS1 uplink PCS"),
    (["u_fe_agc", "u_adcr_peak"], "Rev08 G-2 to G-6: front-end AGC and its AD9484 peak detector (the expander and "
                                  "RFFC5072/PE4312 sequencer logic is flattened into the top level)"),
    (["gen_rev06_eth.*"], "`1000BASE-T` SGMII + UDP MAC + dual-path failover"),
    (["u_dl_pcs_rx", "u_dl_train_fsm"], "1-lane 1.0 Gb/s IAS1 downlink + eye trainer"),
    (["u_xadc_pps", "u_hk_i2c", "u_clk_mode_ctrl", "u_pmod_spi"], "Safe-boot MMCM DRP / Si549, XADC, 1-PPS, I2C, Pmod SPI"),
    (["u_adc_cap", "u_adcs_cap", "u_conv_spi"], "High-speed LVDS ADC capture and 3-wire converter init"),
    (["u_dac_radar", "u_dac_sdr", "u_adar_ctrl", "u_rf_switch"], "Non-MMCM DACs, `8x ADAR1000` beamformer, RF switches"),
]


def read_build(top, rpt_dir):
    util = open(os.path.join(ROOT, rpt_dir, "utilization.rpt"), encoding="utf-8", errors="replace").read()
    hdr = re.search(r"^\|\s+Instance\s+\|.*$", util, re.M).group(0)
    cols = [c.strip() for c in hdr.strip("|").split("|")]
    row = re.search(rf"^\|\s+{re.escape(top)}\s+\|.*$", util, re.M).group(0)
    vals = dict(zip(cols, [c.strip() for c in row.strip("|").split("|")]))
    date = re.search(r"\| Date\s+:\s+(.+)$", util, re.M).group(1).strip()
    tim = open(os.path.join(ROOT, rpt_dir, "timing_summary.rpt"), encoding="utf-8", errors="replace").read()
    m = re.search(r"WNS\(ns\)\s+TNS\(ns\).*?\n\s*-+.*?\n\s*([-\d.]+)\s+([-\d.]+)\s+(\d+)\s+(\d+)\s+([-\d.]+)", tim, re.S)
    return {
        "lut": int(vals["Total LUTs"]), "ff": int(vals["FFs"]),
        "bram": int(vals["RAMB36"]) + int(vals["RAMB18"]) / 2, "uram": int(vals.get("URAM", 0) or 0),
        "dsp": int(vals["DSP Blocks"]), "wns": float(m.group(1)), "fail": int(m.group(3)),
        "endpoints": int(m.group(4)), "whs": float(m.group(5)), "date": date,
    }


def figures():
    return [(top, dev, rpt, script, cap, read_build(top, rpt)) for top, dev, rpt, script, cap in BUILDS]


def pct(n, d):
    return f"{100.0 * n / d:.1f} %"


def table(rel_from):
    """The markdown table, with report links relative to the document at rel_from."""
    base = os.path.dirname(rel_from)
    lines = ["| Design (Vivado 2026.1) | Device | LUTs | FFs | BRAM36 eq. | DSPs | WNS / WHS | Failing endpoints | Reports |",
             "|---|---|---|---|---|---|---|---|---|"]
    for top, dev, rpt, script, cap, f in figures():
        bram = f"{f['bram']:.1f} ({pct(f['bram'], cap['bram'])})"
        if f["uram"]:
            bram += f", {f['uram']} URAM"
        link = os.path.relpath(os.path.join(ROOT, rpt), os.path.join(ROOT, base)).replace(os.sep, "/")
        slink = os.path.relpath(os.path.join(ROOT, script), os.path.join(ROOT, base)).replace(os.sep, "/")
        lines.append(
            f"| `{top}` | {dev} | {f['lut']:,} ({pct(f['lut'], cap['lut'])}) | {f['ff']:,} ({pct(f['ff'], cap['ff'])}) | "
            f"{bram} | {f['dsp']:,} ({pct(f['dsp'], cap['dsp'])}) | +{f['wns']:.3f} / +{f['whs']:.3f} ns | "
            f"{f['fail']} of {f['endpoints']:,} | [`{rpt.split('fpga/')[1]}/`]({link}/) from [`{os.path.basename(script)}`]({slink}) |")
    dates = "; ".join(f"{t}: {f['date']}" for t, _, _, _, _, f in figures())
    lines.append("")
    lines.append(f"*Post-route, generated from the Vivado reports by `_work/fpga_figures.py` ({dates}).*")
    return "\n".join(lines)


def artix_hier(rel_from):
    util = open(os.path.join(ROOT, "fpga/artix/reports_rev06/utilization.rpt"), encoding="utf-8",
                errors="replace").read()
    hdr = re.search(r"^\|\s+Instance\s+\|.*$", util, re.M).group(0)
    cols = [c.strip() for c in hdr.strip("|").split("|")]
    inst = {}
    for line in re.findall(r"^\|   [A-Za-z].*$", util, re.M):            # depth 1 under artix_top
        v = dict(zip(cols, [c.strip() for c in line.strip("|").split("|")]))
        inst[v["Instance"]] = v
    top, _, _, _, cap, f = figures()[0]
    keys = ("Total LUTs", "FFs", "RAMB36", "RAMB18", "DSP Blocks")
    vt = dict(zip(cols, [c.strip() for c in
                         re.search(rf"^\|\s+{top}\s+\|.*$", util, re.M).group(0).strip("|").split("|")]))
    lines = ["| Hierarchy | Total LUTs | FFs | RAMB36 | RAMB18 | DSP48E1 | Role |",
             "| :--- | :---: | :---: | :---: | :---: | :---: | :--- |",
             f"| **`artix_top` (total)** | **{int(vt['Total LUTs']):,} ({pct(f['lut'], cap['lut'])})** | "
             f"**{int(vt['FFs']):,} ({pct(f['ff'], cap['ff'])})** | **{vt['RAMB36']}** | **{vt['RAMB18']}** | "
             f"**{vt['DSP Blocks']} ({pct(f['dsp'], cap['dsp'])})** | Everything below plus the top level's own logic |"]
    used = set()
    for names, role in ARTIX_GROUPS:
        sel = [k for k in inst if any(k == n or (n.endswith(".*") and k.startswith(n[:-1])) for n in names)]
        used.update(sel)
        sums = {k: sum(int(inst[i][k]) for i in sel) for k in keys}
        label = " + ".join(f"`{n}`" for n in names)
        lines.append(f"| {label} | {sums['Total LUTs']:,} | {sums['FFs']:,} | {sums['RAMB36']} | {sums['RAMB18']} | "
                     f"{sums['DSP Blocks']} | {role} |")
    left = sorted(set(inst) - used)
    if left:
        raise SystemExit(f"artix_top instances not in a group: {left}")
    return "\n".join(lines)


def replace_block(text, begin, end, body):
    return re.sub(re.escape(begin) + r".*?" + re.escape(end), lambda _: begin + "\n" + body + "\n" + end, text,
                  flags=re.S)


def main():
    check = "--check" in sys.argv
    stale = []
    for rel in TARGETS:
        path = os.path.join(ROOT, rel)
        text = open(path, encoding="utf-8").read()
        if BEGIN not in text:
            raise SystemExit(f"{rel}: no {BEGIN} marker")
        new = replace_block(text, BEGIN, END, table(rel))
        if rel == HIER_DOC:
            if HBEGIN not in text:
                raise SystemExit(f"{rel}: no {HBEGIN} marker")
            new = replace_block(new, HBEGIN, HEND, artix_hier(rel))
        if new != text:
            stale.append(rel)
            if not check:
                open(path, "w", encoding="utf-8", newline="\n").write(new)
    print(("stale: " if check else "updated: ") + (", ".join(stale) or "none"))
    sys.exit(1 if check and stale else 0)


if __name__ == "__main__":
    main()
