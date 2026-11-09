"""Lesson audio maker for the ESOL library - made by Atin.

For every */audio/*/scripts.json in the repo:
  - makes an MP3 for each script that doesn't have one yet (Google Gemini speech)
  - writes index.html: one page with a player for each script

Run by .github/workflows/lesson-audio.yml. Needs the GEMINI_API_KEY secret.
To remake one script's audio, delete its MP3 and push.
"""
import base64, glob, html, json, os, subprocess, sys, tempfile
import urllib.request, urllib.error

MODEL = "gemini-3.8-flash-tts"
URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
DEFAULT_STYLE = ("clear British accent, natural classroom pace, just slightly slower "
                 "than normal conversation, short natural pause between turns")
KEY = os.environ.get("GEMINI_API_KEY", "").strip()
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def find_audio(o):
    if isinstance(o, dict):
        t = str(o.get("type", "")) + str(o.get("mime_type", "")) + str(o.get("mimeType", ""))
        if "audio" in t and isinstance(o.get("data"), str):
            return o["data"]
        for v in o.values():
            a = find_audio(v)
            if a:
                return a
    elif isinstance(o, list):
        for v in o:
            a = find_audio(v)
            if a:
                return a
    return None


def speak(lines, voices, style):
    names = sorted({s for s, _ in lines})
    if len(names) == 1:
        content = [{"type": "text", "text": " ".join(t for _, t in lines),
                    "annotations": [{"type": "speech_metadata", "style": style}]}]
        speech = [{"voice": voices[names[0]]}]
    else:
        content = [{"type": "text", "text": t,
                    "annotations": [{"type": "speech_metadata", "speaker": s, "style": style}]}
                   for s, t in lines]
        speech = {"speakers": [{"speaker": n, "voice": voices[n]} for n in names]}
    body = json.dumps({"model": MODEL, "input": [{"type": "user_input", "content": content}],
                       "response_format": {"type": "audio"},
                       "generation_config": {"speech_config": speech}}).encode()
    req = urllib.request.Request(URL, data=body, method="POST", headers={
        "x-goog-api-key": KEY, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            reply = json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{e.code} {e.read()[:600]!r}")
    a = find_audio(reply)
    if not a:
        raise RuntimeError("No audio in reply")
    return base64.b64decode(a)


def to_mp3(wav_bytes, mp3_path):
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(wav_bytes)
        tmp = f.name
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", tmp, "-ac", "1",
                    "-b:a", "96k", mp3_path], check=True)
    os.remove(tmp)


LOGO = open(os.path.join(ROOT, "tools", "logo-snippet.html"), encoding="utf-8").read()


def page(d, folder):
    title = html.escape(d["title"])
    data = json.dumps(d["scripts"], ensure_ascii=False).replace("</", "<\\/")
    plan = d.get("plan")
    plan_link = f'<a class="plan" href="{html.escape(plan)}">Lesson plan</a>' if plan else ""
    return f"""<!doctype html>
<html lang="en-GB"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
:root{{--ink:#1F2A37;--muted:#5B6776;--line:#D5DCE4;--card:#fff;--bg:#F3F5F8;--accent:#1F5FA8;--accent-ink:#fff;--soft:#E7EFF9}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font-family:Arial,Helvetica,sans-serif;font-size:18px;line-height:1.45}}
main{{max-width:900px;margin:0 auto;padding:20px 16px 110px}}
h1{{font-size:clamp(22px,3.4vw,32px);margin:4px 0 6px}}
.top{{display:flex;flex-wrap:wrap;gap:10px;align-items:center;color:var(--muted);font-size:16px;margin-bottom:18px}}
.plan{{color:var(--accent)}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin:0 0 14px}}
.card.playing{{border-color:var(--accent);box-shadow:0 0 0 3px var(--soft)}}
h2{{font-size:clamp(19px,2.6vw,24px);margin:0 0 12px}}
.row{{display:flex;flex-wrap:wrap;gap:10px}}
button{{font:inherit;font-size:18px;border-radius:10px;border:1px solid var(--line);background:#fff;color:var(--ink);padding:12px 18px;min-height:48px;cursor:pointer}}
button.main{{background:var(--accent);border-color:var(--accent);color:var(--accent-ink);font-weight:700}}
button:disabled{{opacity:.5;cursor:default}}
.status{{color:var(--muted);font-size:16px;margin-top:8px;min-height:1.4em}}
.box{{display:none;margin-top:12px;padding:12px 14px;background:var(--soft);border-radius:10px}}
.box.open{{display:block}}
.box p{{margin:4px 0}}
.who{{font-weight:700}}
.ans{{display:none;color:#0B6B3A;font-weight:700}}
.show-ans .ans{{display:inline}}
audio{{display:none}}
@media (max-width:520px){{button{{flex:1 1 calc(50% - 10px)}}}}
</style></head><body>
<main>
<h1>{title}</h1>
<div class="top"><span>Use “Play twice” to play a script, pause, then play it again.</span>{plan_link}</div>
<div id="list"></div>
</main>
<script>
const SCRIPTS = {data};
const list = document.getElementById('list');
let current = null;
function stopAll(){{ document.querySelectorAll('audio').forEach(a=>{{a.pause();a.currentTime=0;a.onended=null;}});
  document.querySelectorAll('.card').forEach(c=>c.classList.remove('playing'));
  document.querySelectorAll('.status').forEach(s=>s.textContent=s.dataset.base||''); clearTimeout(window._gap); }}
SCRIPTS.forEach(s=>{{
  const c=document.createElement('section'); c.className='card';
  const lines=s.lines.map(([w,t])=>`<p><span class="who">${{w}}:</span> ${{t}}</p>`).join('');
  const qs=(s.questions||[]).map(q=>{{const m=q.match(/^(.*?)\\s*\\((.*)\\)\\s*$/);
    return m?`<p>${{m[1]}} <span class="ans">→ ${{m[2]}}</span></p>`:`<p>${{q}}</p>`;}}).join('');
  c.innerHTML=`<h2>${{s.label}}</h2>
  <audio preload="none" src="${{s.id}}.mp3"></audio>
  <div class="row">
    <button class="main" data-act="once">▶ Play</button>
    <button data-act="twice">▶▶ Play twice</button>
    <button data-act="stop">■ Stop</button>
    <button data-act="script">Show script</button>
    ${{qs?'<button data-act="qs">Questions</button><button data-act="ans">Answers</button>':''}}
  </div>
  <div class="status"></div>
  <div class="box b-script">${{lines}}</div>
  ${{qs?`<div class="box b-qs">${{qs}}</div>`:''}}`;
  list.appendChild(c);
  const a=c.querySelector('audio'), st=c.querySelector('.status');
  a.addEventListener('error',()=>{{st.dataset.base='Audio not ready yet – it is made automatically a few minutes after upload.';st.textContent=st.dataset.base;}});
  function play(times){{ stopAll(); c.classList.add('playing'); let n=1;
    const go=()=>{{st.textContent=times>1?`Playing (${{n}} of ${{times}})…`:'Playing…'; a.currentTime=0; a.play().catch(()=>{{}});}};
    a.onended=()=>{{ if(n<times){{n++; st.textContent='Short pause…'; window._gap=setTimeout(go,3000);}} else {{c.classList.remove('playing'); st.textContent='Finished.';}} }};
    go(); }}
  c.addEventListener('click',e=>{{const b=e.target.closest('button'); if(!b) return;
    const act=b.dataset.act;
    if(act==='once') play(1); else if(act==='twice') play(2); else if(act==='stop') stopAll();
    else if(act==='script'){{const x=c.querySelector('.b-script'); x.classList.toggle('open'); b.textContent=x.classList.contains('open')?'Hide script':'Show script';}}
    else if(act==='qs'){{c.querySelector('.b-qs').classList.toggle('open');}}
    else if(act==='ans'){{const x=c.querySelector('.b-qs'); x.classList.add('open'); x.classList.toggle('show-ans');}}
  }});
}});
</script>
{LOGO}
</body></html>
"""


def main():
    jobs = sorted(glob.glob(os.path.join(ROOT, "**", "audio", "*", "scripts.json"), recursive=True))
    failed = False
    for job in jobs:
        folder = os.path.dirname(job)
        d = json.load(open(job, encoding="utf-8"))
        style = d.get("style", DEFAULT_STYLE)
        for s in d["scripts"]:
            mp3 = os.path.join(folder, s["id"] + ".mp3")
            if os.path.exists(mp3):
                continue
            if not KEY:
                print("No GEMINI_API_KEY - skipping audio for", mp3)
                continue
            print("Making", os.path.relpath(mp3, ROOT))
            try:
                to_mp3(speak(s["lines"], d["voices"], style), mp3)
            except Exception as e:
                print("  ERROR:", e)
                failed = True
        open(os.path.join(folder, "index.html"), "w", encoding="utf-8").write(page(d, folder))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
