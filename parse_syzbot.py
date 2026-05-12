#!/usr/bin/env python3
"""
parse_syzbot.py - Extract structured data from a syzbot bug page.

Usage:
  curl -sL "https://syzkaller.appspot.com/bug?extid=XXXX" | python3 parse_syzbot.py
  python3 parse_syzbot.py bug_page.html
  python3 parse_syzbot.py https://syzkaller.appspot.com/bug?extid=XXXX

Outputs key=value lines for easy parsing by LLM.
"""

import html.parser
import json
import re
import sys
from urllib.request import urlopen


class SyzbotParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.in_title = False
        self.instances = []

        # Table tracking
        self.in_crashes_table = False  # only process table with "Crashes" caption
        self.in_tbody = False
        self.in_tr = False
        self.in_td = False
        self.col_idx = 0
        self.current_row = None

        # TD tracking
        self.td_class = ""
        self.td_attrs = {}
        self.td_hrefs = []     # all hrefs found in this td
        self.td_link_labels = []  # link text labels for this td
        self.td_raw_text = ""   # raw text content of td (for cells without links)

        # Link tracking
        self.in_a = False
        self.a_href = ""
        self.a_text = ""

        # Caption tracking
        self.in_caption = False
        self.caption_text = ""

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "title":
            self.in_title = True
        elif tag == "caption":
            self.in_caption = True
            self.caption_text = ""
        elif tag == "table" and attrs.get("class") == "list_table":
            # Will be set to True when caption "Crashes" is detected
            pass
        elif tag == "tbody" and self.in_crashes_table:
            self.in_tbody = True
        elif tag == "tr" and self.in_tbody:
            self.in_tr = True
            self.col_idx = 0
            self.current_row = [""] * 13
        elif tag == "td" and self.in_tr:
            self.in_td = True
            self.td_class = attrs.get("class", "")
            self.td_attrs = attrs
            self.td_hrefs = []
            self.td_link_labels = []
            self.td_raw_text = ""
        elif tag == "a" and self.in_td:
            self.in_a = True
            self.a_href = attrs.get("href", "")
            self.a_text = ""

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        elif tag == "caption":
            self.in_caption = False
            if "Crashes" in self.caption_text:
                self.in_crashes_table = True
        elif tag == "table":
            self.in_crashes_table = False
        elif tag == "tbody":
            self.in_tbody = False
        elif tag == "tr" and self.in_tr:
            self.in_tr = False
            if self.current_row and any(c.strip() for c in self.current_row[:5]):
                self._process_row()
        elif tag == "td" and self.in_td:
            self.in_td = False

            # For cells with links, store hrefs
            if self.td_hrefs:
                if self.td_class == "assets":
                    # Store all asset hrefs with their labels
                    parts = []
                    for h, l in zip(self.td_hrefs, self.td_link_labels):
                        parts.append(f"{h}\t{l}")
                    self.current_row[self.col_idx] = "\n".join(parts)
                else:
                    # For non-asset cells, use the first href
                    self.current_row[self.col_idx] = self.td_hrefs[0]
            else:
                # No links — use raw text content
                self.current_row[self.col_idx] = self.td_raw_text.strip()

            # Store td title attribute for commit hash extraction
            if self.td_attrs.get("title"):
                if not hasattr(self, '_td_titles'):
                    self._td_titles = {}
                self._td_titles[self.col_idx] = self.td_attrs["title"]
            self.col_idx += 1
        elif tag == "a" and self.in_a:
            self.in_a = False
            self.td_hrefs.append(self.a_href)
            self.td_link_labels.append(self.a_text)

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        if self.in_caption:
            self.caption_text += data
        if self.in_td and not self.in_a:
            self.td_raw_text += data
        if self.in_a:
            self.a_text += data

    def _process_row(self):
        row = self.current_row
        # Column layout (0-indexed):
        # 0:Time  1:Kernel  2:Kernel-commit  3:Syzkaller-commit
        # 4:Config  5:CrashLog  6:Report  7:SyzRepro  8:CRepro
        # 9:MachineInfo  10:Assets  11:Manager  12:Title

        if len(row) < 11:
            return

        # Extract full kernel commit from td[2] title attr or href
        kernel_commit = row[2]
        td_title = getattr(self, '_td_titles', {}).get(2, "")
        if td_title:
            m = re.search(r"([0-9a-f]{40})", td_title)
            if m:
                kernel_commit = m.group(1)

        # Extract syzkaller commit from href
        syz_commit = ""
        if row[3]:
            m = re.search(r"commits/([0-9a-f]{40})", row[3])
            if m:
                syz_commit = m.group(1)

        inst = {
            "time": row[0] if len(row) > 0 else "",
            "kernel_tree": row[1] if len(row) > 1 else "",
            "kernel_commit": kernel_commit,
            "syzkaller_commit": syz_commit,
            "config_url": row[4] if len(row) > 4 else "",
            "crash_log_url": row[5] if len(row) > 5 else "",
            "report_url": row[6] if len(row) > 6 else "",
            "syz_repro_url": self._clean_repro(row[7]) if len(row) > 7 else "",
            "c_repro_url": self._clean_repro(row[8]) if len(row) > 8 else "",
            "machine_info_url": row[9] if len(row) > 9 else "",
            "bzImage_url": "",
            "vmlinux_url": "",
            "disk_url": "",
            "raw_title": row[12] if len(row) > 12 else "",
        }

        # Parse asset links (col 10) — stored as "url\tlabel\nurl\tlabel..."
        if len(row) > 10 and row[10]:
            for line in row[10].split("\n"):
                if "\t" in line:
                    url, label = line.split("\t", 1)
                    label_lower = label.lower()
                    if "kernel image" in label_lower or "bzimage" in label_lower:
                        inst["bzImage_url"] = url
                    elif "vmlinux" in label_lower:
                        inst["vmlinux_url"] = url
                    elif "disk" in label_lower:
                        inst["disk_url"] = url

        self.instances.append(inst)

    @staticmethod
    def _clean_repro(text):
        """Extract reproducer URL from cell content."""
        if not text:
            return ""
        m = re.search(r"tag=Repro(Syz|C)(?:&|&amp;)x=[0-9a-f]+", text)
        if m:
            return "/text?" + m.group(0)
        return text


def score_instance(inst):
    """Score an instance for selection. Higher = better."""
    score = 0
    if inst["c_repro_url"]:
        score += 1000
    if inst["syz_repro_url"]:
        score += 900
    if inst["crash_log_url"]:
        score += 100
    assets = sum(1 for u in [inst["bzImage_url"], inst["vmlinux_url"], inst["disk_url"]] if u)
    score += assets * 50
    if inst["kernel_commit"]:
        score += 30
    if inst["syzkaller_commit"]:
        score += 10
    return score


def parse_page(html_text):
    parser = SyzbotParser()
    parser.feed(html_text)
    return parser.title.strip(), parser.instances


def main():
    # Get input
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg.startswith("http://") or arg.startswith("https://"):
            with urlopen(arg) as resp:
                html_text = resp.read().decode("utf-8", errors="replace")
        else:
            with open(arg, "r", encoding="utf-8", errors="replace") as f:
                html_text = f.read()
    else:
        html_text = sys.stdin.read()

    title, instances = parse_page(html_text)

    if not instances:
        print("ERROR: No crash instances found in page.", file=sys.stderr)
        sys.exit(1)

    # Score and sort
    scored = [(score_instance(inst), inst) for inst in instances]
    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best = scored[0]

    # Determine tier
    if best["c_repro_url"] or best["syz_repro_url"]:
        tier = 1
    elif best["crash_log_url"] and best["bzImage_url"] and best["vmlinux_url"] and best["disk_url"] and best["kernel_commit"]:
        tier = 2
    elif best["crash_log_url"] and best["bzImage_url"] and best["vmlinux_url"] and best["kernel_commit"]:
        tier = 3
    else:
        tier = 99

    # Extract extid from page if we have a URL
    extid = ""
    if len(sys.argv) > 1:
        m = re.search(r"extid=([0-9a-f]+)", sys.argv[1])
        if m:
            extid = m.group(1)

    # Human-readable output (stdout)
    print(f"TITLE: {title}")
    print(f"EXTID: {extid}")
    print(f"INSTANCES: {len(instances)}")
    print(f"TIER: {tier}")
    print(f"KERNEL_COMMIT: {best['kernel_commit']}")
    print(f"SYZKALLER_COMMIT: {best['syzkaller_commit']}")
    print(f"KERNEL_TREE: {best['kernel_tree']}")
    print(f"CRASH_TIME: {best['time']}")
    print(f"SYZ_REPRO: {best['syz_repro_url'] or '(none)'}")
    print(f"C_REPRO: {best['c_repro_url'] or '(none)'}")
    print(f"CRASH_LOG: {best['crash_log_url'] or '(none)'}")
    print(f"CRASH_REPORT: {best['report_url'] or '(none)'}")
    print(f"CONFIG: {best['config_url'] or '(none)'}")
    print(f"BZIMAGE: {best['bzImage_url'] or '(none)'}")
    print(f"VMLINUX: {best['vmlinux_url'] or '(none)'}")
    print(f"DISK: {best['disk_url'] or '(none)'}")
    print()
    print("# All instances:")
    for i, (score, inst) in enumerate(scored):
        has_repro = "C" if inst["c_repro_url"] else ("S" if inst["syz_repro_url"] else "-")
        has_log = "Y" if inst["crash_log_url"] else "-"
        has_assets = sum(1 for u in [inst["bzImage_url"], inst["vmlinux_url"], inst["disk_url"]] if u)
        kh = inst['kernel_commit']
        print(f"  [{i}] score={score:4d} repro={has_repro} log={has_log} assets={has_assets}/3 "
              f"commit={kh[:12] if len(kh) >= 12 else kh} "
              f"time={inst['time']}")

    # JSON on stderr for programmatic use
    output = {k: v for k, v in best.items() if k != "raw_title"}
    output["title"] = title
    output["extid"] = extid
    output["total_instances"] = len(instances)
    output["selected_tier"] = tier
    output["all_instances"] = instances
    print("\n# --- JSON ---", file=sys.stderr)
    json.dump(output, sys.stderr, indent=2)


if __name__ == "__main__":
    main()
