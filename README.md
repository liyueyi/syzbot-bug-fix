# syzbot-bug-fix

Claude Code skill for fully autonomous syzbot kernel bug fix — from URL to `.patch`.

## Install

```bash
# 1. Clone the skill
mkdir -p .claude/skills
git clone https://github.com/liyueyi/syzbot-bug-fix.git .claude/skills/syzbot-bug-fix

# 2. Add crash MCP server (for vmcore analysis)
claude mcp add crash-mcp -- crash-mcp-client /tmp/crash.sock
```

The crash MCP server is [liyy-crash](https://github.com/liyueyi/liyy-crash/tree/mcp) (mcp branch).

## Prerequisites

`qemu-system-x86_64` `busybox` `gcc` `go` `crash` `cpio` `curl`

## Usage

Paste a syzbot bug URL in Claude Code:

```
https://syzkaller.appspot.com/bug?extid=8b12fc6e0fb139765b58
```

The skill runs autonomously through: bug triage → asset download → reproducer
acquisition → QEMU reproduction + vmcore → kernel source → crash dump analysis →
fix → rebuild + verify → `git format-patch`.

## License

MIT
