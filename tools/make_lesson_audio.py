"""Lesson audio maker for the ESOL library - made by Atin.

For every */audio/*/scripts.json in the repo:
  - makes an MP3 for each script that doesn't have one yet
    Voices: Google Gemini (if the key works) -> Microsoft Edge voices -> Piper (always free)
    Scripts made by a fallback are remade with Gemini when Gemini works again.
  - writes index.html: one page with a player for each script

Run by .github/workflows/lesson-audio.yml. Needs the GEMINI_API_KEY secret.
To remake one script's audio, delete its MP3 and push.
"""
import base64, glob, html, json, os, subprocess, sys, tempfile
import urllib.request, urllib.error

MODELS = ["gemini-3.8-flash-tts", "gemini-3.1-flash-tts-preview"]  # second has its own free quota
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
    err = None
    for model in MODELS:
        try:
            return _speak(model, content, speech)
        except RuntimeError as e:
            err = e
            print(f"  {model}: {str(e)[:200]}")
    raise err


def _speak(model, content, speech):
    body = json.dumps({"model": model, "input": [{"type": "user_input", "content": content}],
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


FEMALE = {"kore", "aoede", "leda", "zephyr", "callirrhoe", "despina", "erinome", "laomedeia",
          "achernar", "gacrux", "pulcherrima", "vindemiatrix", "sulafat", "autonoe"}
EDGE = {"f": "en-GB-SoniaNeural", "m": "en-GB-RyanNeural"}
PIPER = {"f": "en_GB-jenny_dioco-medium", "m": "en_GB-alan-medium"}
PIPER_DIR = os.path.join(tempfile.gettempdir(), "piper-voices")


def gender(d, name):
    g = d.get("genders", {}).get(name)
    if g:
        return g[0].lower()
    return "f" if d["voices"][name].lower() in FEMALE else "m"


def run(cmd, **kw):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, **kw)


def join(parts, wav_out, gap=0.7):
    """Join line recordings into one WAV with a short pause between turns."""
    tmp = tempfile.mkdtemp()
    norm = []
    for i, p in enumerate(parts):
        n = os.path.join(tmp, f"{i}.wav")
        run(["ffmpeg", "-y", "-i", p, "-ar", "24000", "-ac", "1", n])
        norm.append(n)
    sil = os.path.join(tmp, "sil.wav")
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", str(gap), sil])
    lst = os.path.join(tmp, "list.txt")
    with open(lst, "w") as f:
        for i, n in enumerate(norm):
            if i:
                f.write(f"file '{sil}'\n")
            f.write(f"file '{n}'\n")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, wav_out])


def speak_edge(lines, d):
    tmp = tempfile.mkdtemp()
    parts = []
    for i, (who, text) in enumerate(lines):
        out = os.path.join(tmp, f"{i}.mp3")
        run(["edge-tts", "--voice", EDGE[gender(d, who)], "--rate=-8%", "--text", text,
             "--write-media", out], timeout=120)
        parts.append(out)
    wav = os.path.join(tmp, "all.wav")
    join(parts, wav)
    return open(wav, "rb").read()


def speak_piper(lines, d):
    tmp = tempfile.mkdtemp()
    os.makedirs(PIPER_DIR, exist_ok=True)
    parts = []
    for i, (who, text) in enumerate(lines):
        voice = PIPER[gender(d, who)]
        model = os.path.join(PIPER_DIR, voice + ".onnx")
        if not os.path.exists(model):
            run([sys.executable, "-m", "piper.download_voices", "--download-dir", PIPER_DIR, voice])
        out = os.path.join(tmp, f"{i}.wav")
        run([sys.executable, "-m", "piper", "-m", model, "-f", out, "--length-scale", "1.1"],
            input=text.encode())
        parts.append(out)
    wav = os.path.join(tmp, "all.wav")
    join(parts, wav)
    return open(wav, "rb").read()


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
<div class="top"><span>Use “Play twice” to play a script, pause, then play it again. Press ▶ Play again to pause; press it again to carry on.</span>{plan_link}</div>
<div id="list"></div>
</main>
<script>
const SCRIPTS = {data};
const list = document.getElementById('list');
let current = null;
function stopAll(){{ document.querySelectorAll('audio').forEach(a=>{{a.pause();a.currentTime=0;a.onended=null;}});
  document.querySelectorAll('.card').forEach(c=>c.classList.remove('playing'));
  document.querySelectorAll('.status').forEach(s=>s.textContent=s.dataset.base||''); clearTimeout(window._gap);
  document.querySelectorAll('[data-act="once"]').forEach(b=>{{b.textContent='▶ Play';}});
  document.querySelectorAll('.card').forEach(c=>{{c._paused=false;c._resume=null;c._gapWaiting=false;}}); }}
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
  const pb=c.querySelector('[data-act="once"]');
  function play(times){{ stopAll(); c.classList.add('playing'); pb.textContent='⏸ Pause'; let n=1;
    const go=()=>{{c._gapWaiting=false; st.textContent=times>1?`Playing (${{n}} of ${{times}})…`:'Playing…'; a.currentTime=0; a.play().catch(()=>{{}});}};
    a.onended=()=>{{ if(n<times){{n++; st.textContent='Short pause…'; c._gapWaiting=true; window._gap=setTimeout(go,3000);}} else {{c.classList.remove('playing'); pb.textContent='▶ Play'; st.textContent='Finished.';}} }};
    c._go=go; go(); }}
  function togglePause(){{ if(!c.classList.contains('playing')) return;
    if(!c._paused){{ c._paused=true; pb.textContent='▶ Resume'; c._st=st.textContent;
      if(c._gapWaiting){{ clearTimeout(window._gap); c._resume=c._go; }} else {{ a.pause(); c._resume=()=>{{a.play().catch(()=>{{}});}}; }}
      st.textContent='Paused.'; }}
    else {{ c._paused=false; pb.textContent='⏸ Pause'; st.textContent=c._st||''; const r=c._resume; c._resume=null; if(r) r(); }} }}
  c.addEventListener('click',e=>{{const b=e.target.closest('button'); if(!b) return;
    const act=b.dataset.act;
    if(act==='once'){{ if(c.classList.contains('playing')) togglePause(); else play(1); }} else if(act==='twice') play(2); else if(act==='stop') stopAll();
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
        rec_path = os.path.join(folder, "engines.json")
        rec = json.load(open(rec_path)) if os.path.exists(rec_path) else {}
        for s in d["scripts"]:
            mp3 = os.path.join(folder, s["id"] + ".mp3")
            have = os.path.exists(mp3)
            made_by = rec.get(s["id"], "gemini" if have else None)
            if have and (made_by == "gemini" or not KEY):
                continue
            rel = os.path.relpath(mp3, ROOT)
            engines = [("gemini", lambda: speak(s["lines"], d["voices"], style))] if KEY else []
            if not have:
                engines += [("edge", lambda: speak_edge(s["lines"], d)),
                            ("piper", lambda: speak_piper(s["lines"], d))]
            for name, fn in engines:
                try:
                    to_mp3(fn(), mp3)
                    rec[s["id"]] = name
                    print(f"Made {rel} with {name}")
                    break
                except Exception as e:
                    err = getattr(e, "stderr", b"") or b""
                    print(f"  {name} failed for {rel}: {str(e)[:300]} {err[-300:]!r}")
            else:
                if not have:
                    failed = True
        json.dump(rec, open(rec_path, "w"), indent=1)
        open(os.path.join(folder, "index.html"), "w", encoding="utf-8").write(page(d, folder))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
