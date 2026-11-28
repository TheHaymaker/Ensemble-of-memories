#!/usr/bin/env bash
# Install Family Matters for Claude Code.
#   ./install.sh            the `fam` command and the skills (family-matters, and the night: thats-not-how-i-remember-it
#                           plus seven alias skills named after other family sayings)
#   ./install.sh --hook     also: family dinner (`fam --listen`) at the start of every Claude Code session
#   ./install.sh --mcp      also: register `fam mcp` as an MCP server (user scope)
# Re-run any time to update. Nothing outside ~/.family-matters, ~/.local/bin/{fam,ens} and ~/.claude is touched.
#
# Upgrading from Ensemble: an existing ~/.ensemble is moved to ~/.family-matters (memories, family and
# all), with a symlink left behind; `ens` becomes a shim for `fam`; the old skills, SessionStart hook
# and MCP registration are swapped for the new ones. Old command names keep working as aliases.
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
OLD_HOME="$HOME/.ensemble"
HOME_DIR="${FAM_HOME:-${ENSEMBLE_HOME:-$HOME/.family-matters}}"
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

# --- moving out of ~/.ensemble (only with the default home, and only once)
if [ -z "${FAM_HOME:-}${ENSEMBLE_HOME:-}" ] && [ -d "$OLD_HOME" ] && [ ! -L "$OLD_HOME" ] && [ ! -e "$HOME_DIR" ]; then
  echo "-> moving $OLD_HOME to $HOME_DIR (the family is relocating; a symlink stays behind)"
  mv "$OLD_HOME" "$HOME_DIR"
  rm -rf "$HOME_DIR/venv" "$HOME_DIR/app"          # rebuilt below; a moved venv points at its old path
  ln -s "$HOME_DIR" "$OLD_HOME"
fi

echo "-> app in $APP"
mkdir -p "$APP" "$BIN" "$SKILLS"
for f in "$SRC"/*.py "$SRC/requirements.txt" "$SRC/README.md"; do
  case "$(basename "$f")" in test_*|simulate.py|compare.py|calibrate.py) continue ;; esac
  cp "$f" "$APP/"
done
rm -f "$APP/ens.py"                                 # renamed to fam.py

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

echo "-> command $BIN/fam (and $BIN/ens, the old name, as a shim)"
cat > "$BIN/fam" <<EOF
#!/bin/sh
exec "$VENV/bin/python" "$APP/fam.py" "\$@"
EOF
cat > "$BIN/ens" <<EOF
#!/bin/sh
# Ensemble is now Family Matters: \`ens\` is kept as a shim for \`fam\`. Old command names still work.
[ "\$1" = "--listen" ] || [ "\$1" = "mcp" ] || echo "(ens is now fam: Family Matters. Old commands still work.)" >&2
exec "$BIN/fam" "\$@"
EOF
chmod +x "$BIN/fam" "$BIN/ens"

echo "-> skills in $SKILLS (family-matters, thats-not-how-i-remember-it and its aliases)"
for d in "$SRC"/claude/skills/*/; do
  s="$(basename "$d")"
  mkdir -p "$SKILLS/$s"
  cp "$d/SKILL.md" "$SKILLS/$s/SKILL.md"
done
for s in ensemble ensemble-night family-therapy; do  # old skills, if an earlier version installed them
  if [ -f "$SKILLS/$s/SKILL.md" ] && grep -Eq '^allowed-tools: Bash\((ens|fam) \*\)' "$SKILLS/$s/SKILL.md"; then
    echo "-> removing old skill $s"
    rm -rf "${SKILLS:?}/$s"
  fi
done

if [ "$want_hook" = 1 ]; then
  echo "-> SessionStart hook in ~/.claude/settings.json (backup kept)"
  "$VENV/bin/python" - "$BIN/fam" "$BIN/ens" <<'EOF'
import json, os, shutil, sys
path = os.path.expanduser("~/.claude/settings.json")
cmd, old = f"{sys.argv[1]} --listen", f"{sys.argv[2]} --listen"
data = {}
if os.path.exists(path):
    shutil.copy(path, path + ".bak-family-matters")
    with open(path) as f:
        data = json.load(f)
groups = data.setdefault("hooks", {}).setdefault("SessionStart", [])
for g in groups:                                   # swap Ensemble's old hook for the new one
    for h in g.get("hooks", []):
        if h.get("command") == old:
            h["command"] = cmd
seen = False
for g in groups:                                   # and keep exactly one
    keep = []
    for h in g.get("hooks", []):
        if h.get("command") == cmd:
            if seen:
                continue
            seen = True
        keep.append(h)
    g["hooks"] = keep
groups[:] = [g for g in groups if g.get("hooks")]
if not seen:
    groups.append({"hooks": [{"type": "command", "command": cmd}]})
with open(path, "w") as f:
    json.dump(data, f, indent=2)
EOF
fi

if [ "$want_mcp" = 1 ]; then
  if command -v claude >/dev/null 2>&1; then
    echo "-> MCP server 'family-matters' (user scope)"
    claude mcp remove --scope user ensemble >/dev/null 2>&1 || true
    claude mcp add --transport stdio --scope user family-matters -- "$BIN/fam" mcp || true
  else
    echo "!! claude CLI not found; register later with:"
    echo "   claude mcp add --transport stdio --scope user family-matters -- $BIN/fam mcp"
  fi
fi

case ":$PATH:" in *":$BIN:"*) ;; *) echo "!! add $BIN to your PATH (e.g. in ~/.zshrc: export PATH=\"$BIN:\$PATH\")" ;; esac
echo "done. Try: fam help   then, in any project: fam dinner"
