"""Build a local interactive, post-episode replay from actual sensor/event logs."""
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("run")
args = parser.parse_args()
run = Path(args.run)
events = [json.loads(line) for line in (run/"trace.jsonl").read_text().splitlines()]
result = json.loads((run/"result.json").read_text())
result.pop("capabilities", None)
frames = []
for event in events:
    if event["kind"] == "OBSERVATION":
        obs_id = event["payload"]["obs_id"]
        sequence = int(obs_id.rsplit(":", 1)[1])
        raw = f"frame_{sequence:04}.png"
        annotated = f"candidates_{sequence:04}.png"
        frames.append({"obs_id": obs_id, "sequence": sequence, "time": event["elapsed_s"],
                       "raw": raw, "annotated": annotated if (run/annotated).exists() else raw})
data = {"events": events, "frames": frames, "result": result}
encoded = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
template = '''<!doctype html>
<html lang="zh"><meta charset="utf-8"><title>NavCode · Episode Replay</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#0e1520;color:#e4eaf2;font:15px system-ui,sans-serif}
main{max-width:1400px;margin:auto;padding:24px}h1{font-size:25px;margin:0 0 8px}h2{font-size:17px;margin:0 0 12px}
.muted{color:#99aac0;font-size:13px}.bar{display:flex;align-items:center;gap:16px;flex-wrap:wrap;margin:20px 0}
.chip{background:#1d3042;padding:8px 12px;border-radius:8px}.grid{display:grid;grid-template-columns:minmax(350px,1.05fr) minmax(360px,1fr);gap:20px}
.card{padding:20px;border:1px solid #2a3a4e;background:#151f2e;border-radius:12px;margin-bottom:18px}
#scene{width:100%;max-height:560px;object-fit:contain;background:#080e16;border-radius:8px;image-rendering:auto}
input[type=range]{width:100%}button,select{background:#263a50;border:1px solid #46617c;border-radius:7px;color:#edf4fb;padding:8px 12px;cursor:pointer}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.55 ui-monospace,monospace;margin:0}#code{max-height:430px;overflow:auto}
#evidence{display:flex;gap:10px;overflow:auto}#evidence img{width:120px;border-radius:6px;cursor:pointer}
.event{border-top:1px solid #2a3a4e;padding:10px 0}.kind{font:12px ui-monospace,monospace;color:#80c9ef}
#events{max-height:300px;overflow:auto}.question{color:#a5dce7;line-height:1.5}.warning{color:#f2c87d}
@media(max-width:850px){.grid{grid-template-columns:1fr}main{padding:12px}}
</style><main><h1>NavCode · Episode Replay</h1>
<div class="muted">真实传感器与事件的离线回放 · 不向在线 Agent 提供评测指标 · 地面标记不是目标或可达性保证</div>
<div class="bar" id="metrics"></div><div class="card" id="instruction"></div>
<div class="grid"><section><div class="card"><h2>观察与执行</h2><img id="scene" alt="episode RGB">
<div class="bar"><button id="prev">←</button><button id="play">播放</button><button id="next">→</button>
<select id="mode"><option value="annotated">地面候选标记</option><option value="raw">原始 RGB</option></select><span id="position" class="muted"></span></div>
<input id="slider" type="range" min="0" value="0"><div id="motion" class="muted"></div></div>
<div class="card"><h2>当时的视觉问题与证据</h2><p id="question" class="question"></p><pre id="report"></pre><div class="bar" id="evidence"></div></div>
</section><section><div class="card"><h2 id="codeTitle">Python Policy</h2><pre id="code"></pre></div>
<div class="card"><h2>事件账本</h2><div id="events"></div></div></section></div>
<div class="card"><h2>终止结果</h2><pre id="result"></pre></div></main>
<script type="application/json" id="data">__DATA__</script><script>
const D=JSON.parse(document.getElementById('data').textContent), $=id=>document.getElementById(id);
const slider=$('slider');slider.max=D.frames.length-1;let timer=null;
const instruction=D.events.find(e=>e.kind==='EPISODE_START');$('instruction').textContent=instruction?.payload.instruction||'';
const m=D.result.metrics||{};
for(const s of [`${D.result.suite} · episode ${D.result.episode_id}`,`Agent success: ${D.result.agent_success??!D.result.forced_stop&&!!m.success}`,`SPL: ${(m.spl??0).toFixed(3)}`,`nDTW: ${(m.ndtw??0).toFixed(3)}`,`Path: ${(m.path_length??0).toFixed(2)} m`]){
 const el=document.createElement('span');el.className='chip';el.textContent=s;$('metrics').append(el);
}
$('result').textContent=JSON.stringify(D.result,null,2);
function show(){
 const i=Number(slider.value), f=D.frames[i], next=D.frames[i+1];
 $('scene').src=f[$('mode').value];$('position').textContent=`${i+1}/${D.frames.length} · action ${f.sequence} · ${f.time.toFixed(1)}s`;
 const until=next?next.time:Infinity, subset=D.events.filter(e=>e.elapsed_s<until);
 const latest=kind=>[...subset].reverse().find(e=>e.kind===kind);
 const policy=latest('POLICY_SUBMITTED');$('codeTitle').textContent=`Python Policy · revision ${policy?.payload.revision??0}`;
 $('code').textContent=policy?.payload.source||'Code Agent 尚未提交程序';
 const contract=latest('PERCEPTION_REQUESTED'), report=latest('EVIDENCE_APPLIED')||latest('PERCEPTION_RESOLVED');
 $('question').textContent=contract?`${contract.payload.stage_id}: ${contract.payload.predicate}`:'';
 $('report').textContent=report?JSON.stringify(report.payload,null,2):'暂无视觉报告';
 $('evidence').replaceChildren();
 for(const id of report?.payload.evidence_obs_ids||[]){const index=D.frames.findIndex(x=>x.obs_id===id);if(index<0)continue;
  const wrap=document.createElement('div'), img=document.createElement('img'), label=document.createElement('div');
  img.src=D.frames[index].raw;img.alt=id;img.onclick=()=>{slider.value=index;show()};label.className='muted';label.textContent=`frame ${D.frames[index].sequence}`;
  wrap.append(img,label);$('evidence').append(wrap);
 }
 const action=latest('ACTION_COMMITTED');$('motion').textContent=action?`已提交: ${action.payload.action} · op_id ${action.payload.op_id}`:'初始观察';
 $('events').replaceChildren();
 for(const event of subset.filter(e=>!['OBSERVATION','GROUND_CANDIDATES','POLICY_SUBMITTED'].includes(e.kind)).slice(-12).reverse()){
  const div=document.createElement('div'),kind=document.createElement('div'),payload=document.createElement('pre');
  div.className='event';kind.className='kind';kind.textContent=`${event.elapsed_s.toFixed(1)}s · ${event.kind}`;payload.textContent=JSON.stringify(event.payload,null,1);
  div.append(kind,payload);$('events').append(div);
 }
}
function step(delta){slider.value=Math.max(0,Math.min(D.frames.length-1,Number(slider.value)+delta));show()}
$('prev').onclick=()=>step(-1);$('next').onclick=()=>step(1);slider.oninput=show;$('mode').onchange=show;
$('play').onclick=()=>{if(timer){clearInterval(timer);timer=null;$('play').textContent='播放'}else{timer=setInterval(()=>{if(Number(slider.value)>=D.frames.length-1){clearInterval(timer);timer=null;$('play').textContent='播放'}else step(1)},700);$('play').textContent='暂停'}};
show();</script></html>'''
# Parentheses are required when mixing ?? and && in JavaScript.
template = template.replace('D.result.agent_success??!D.result.forced_stop&&!!m.success',
                            'D.result.agent_success??(!D.result.forced_stop&&!!m.success)')
(run/"replay.html").write_text(template.replace("__DATA__", encoded))
print(run/"replay.html")
