#!/usr/bin/env python3
"""Keyword search for the ESOL library.

Run this AFTER home.py has (re)generated index.html, from the esol repo root:

    python3 tools/build_search_index.py [path-to-esol-repo]

What it does:
  1. Patches index.html's inline <script> to add content-word search
     (merged into the existing #q box) — idempotent, safe to re-run.
  2. Parses index.html for every library row (this is the single source
     of truth: whatever home.py left off the page because it's "hidden"
     is automatically left off here too — no separate exclusion list to
     maintain).
  3. For each row, extracts plain text from its linked .docx/.pptx/.xlsx
     file, or from a sibling .html/.htm page's own static text. PDFs are
     skipped (every PDF in this library has a .docx twin with the same
     text, so nothing is lost).
  4. Writes search-index.json next to index.html, keyed by each row's
     primary link, fetched lazily by the page's own script.

Dependencies: beautifulsoup4, python-docx, python-pptx, openpyxl.
"""
import json
import os
import re
import sys

from bs4 import BeautifulSoup

try:
    import docx as docx_lib
except ImportError:
    docx_lib = None
try:
    from pptx import Presentation
except ImportError:
    Presentation = None
try:
    import openpyxl
except ImportError:
    openpyxl = None

MAX_CHARS_PER_ENTRY = 20000
INDEXABLE_EXTS = {".docx", ".pptx", ".xlsx", ".html", ".htm"}

# ---------------------------------------------------------------- extraction

def clean_text(text):
    return re.sub(r"\s+", " ", text).strip()


def extract_docx(path):
    if docx_lib is None:
        return ""
    d = docx_lib.Document(path)
    parts = [p.text for p in d.paragraphs]
    for table in d.tables:
        for row in table.rows:
            for cell in row.cells:
                parts.append(cell.text)
    return clean_text(" ".join(parts))


def extract_pptx(path):
    if Presentation is None:
        return ""
    prs = Presentation(path)
    parts = []
    for slide in prs.slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                parts.append(shape.text_frame.text)
            if shape.has_table:
                for row in shape.table.rows:
                    for cell in row.cells:
                        parts.append(cell.text)
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
            parts.append(slide.notes_slide.notes_text_frame.text)
    return clean_text(" ".join(parts))


def extract_xlsx(path):
    if openpyxl is None:
        return ""
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    parts = []
    for ws in wb.worksheets:
        for row in ws.iter_rows(values_only=True):
            for v in row:
                if v is not None:
                    parts.append(str(v))
    return clean_text(" ".join(parts))


def extract_html(path):
    # Static DOM text only (deliberate — see module docstring). Many of
    # this library's interactive pages build their content as JS data at
    # runtime, which a text extractor can't see; chasing it would be a
    # maintenance trap for little gain, since the real content-search
    # value is in the docx/pptx/xlsx files anyway.
    with open(path, encoding="utf-8", errors="ignore") as f:
        html = f.read()
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    return clean_text(soup.get_text(" ", strip=True))


EXTRACTORS = {
    ".docx": extract_docx,
    ".pptx": extract_pptx,
    ".xlsx": extract_xlsx,
    ".html": extract_html,
    ".htm": extract_html,
}


def extract_text(path):
    ext = os.path.splitext(path)[1].lower()
    fn = EXTRACTORS.get(ext)
    if not fn:
        return ""
    try:
        return fn(path)[:MAX_CHARS_PER_ENTRY]
    except Exception as e:
        print(f"  ! could not extract {path}: {e}", file=sys.stderr)
        return ""


# ------------------------------------------------------------ index.html -> rows

def row_candidate_paths(li, repo_root):
    """Primary link href, plus any .docx/.pptx/.xlsx download links in
    the row's actions (so a PDF-fronted worksheet still gets indexed via
    its Word twin). Returns (key_href, [absolute file paths to extract])."""
    main_a = li.select_one("a.t")
    if not main_a or not main_a.get("href"):
        return None, []
    key_href = main_a["href"]
    hrefs = [key_href]
    for a in li.select("span.acts a.tag[href]"):
        hrefs.append(a["href"])
    paths = []
    seen = set()
    for href in hrefs:
        if href.startswith(("http://", "https://", "mailto:")):
            continue
        ext = os.path.splitext(href)[1].lower()
        if ext not in INDEXABLE_EXTS:
            continue
        abspath = os.path.normpath(os.path.join(repo_root, href))
        if abspath in seen or not os.path.isfile(abspath):
            continue
        seen.add(abspath)
        paths.append(abspath)
    return key_href, paths


def build_index(repo_root):
    index_path = os.path.join(repo_root, "index.html")
    with open(index_path, encoding="utf-8") as f:
        html = f.read()
    soup = BeautifulSoup(html, "html.parser")

    index = {}
    text_cache = {}
    n_rows = n_indexed = 0
    for li in soup.select("li.row"):
        n_rows += 1
        key_href, paths = row_candidate_paths(li, repo_root)
        if not key_href or not paths:
            continue
        texts = []
        for p in paths:
            if p not in text_cache:
                text_cache[p] = extract_text(p)
            if text_cache[p]:
                texts.append(text_cache[p])
        if texts:
            index[key_href] = clean_text(" ".join(texts))[:MAX_CHARS_PER_ENTRY]
            n_indexed += 1

    print(f"Indexed {n_indexed} of {n_rows} library rows "
          f"({len(text_cache)} source files read).")
    return index


# ------------------------------------------------------------ UI patch (idempotent)

OLD_SCRIPT_MARKER = '(function(){var f={lvl:"",skill:[],g:"",t:"",e:"",r:"",type:"",coll:""},q="",browse=false;'
NEW_SCRIPT_MARKER = "/*content-search-v1*/"


def build_new_script(old_script):
    """Returns the patched script, or None if already patched or the
    anchor text wasn't found (template changed upstream — re-check by
    hand rather than silently doing nothing)."""
    if NEW_SCRIPT_MARKER in old_script:
        return None  # already patched
    if OLD_SCRIPT_MARKER not in old_script:
        raise SystemExit(
            "index.html's inline script doesn't match the expected template "
            "(home.py's JS output may have changed) — re-check this patch by hand."
        )

    addition = r"""
%s
var contentIdx=null;
fetch("search-index.json").then(function(r){return r.ok?r.json():{}}).catch(function(){return {}}).then(function(j){contentIdx=j||{};apply()});
function qWords(){return q.split(/\s+/).filter(Boolean)}
function titleMatch(d){var w=qWords();if(!w.length)return true;return w.every(function(x){return d.q.indexOf(x)>=0})}
function snippet(text,words){var low=text.toLowerCase(),pos=-1;for(var i=0;i<words.length;i++){var p=low.indexOf(words[i]);if(p>=0){pos=p;break}}
if(pos<0)return text.slice(0,140);var start=Math.max(0,pos-50),end=Math.min(text.length,pos+90);
return (start>0?"…":"")+text.slice(start,end).trim()+(end<text.length?"…":"")}
function contentMatch(li){var w=qWords();if(!w.length||!contentIdx)return null;
var a=li.querySelector("a.t");if(!a)return null;var text=contentIdx[a.getAttribute("href")];if(!text)return null;
var low=text.toLowerCase();if(!w.every(function(x){return low.indexOf(x)>=0}))return null;return text}
""" % NEW_SCRIPT_MARKER

    new_ok = '''function ok(el){var d=el.dataset;
if(f.lvl&&d.lvl.split(" ").indexOf(f.lvl)<0)return false;
if(f.skill.length&&!f.skill.some(function(s){return has(d.skill,s)}))return false;
if(!has(d.g,f.g)||!has(d.t,f.t)||!has(d.e,f.e)||!has(d.r,f.r)||!has(d.type,f.type)||!has(d.c,f.coll))return false;
return true}'''
    old_ok = '''function ok(el){var d=el.dataset;
if(f.lvl&&d.lvl.split(" ").indexOf(f.lvl)<0)return false;
if(f.skill.length&&!f.skill.some(function(s){return has(d.skill,s)}))return false;
if(!has(d.g,f.g)||!has(d.t,f.t)||!has(d.e,f.e)||!has(d.r,f.r)||!has(d.type,f.type)||!has(d.c,f.coll))return false;
return !q||d.q.indexOf(q)>=0}'''
    if old_ok not in old_script:
        raise SystemExit("ok() function text didn't match expected template — re-check by hand.")
    script = old_script.replace(old_ok, new_ok)

    old_section_loop = '''document.querySelectorAll("#results section").forEach(function(s){var n=0;if(f.lvl&&s.dataset.sec!==f.lvl&&s.dataset.sec!=="all"){s.hidden=true;return}
s.querySelectorAll("li.row").forEach(function(li){var m=ok(li);li.hidden=!m;if(m)n++});
s.hidden=!n;if(n)any=true});'''
    new_section_loop = '''document.querySelectorAll("#results section").forEach(function(s){var n=0;if(f.lvl&&s.dataset.sec!==f.lvl&&s.dataset.sec!=="all"){s.hidden=true;return}
var rows=Array.prototype.slice.call(s.querySelectorAll("li.row"));
rows.forEach(function(li,i){if(li.dataset.idx===undefined)li.dataset.idx=i});
rows.forEach(function(li){var filterOk=ok(li);var tMatch=filterOk&&titleMatch(li.dataset);var cText=null;
if(filterOk&&!tMatch)cText=contentMatch(li);
var show=filterOk&&(tMatch||cText!==null);
li.hidden=!show;li.classList.toggle("content-match",!!(show&&!tMatch&&cText));
var snip=li.querySelector(".search-snippet");
if(show&&!tMatch&&cText){if(!snip){snip=document.createElement("span");snip.className="search-snippet";snip.style.cssText="display:block;font-size:.85em;color:var(--muted);margin-top:.3em";var main=li.querySelector(".main");if(main)main.appendChild(snip)}
snip.textContent="Found in text: "+snippet(cText,qWords())}else if(snip){snip.remove()}
if(show)n++});
rows.sort(function(a,b){function rank(li){if(li.hidden)return 2;return li.classList.contains("content-match")?1:0}
var ra=rank(a),rb=rank(b);if(ra!==rb)return ra-rb;return (+a.dataset.idx)-(+b.dataset.idx)});
var ul=s.querySelector("ul.rows");if(ul)rows.forEach(function(li){ul.appendChild(li)});
s.hidden=!n;if(n)any=true});'''
    if old_section_loop not in script:
        raise SystemExit("results-section loop text didn't match expected template — re-check by hand.")
    script = script.replace(old_section_loop, new_section_loop)

    script = script.replace(OLD_SCRIPT_MARKER, OLD_SCRIPT_MARKER + addition, 1)
    return script


def patch_index_html(repo_root):
    index_path = os.path.join(repo_root, "index.html")
    with open(index_path, encoding="utf-8") as f:
        html = f.read()
    start = html.index("<script>") + len("<script>")
    end = html.index("</script>", start)
    old_script = html[start:end]
    new_script = build_new_script(old_script)
    if new_script is None:
        print("index.html already has the content-search patch — leaving it as is.")
        return False
    patched = html[:start] + new_script + html[end:]
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(patched)
    print("Patched index.html's inline script.")
    return True


def main():
    repo_root = sys.argv[1] if len(sys.argv) > 1 else "."
    repo_root = os.path.abspath(repo_root)
    patch_index_html(repo_root)
    index = build_index(repo_root)
    out_path = os.path.join(repo_root, "search-index.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, separators=(",", ":"))
    print(f"Wrote {out_path} ({os.path.getsize(out_path)} bytes).")


if __name__ == "__main__":
    main()
