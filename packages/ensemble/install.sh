#!/usr/bin/env bash
# Install Ensemble for Claude Code.
#   ./install.sh            the `ens` command and the two skills
#   ./install.sh --hook     also: show `ens listen` at the start of every Claude Code session
#   ./install.sh --mcp      also: register `ens mcp` as an MCP server (user scope)
# Re-run any time to update. Nothing outside ~/.ensemble, ~/.local/bin/ens and ~/.claude is touched.
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
HOME_DIR="${ENSEMBLE_HOME:-$HOME/.ensemble}"
APP="$HOME_DIR/app"
VENV="$HOME_DIR/venv"
BIN="$HOME/.local/bin"
SKILLS="$HOME/.claude/skills"
PY="${PYTHON:-python3}"

want_hook=0; want_mcp=0
for a in "$@"; do
  case "$a" in
    --hook) want_hook=1 ;;
    --mcp) want_mcp=1 ;;
    *) echo "unknown option $a"; exit 2 ;;
  esac
done

echo "-> app in $APP"
mkdir -p "$APP" "$BIN" "$SKILLS"
for f in "$SRC"/*.py "$SRC/requirements.txt" "$SRC/README.md"; do
  case "$(basename "$f")" in test_*|simulate.py|compare.py|calibrate.py) continue ;; esac
  cp "$f" "$APP/"
done

if [ ! -x "$VENV/bin/python" ]; then
  echo "-> python environment in $VENV"
  "$PY" -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install -q --upgrade pip
if [ "$want_mcp" = 1 ]; then
  "$VENV/bin/python" -m pip install -q -r "$APP/requirements.txt"
else
  "$VENV/bin/python" -m pip install -q numpy wordfreq
fi

echo "-> command $BIN/ens"
cat > "$BIN/ens" <<EOF
#!/bin/sh
exec "$VENV/bin/python" "$APP/ens.py" "\$@"
EOF
chmod +x "$BIN/ens"

echo "-> skills in $SKILLS (ensemble, ensemble-night)"
for s in ensemble ensemble-night; do
  mkdir -p "$SKILLS/$s"
  cp "$SRC/claude/skills/$s/SKILL.md" "$SKILLS/$s/SKILL.md"
done

if [ "$want_hook" = 1 ]; then
  echo "-> SessionStart hook in ~/.claude/settings.json (backup kept)"
  "$VENV/bin/python" - "$BIN/ens" <<'EOF'
import json, os, shutil, sys
path = os.path.expanduser("~/.claude/settings.json")
cmd = f"{sys.argv[1]} --listen"
data = {}
if os.path.exists(path):
    shutil.copy(path, path + ".bak-ensemble")
    with open(path) as f:
        data = json.load(f)
groups = data.setdefault("hooks", {}).setdefault("SessionStart", [])
if not any(h.get("command") == cmd for g in groups for h in g.get("hooks", [])):
    groups.append({"hooks": [{"type": "command", "command": cmd}]})
with open(path, "w") as f:
    json.dump(data, f, indent=2)
EOF
fi

if [ "$want_mcp" = 1 ]; then
  if command -v claude >/dev/null 2>&1; then
    echo "-> MCP server 'ensemble' (user scope)"
    claude mcp add --transport stdio --scope user ensemble -- "$BIN/ens" mcp || true
  else
    echo "!! claude CLI not found; register later with:"
    echo "   claude mcp add --transport stdio --scope user ensemble -- $BIN/ens mcp"
  fi
fi

case ":$PATH:" in *":$BIN:"*) ;; *) echo "!! add $BIN to your PATH (e.g. in ~/.zshrc: export PATH=\"$BIN:\$PATH\")" ;; esac
echo "done. Try: ens help   then, in any project: ens listen"
