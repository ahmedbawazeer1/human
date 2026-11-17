"""Turn docs/slides.md (Marp-style markdown) into docs/slides.html: one self-contained
page, arrow keys / click to move between slides, presenter notes hidden.

    python docs/build_slides.py
"""
from __future__ import annotations

import html
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent


def inline(t: str) -> str:
    t = html.escape(t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"`(.+?)`", r"<code>\1</code>", t)
    t = re.sub(r"(?<!\*)\*(?!\s)(.+?)\*", r"<em>\1</em>", t)
    return t


def render(block: str) -> str:
    block = re.sub(r"<!--.*?-->", "", block, flags=re.S).strip()
    out, lines, i = [], block.splitlines(), 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("```"):
            j = i + 1
            while j < len(lines) and not lines[j].startswith("```"):
                j += 1
            out.append("<pre>" + html.escape("\n".join(lines[i + 1:j])) + "</pre>")
            i = j + 1
            continue
        if ln.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                if not re.match(r"^\|[\s\-|]+\|$", lines[i]):
                    rows.append([c.strip() for c in lines[i].strip("|").split("|")])
                i += 1
            head, body = rows[0], rows[1:]
            out.append("<table><tr>" + "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr>"
                       + "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in body)
                       + "</table>")
            continue
        if ln.startswith("- "):
            items = []
            while i < len(lines) and lines[i].startswith("- "):
                items.append(f"<li>{inline(lines[i][2:])}</li>")
                i += 1
            out.append("<ul>" + "".join(items) + "</ul>")
            continue
        m = re.match(r"^(#{1,3}) (.+)$", ln)
        if m:
            out.append(f"<h{len(m.group(1))}>{inline(m.group(2))}</h{len(m.group(1))}>")
        elif ln.strip():
            out.append(f"<p>{inline(ln)}</p>")
        i += 1
    return "\n".join(out)


def main():
    src = (HERE / "slides.md").read_text(encoding="utf-8")
    parts = [p for p in re.split(r"^---\s*$", src, flags=re.M) if p.strip()]
    parts = parts[1:] if parts and "marp:" in parts[0] else parts  # drop front matter
    slides = "\n".join(f'<section class="slide">{render(p)}<div class="num">{i}/{len(parts)}</div></section>'
                       for i, p in enumerate(parts, 1))
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Open Venture Builder</title>
<style>
:root{{--bg:#0f172a;--card:#ffffff;--ink:#111827;--muted:#4b5563;--accent:#4f46e5}}
body{{margin:0;background:var(--bg);font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif}}
.slide{{display:none;box-sizing:border-box;width:100vw;height:100vh;padding:6vh 7vw;background:var(--card);color:var(--ink);position:relative;overflow:auto}}
.slide.on{{display:block}} h1{{font-size:3.2em;margin:.2em 0;color:var(--accent)}} h2{{font-size:2.2em;color:var(--accent);margin-top:0}}
h3{{font-size:1.5em;font-weight:500}} p,li,td,th{{font-size:1.35em;line-height:1.45}} li{{margin:.35em 0}}
table{{border-collapse:collapse;width:100%}} td,th{{border-bottom:1px solid #e5e7eb;padding:.45em .6em;text-align:left;vertical-align:top}}
th{{color:var(--muted)}} pre{{background:#f3f4f6;padding:1em;border-radius:8px;font-size:1.15em;white-space:pre-wrap}}
code{{background:#eef2ff;padding:.05em .3em;border-radius:4px}} .num{{position:absolute;right:3vw;bottom:2vh;color:var(--muted)}}
</style></head><body>
{slides}
<script>
const s=[...document.querySelectorAll('.slide')];let i=0;const show=n=>{{i=Math.max(0,Math.min(s.length-1,n));s.forEach((e,k)=>e.classList.toggle('on',k===i));}};
document.addEventListener('keydown',e=>{{if(['ArrowRight','PageDown',' '].includes(e.key))show(i+1);if(['ArrowLeft','PageUp'].includes(e.key))show(i-1);}});
document.addEventListener('click',e=>show(e.clientX>innerWidth/2?i+1:i-1));show(0);
</script></body></html>"""
    (HERE / "slides.html").write_text(page, encoding="utf-8")
    print(f"{len(parts)} slides -> docs/slides.html")


if __name__ == "__main__":
    main()
