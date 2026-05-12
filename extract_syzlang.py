#!/usr/bin/env python3
"""
extract_syzlang.py - Extract syzlang programs from a syzbot console log.

The syzbot console log has structure:
  [boot messages...]
  last executing test programs:
  TIMESTAMP ago: executing program N (id=NNNN):
  <syzlang code...>

  TIMESTAMP ago: executing program N (id=MMMM):
  <syzlang code...>

  [kernel messages and crash output]

Usage:
  curl -sL "https://syzkaller.appspot.com/text?tag=CrashLog&x=XXXX" | python3 extract_syzlang.py
  python3 extract_syzlang.py console_log.txt
  python3 extract_syzlang.py --last 3 console_log.txt    # only last N programs
  python3 extract_syzlang.py --dump console_log.txt      # save each program to progs/
"""

import re
import sys
import os


def parse_console_log(text):
    """Parse console log and extract syzlang program blocks.

    Returns list of dicts: {id, number, timestamp, code_lines}
    """
    programs = []
    current = None

    # Lines like: "16m13.675133948s ago: executing program 3 (id=5045):"
    header_re = re.compile(
        r'^(\S+)\s+ago:\s+executing\s+program\s+(\d+)\s+\(id=(\d+)\):\s*$'
    )

    for line in text.split('\n'):
        m = header_re.match(line)
        if m:
            if current and current.get('code_lines'):
                programs.append(current)
            current = {
                'timestamp': m.group(1),
                'program_number': m.group(2),
                'id': m.group(3),
                'code_lines': []
            }
            continue

        if current is not None:
            stripped = line.rstrip()
            if stripped == '':
                # Blank line ends the program block
                if current.get('code_lines'):
                    programs.append(current)
                current = None
            else:
                current['code_lines'].append(stripped)

    # Don't forget the last one
    if current and current.get('code_lines'):
        programs.append(current)

    return programs


def main():
    last_n = None
    dump_dir = None
    args = sys.argv[1:]

    i = 0
    while i < len(args):
        if args[i] == '--last':
            i += 1
            last_n = int(args[i])
        elif args[i] == '--dump':
            i += 1
            dump_dir = args[i]
        else:
            break
        i += 1

    # Read input
    if i < len(args):
        with open(args[i], 'r', encoding='utf-8', errors='replace') as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    programs = parse_console_log(text)

    if not programs:
        print("ERROR: No syzlang programs found in console log.", file=sys.stderr)
        sys.exit(1)

    # Filter to last N
    if last_n:
        programs = programs[-last_n:]

    # Output
    for p in programs:
        print(f"# Program id={p['id']} num={p['program_number']} {p['timestamp']} ago")
        for line in p['code_lines']:
            print(line)
        print()

    # Summary on stderr
    print(f"Extracted {len(programs)} program(s) from console log.", file=sys.stderr)
    if last_n:
        print(f"(showing last {last_n})", file=sys.stderr)

    # Optionally dump to files
    if dump_dir:
        os.makedirs(dump_dir, exist_ok=True)
        for p in programs:
            fname = f"prog_{p['id']}_{p['program_number']}.syz"
            fpath = os.path.join(dump_dir, fname)
            with open(fpath, 'w') as f:
                for line in p['code_lines']:
                    f.write(line + '\n')
            print(f"  Wrote {fpath}", file=sys.stderr)


if __name__ == "__main__":
    main()
