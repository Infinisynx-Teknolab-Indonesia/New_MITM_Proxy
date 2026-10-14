"""Dashboard web buat lihat & edit flow yang ditahan proxy.

Buka http://127.0.0.1:8081 di browser. Butuh Flask: pip install flask
"""
from flask import Flask, request, jsonify, Response

import interceptor

app = Flask(__name__)

PAGE = r"""<!doctype html>
<html lang="id"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Proxy Intercept</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body { margin:0; font:14px/1.5 ui-monospace,Menlo,Consolas,monospace;
         background:#0f1115; color:#e6e6e6; }
  header { position:sticky; top:0; background:#161a22; padding:12px 16px;
           border-bottom:1px solid #2a2f3a; display:flex; gap:16px; align-items:center; flex-wrap:wrap; }
  header b { color:#7fd1ff; }
  .tgl { display:flex; gap:6px; align-items:center; }
  .wrap { padding:16px; max-width:900px; margin:0 auto; }
  .card { background:#161a22; border:1px solid #2a2f3a; border-radius:10px;
          padding:14px; margin-bottom:14px; }
  .req { border-left:4px solid #7fd1ff; }
  .res { border-left:4px solid #8ce99a; }
  .tag { font-size:11px; padding:2px 8px; border-radius:999px; background:#2a2f3a; }
  .row { display:flex; gap:8px; margin:6px 0; flex-wrap:wrap; }
  input, textarea { background:#0f1115; color:#e6e6e6; border:1px solid #2a2f3a;
                    border-radius:6px; padding:6px 8px; font:inherit; }
  input { flex:1; min-width:80px; }
  textarea { width:100%; resize:vertical; }
  label { font-size:11px; color:#9aa4b2; display:block; margin:8px 0 2px; }
  button { cursor:pointer; border:0; border-radius:6px; padding:8px 14px; font:inherit; font-weight:600; }
  .fwd { background:#2f7; color:#06260f; }
  .drop { background:#f66; color:#2a0606; }
  .ghost { background:#2a2f3a; color:#e6e6e6; }
  .empty { color:#6b7280; text-align:center; padding:40px 0; }
  .hist { font-size:12px; color:#9aa4b2; border-top:1px dashed #2a2f3a; margin-top:20px; padding-top:10px; }
  .hist div { padding:2px 0; }
  .hist .drop { color:#f66; } .hist .forward { color:#8ce99a; } .hist .pass { color:#6b7280; }
</style></head><body>
<header>
  <b>Proxy Intercept</b>
  <span class="tgl"><input type="checkbox" id="t-request" onchange="toggle('request',this.checked)"><label style="margin:0">Tahan request</label></span>
  <span class="tgl"><input type="checkbox" id="t-response" onchange="toggle('response',this.checked)"><label style="margin:0">Tahan response</label></span>
  <button class="ghost" onclick="resolveAll()">Forward semua</button>
  <span id="count" style="margin-left:auto;color:#9aa4b2"></span>
</header>
<div class="wrap">
  <div id="pending"></div>
  <div id="emptymsg" class="empty">Belum ada yang ditahan. Nyalakan toggle lalu buka situs/app kamu.</div>
  <div class="hist"><b>Riwayat</b><div id="history"></div></div>
</div>
<script>
const rendered = new Map();

function hdrToText(h){ return h.map(p => p[0]+": "+p[1]).join("\n"); }
function textToHdr(t){
  return t.split("\n").map(l=>l.trim()).filter(Boolean).map(l=>{
    const i=l.indexOf(":"); return i<0?[l,""]:[l.slice(0,i).trim(), l.slice(i+1).trim()];
  });
}

function buildCard(f){
  const c=document.createElement("div");
  c.className="card "+(f.kind==="request"?"req":"res");
  c.id="flow-"+f.id;
  let top;
  if(f.kind==="request"){
    top=`<div class="row">
      <input value="${f.method}" id="m-${f.id}" style="flex:0 0 90px">
      <input value="${f.host}" id="h-${f.id}">
      <input value="${f.port}" id="pt-${f.id}" style="flex:0 0 70px">
    </div>
    <label>Path</label><input value="${esc(f.path)}" id="pa-${f.id}" style="width:100%">`;
  } else {
    top=`<label>Status line</label><input value="${esc(f.status_line)}" id="sl-${f.id}" style="width:100%">`;
  }
  c.innerHTML=`<div class="row"><span class="tag">${f.kind.toUpperCase()} #${f.id}</span></div>
    ${top}
    <label>Headers</label><textarea rows="6" id="hd-${f.id}">${esc(hdrToText(f.headers))}</textarea>
    <label>Body ${f.body_editable?"":"(read-only)"}</label>
    <textarea rows="7" id="bd-${f.id}" ${f.body_editable?"":"disabled"}>${esc(f.body_text)}</textarea>
    <div class="row" style="margin-top:10px">
      <button class="fwd" onclick="send(${f.id},'forward','${f.kind}')">Forward</button>
      <button class="drop" onclick="send(${f.id},'drop','${f.kind}')">Drop</button>
    </div>`;
  return c;
}
function esc(s){ return (s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;"); }

async function send(id, action, kind){
  const body={id, action};
  if(action==="forward"){
    body.headers=textToHdr(document.getElementById("hd-"+id).value);
    body.body_text=document.getElementById("bd-"+id).value;
    if(kind==="request"){
      body.fields={method:document.getElementById("m-"+id).value,
                   host:document.getElementById("h-"+id).value,
                   port:document.getElementById("pt-"+id).value,
                   path:document.getElementById("pa-"+id).value};
    } else {
      body.fields={status_line:document.getElementById("sl-"+id).value};
    }
  }
  await fetch("/api/resolve",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
  const el=document.getElementById("flow-"+id); if(el) el.remove(); rendered.delete(id);
}
async function toggle(kind,val){ await fetch("/api/toggle",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({kind,enabled:val})}); }
async function resolveAll(){ await fetch("/api/resolve-all",{method:"POST"}); }

async function poll(){
  const s=await (await fetch("/api/state")).json();
  document.getElementById("t-request").checked=s.enabled.request;
  document.getElementById("t-response").checked=s.enabled.response;
  const box=document.getElementById("pending");
  const ids=new Set(s.pending.map(f=>f.id));
  for(const id of [...rendered.keys()]) if(!ids.has(id)){ const e=document.getElementById("flow-"+id); if(e)e.remove(); rendered.delete(id); }
  for(const f of s.pending) if(!rendered.has(f.id)){ box.appendChild(buildCard(f)); rendered.set(f.id,1); }
  document.getElementById("emptymsg").style.display=s.pending.length?"none":"block";
  document.getElementById("count").textContent=s.pending.length+" ditahan";
  document.getElementById("history").innerHTML=s.history.map(h=>
    `<div class="${h.action}">${h.action.toUpperCase()} · ${esc(h.summary)}</div>`).join("");
}
setInterval(poll, 1000); poll();
</script></body></html>"""


@app.get("/")
def index():
    return Response(PAGE, mimetype="text/html")


@app.get("/api/state")
def state():
    return jsonify(interceptor.snapshot())


@app.post("/api/toggle")
def toggle():
    d = request.get_json(force=True)
    interceptor.set_enabled(d["kind"], d["enabled"])
    return jsonify(ok=True)


@app.post("/api/resolve")
def resolve():
    d = request.get_json(force=True)
    interceptor.resolve(d["id"], d.get("action", "forward"),
                        fields=d.get("fields"), headers=d.get("headers"),
                        body_text=d.get("body_text"))
    return jsonify(ok=True)


@app.post("/api/resolve-all")
def resolve_all():
    interceptor.resolve_all()
    return jsonify(ok=True)


def run(host="127.0.0.1", port=8081):
    app.run(host=host, port=port, threaded=True)
