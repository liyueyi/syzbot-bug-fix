# syzbot-bug-fix

Claude Code skill for fully autonomous syzbot kernel bug fix — from URL to `.patch`.

## Install

```bash
# 1. Clone the skill
mkdir -p .claude/skills
git clone https://github.com/liyueyi/syzbot-bug-fix.git .claude/skills/syzbot-bug-fix

# 2. Build crash MCP server (for vmcore analysis)
git clone https://github.com/liyueyi/liyy-crash.git /tmp/liyy-crash
cd /tmp/liyy-crash && git checkout mcp && make

# 3. Add crash MCP to Claude Code
# NOTE: This will fail on first connection because the crash server isn't
# running yet. The skill starts crash --mcp vmcore vmlinux during Phase 6,
# then Claude Code auto-reconnects. The initial failure is expected.
claude mcp add crash-mcp -- /tmp/liyy-crash/crash-mcp-client /tmp/crash.sock
```

## Usage

Paste a syzbot bug URL in Claude Code:

```
fix https://syzkaller.appspot.com/bug?extid=8b12fc6e0fb139765b58
```

The skill runs autonomously through: bug triage → asset download → reproducer
acquisition → QEMU reproduction + vmcore → kernel source → crash dump analysis →
fix → rebuild + verify → `git format-patch`.

## License

MIT
