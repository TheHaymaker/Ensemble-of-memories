"""Views of a family tree.

    render_html(family, path)   one self-contained page: generations as rows, parent-to-child
                                lines, coming of age drawn as the same project continuing,
                                approved kinship dashed, retired members faded; each member
                                shows its traits and marks; click one for its details.
    to_mermaid(family)          a Mermaid flowchart (renders in GitLab, Confluence, GitHub, Obsidian)
"""
import html
import json

from family import TRAITS


def _layout(fam):
    gens = {}
    for n, m in fam["members"].items():
        gens.setdefault(m["gen"], []).append(n)
    x = {}
    for g in sorted(gens):
        def key(n):
            ps = [x[p] for p in fam["members"][n]["parents"] if p in x]
            return (sum(ps) / len(ps) if ps else -1, n)
        row = sorted(gens[g], key=key)
        for i, n in enumerate(row):
            x[n] = i
        # centre children under their parents where possible
        for n in row:
            ps = [x[p] for p in fam["members"][n]["parents"] if p in x and p not in row]
            if ps:
                x[n] = max(x[n], sum(ps) / len(ps))
        row = sorted(row, key=lambda n: x[n])
        for i in range(1, len(row)):
            x[row[i]] = max(x[row[i]], x[row[i - 1]] + 1)
    return x, gens


def _data(family):
    fam = family._load()
    members = {}
    for n, m in fam["members"].items():
        try:
            traits = family.traits(n, fam)
            marks = family.effective_marks(n, fam)
        except Exception:                                  # a member whose store is gone
            traits, marks = m.get("final_traits", m["born_traits"]), m["marks"]
        members[n] = {"gen": m["gen"], "parents": m["parents"], "status": m["status"],
                      "traits": traits, "marks": marks, "came_of_age": m.get("came_of_age"),
                      "suggestion": fam.get("suggestions", {}).get(n),
                      "sayings": [s["text"] for s in fam["sayings"].values() if s["from"] == n][:8],
                      "heirlooms": [h["text"] for h in fam["heirlooms"].values() if h["from"] == n]}
    return fam, members


def render_html(family, path, title="Family tree"):
    fam, members = _data(family)
    x, gens = _layout(fam)
    W, H, NW, NH = 210, 150, 170, 92
    width = int((max(x.values(), default=0) + 1) * W + 40)
    height = int(max(gens, default=1) * H + 20)
    pos = {n: (20 + x[n] * W, 20 + (members[n]["gen"] - 1) * H) for n in members}
    edges = []
    for n, m in members.items():
        for p in m["parents"]:
            if p not in pos:
                continue
            (x1, y1), (x2, y2) = pos[p], pos[n]
            same = (m.get("came_of_age") or {}).get("from") == p
            edges.append(f'<path class="edge{" continues" if same else ""}" d="M{x1 + NW / 2},{y1 + NH} '
                         f'C{x1 + NW / 2},{y1 + NH + 40} {x2 + NW / 2},{y2 - 40} {x2 + NW / 2},{y2}"/>')
    for a, b in fam.get("kin", []):
        if a in pos and b in pos:
            (x1, y1), (x2, y2) = sorted((pos[a], pos[b]))             # left member first
            if x1 == x2:                                               # same column: arc out to the right
                sx, ex, c1, c2 = x1 + NW, x2 + NW, x1 + NW + 60, x2 + NW + 60
            else:                                                      # facing sides
                sx, ex, c1, c2 = x1 + NW, x2, x1 + NW + 50, x2 - 50
            edges.append(f'<path class="edge kin" d="M{sx},{y1 + NH / 2} C{c1},{y1 + NH / 2} '
                         f'{c2},{y2 + NH / 2} {ex},{y2 + NH / 2}"/>')
    nodes = []
    for n, m in members.items():
        px, py = pos[n]
        bars = "".join(
            f'<rect class="bar-bg" x="{px + 10}" y="{py + 34 + i * 11}" width="80" height="6" rx="3"/>'
            f'<rect class="bar" x="{px + 10}" y="{py + 34 + i * 11}" width="{80 * m["traits"][t]:.1f}" height="6" rx="3"/>'
            f'<text class="tl" x="{px + 96}" y="{py + 40 + i * 11}">{t[:5]}</text>'
            for i, t in enumerate(TRAITS))
        dots = "".join(f'<circle class="mark" cx="{px + NW - 14 - i * 12}" cy="{py + 16}" r="4.5" '
                       f'style="opacity:{0.25 + 0.75 * mk["strength"]:.2f}"><title>{html.escape(mk["theme"])} '
                       f'{mk["strength"]:.2f}</title></circle>' for i, mk in enumerate(m["marks"][:4]))
        flag = '<circle class="pending" cx="{}" cy="{}" r="5"/>'.format(px + 10, py + 16) \
            if (m.get("suggestion") or {}).get("status") == "pending" else ""
        nodes.append(f'<g class="node {m["status"]}" data-name="{html.escape(n)}" tabindex="0">'
                     f'<rect x="{px}" y="{py}" width="{NW}" height="{NH}" rx="10"/>{flag}'
                     f'<text class="name" x="{px + (20 if flag else 10)}" y="{py + 21}">{html.escape(n)}</text>'
                     f'{dots}{bars}</g>')
    wisdom = "".join(f"<li>{html.escape(w['text'])} <span class=muted>({', '.join(w['members'])})</span></li>"
                     for w in fam["wisdom"]) or "<li class=muted>none yet</li>"
    page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
:root {{ --bg:#fbfaf7; --fg:#1d1d1f; --muted:#6b6b70; --card:#ffffff; --line:#c9c6be; --accent:#2f6f8f;
        --mark:#c0392b; --barbg:#ebe8e1; --pending:#d4a017; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#16171a; --fg:#ececef; --muted:#9a9aa3; --card:#212227;
        --line:#4a4b52; --accent:#7fb7d3; --mark:#e06b5d; --barbg:#33343a; --pending:#e6bd3a; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font:14px/1.45 ui-sans-serif, -apple-system, "Segoe UI", sans-serif; background:var(--bg); color:var(--fg); }}
header {{ padding:20px 24px 6px; }} h1 {{ margin:0; font-size:20px; font-weight:650; }}
.legend {{ color:var(--muted); font-size:12.5px; margin-top:4px; }}
main {{ display:grid; grid-template-columns:minmax(0,1fr) 300px; gap:16px; padding:8px 24px 24px; }}
@media (max-width: 820px) {{ main {{ grid-template-columns:1fr; }} }}
.canvas {{ overflow:auto; background:var(--card); border:1px solid var(--line); border-radius:12px; }}
svg {{ display:block; }}
.edge {{ fill:none; stroke:var(--line); stroke-width:1.6; }}
.edge.continues {{ stroke:var(--accent); stroke-width:3; }}
.edge.kin {{ stroke:var(--accent); stroke-dasharray:5 5; }}
.node rect:first-child {{ fill:var(--card); stroke:var(--line); stroke-width:1.2; cursor:pointer; }}
.node:hover rect:first-child, .node:focus rect:first-child, .node.sel rect:first-child {{ stroke:var(--accent); stroke-width:2.2; outline:none; }}
.node.retired {{ opacity:.55; }}
.name {{ font-weight:650; font-size:13.5px; fill:var(--fg); }}
.tl {{ font-size:9.5px; fill:var(--muted); }}
.bar-bg {{ fill:var(--barbg); }} .bar {{ fill:var(--accent); }}
.mark {{ fill:var(--mark); }} .pending {{ fill:var(--pending); }}
aside {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px; align-self:start; }}
aside h2 {{ font-size:15px; margin:0 0 6px; }} aside h3 {{ font-size:12px; text-transform:uppercase; letter-spacing:.04em;
  color:var(--muted); margin:14px 0 4px; }}
aside ul {{ margin:0; padding-left:18px; }} .muted {{ color:var(--muted); }}
</style></head><body>
<header><h1>{html.escape(title)}</h1>
<div class="legend">Rows are generations. Thick line: the same project coming of age. Dashed: approved kinship.
Bars: curiosity, skepticism, steadiness, expressiveness. Red dots: inherited or lived marks (darker is stronger).
Yellow dot: a pending suggestion. Faded: retired. Click a member for details.</div></header>
<main><div class="canvas"><svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img"
aria-label="family tree">{''.join(edges)}{''.join(nodes)}</svg></div>
<aside id="panel"><h2>Family wisdom</h2><ul>{wisdom}</ul>
<p class="muted" style="margin-top:14px">Select a member to see its traits, marks, sayings and heirlooms.</p></aside></main>
<script>
const M = {json.dumps(members)};
const esc = s => String(s).replace(/[&<>"]/g, c => ({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}})[c]);
const list = xs => xs && xs.length ? "<ul>" + xs.map(t => "<li>" + esc(t) + "</li>").join("") + "</ul>" : "<p class=muted>none</p>";
const panel = document.getElementById("panel"), first = panel.innerHTML;
function show(name) {{
  document.querySelectorAll(".node").forEach(g => g.classList.toggle("sel", g.dataset.name === name));
  const m = M[name];
  const traits = Object.entries(m.traits).map(([k, v]) => k + " " + v.toFixed(2));
  const marks = m.marks.map(k => k.theme + " " + k.strength.toFixed(2) + (k.own ? " (lived)" : " (inherited)"));
  let h = "<h2>" + esc(name) + "</h2><p class=muted>generation " + m.gen + ", " + m.status +
          (m.parents.length ? ", from " + m.parents.map(esc).join(" + ") : ", founder") + "</p>";
  if (m.came_of_age) h += "<h3>Came of age</h3><p>" + esc(m.came_of_age.why || "") + "</p>";
  if (m.suggestion && m.suggestion.status === "pending") h += "<h3>Suggested: new generation</h3>" + list(m.suggestion.reasons);
  h += "<h3>Traits</h3>" + list(traits) + "<h3>Marks</h3>" + list(marks) +
       "<h3>Sayings it told</h3>" + list(m.sayings) + "<h3>Heirlooms</h3>" + list(m.heirlooms) +
       "<p style='margin-top:14px'><a href='#' id=back>Back to family wisdom</a></p>";
  panel.innerHTML = h;
  document.getElementById("back").onclick = e => {{ e.preventDefault(); panel.innerHTML = first;
    document.querySelectorAll(".node").forEach(g => g.classList.remove("sel")); }};
}}
document.querySelectorAll(".node").forEach(g => {{
  g.addEventListener("click", () => show(g.dataset.name));
  g.addEventListener("keydown", e => {{ if (e.key === "Enter") show(g.dataset.name); }});
}});
</script></body></html>"""
    with open(path, "w") as f:
        f.write(page)
    return path


def to_mermaid(family):
    fam, members = _data(family)
    ids = {n: f"n{i}" for i, n in enumerate(members)}
    lines = ["flowchart TD"]
    for n, m in members.items():
        mk = max((k["strength"] for k in m["marks"]), default=0)
        label = f"{n}<br/>gen {m['gen']}, {m['status']}" + (f"<br/>mark {mk:.2f}" if mk else "")
        lines.append(f'    {ids[n]}["{label}"]')
        if m["status"] == "retired":
            lines.append(f"    style {ids[n]} stroke-dasharray: 3 3")
    for n, m in members.items():
        for p in m["parents"]:
            arrow = "==>|came of age|" if (m.get("came_of_age") or {}).get("from") == p else "-->"
            lines.append(f"    {ids[p]} {arrow} {ids[n]}")
    for a, b in fam.get("kin", []):
        lines.append(f"    {ids[a]} -.-|kin| {ids[b]}")
    return "\n".join(lines)
