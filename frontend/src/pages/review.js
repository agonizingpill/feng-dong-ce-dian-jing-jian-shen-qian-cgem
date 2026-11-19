import {esc} from '../utils/format.js';
import {ZONES} from '../constants.js';
import {layout,probeCode,openSubstitution} from '../store.js';
import {layoutPicker,empty,badge,notify} from '../components/instruments.js';
import {send} from '../api.js';

const SUB_LABEL={proposed:'待签发',signed:'已签发',withdrawn:'已退回'};

function backupRow(s,l,b){
  return `<tr><td><b class="mono">${esc(b.probe_code)}</b> <small>${ZONES[b.zone]}</small></td>
  <td><span class="status ${b.signed?'signed':'ready'}">${b.signed?'随布置已签':'待随签'}</span></td>
  <td>${b.calibrated?'已标定':'<b>未标定</b>'}</td>
  <td>${b.enabled?'启用':'<b>已停用</b>'}</td>
  <td>${b.certificate_valid?'证书有效':'<b>无有效证书</b>'}</td>
  <td>${b.in_signed_substitution?'<b>已替换上车</b>':b.available?'可用':'不可用'}</td></tr>`;
}

function substitutionRow(s,l,x){
  return `<tr><td class="mono">#${x.id}</td><td>${esc(x.from_probe_code)} → <b>${esc(x.to_probe_code)}</b></td>
  <td class="mono">${x.holdout_mae_n} / ${x.error_limit_n} N</td>
  <td>${x.passed?'达标':'未达标'}</td>
  <td><span class="status ${x.state==='signed'?'signed':x.state==='withdrawn'?'invalidated':'ready'}">${SUB_LABEL[x.state]}</span><br><small>${esc(x.signed_by||x.created_by||'')}</small></td>
  <td>${x.state==='proposed'?`<button data-sub-sign="${x.id}" class="primary" ${s.user.role!=='admin'||!x.passed?'disabled':''}>签发替换</button> <button data-sub-withdraw="${x.id}" ${s.user.role!=='admin'?'disabled':''}>退回</button>`:x.state==='signed'?`<button data-sub-withdraw="${x.id}" ${s.user.role!=='admin'?'disabled':''}>退回原布置组合</button>`:'—'}</td></tr>`;
}

export function render(s){const l=layout(s),r=l?.evidence,open=openSubstitution(l);
  const replaceable=(l?.backups||[]).filter(b=>b.available);
  return `<div class="head"><div><div class="eyebrow">CHANNEL LAYOUT / 04</div><h1>三段覆盖，才可起试。</h1><p>测点数量、标定与翼段覆盖共同决定布置能否审签。备点随布置一同审签，开车前只可退回已签备点。</p></div><div class="selector">${layoutPicker(s)}</div></div>${l?`<div class="columns"><section class="section"><div class="sectionhead"><h2>${esc(l.code)} · 测点布置</h2>${badge(l)}</div><form id="selection-form">${Object.entries(ZONES).map(([k,v])=>`<div class="zonegroup"><h3>${v}<small>${l.probe_ids.filter(id=>s.probes.find(p=>p.id===id)?.zone===k).length} 点已选</small></h3><div class="checks">${s.probes.filter(p=>p.zone===k).map(p=>`<label class="check"><input type="checkbox" name="probe_id" value="${p.id}" ${l.probe_ids.includes(p.id)?'checked':''} ${l.status==='signed'?'disabled':''}><span><b class="mono">${esc(p.code)}</b><small>${p.calibrated?'已标定':'未标定'} / ${p.enabled?'启用':'停用'}</small></span></label>`).join('')}</div></div>`).join('')}<div class="actions"><button class="primary" ${s.user.role==='viewer'||['signed','calculating'].includes(l.status)?'disabled':''}>保存选点并回算误差</button><small id="chosen-count">已选 ${l.probe_ids.length} / ${l.max_channels} 通道</small></div></form><div class="metricstrip"><div>通道预算<b>${l.max_channels}</b></div><div>实际已选<b>${l.probe_ids.length}</b></div><div>留出 MAE<b>${r?.selected_mae_n??'—'} N</b></div></div><div class="noteblock">未标定或缺失任一翼段不能审签。超过通道预算的选择不会保存。签后来源和方案全部冻结；备点只在审签前登记，随审签固定。</div>

  <div class="sectionhead" style="margin-top:26px"><h2>审签备点</h2><span class="mono">SIGNED WITH LAYOUT</span></div>
  ${(l.backups||[]).length?`<div class="tablewrap"><table><thead><tr><th>备点</th><th>签署</th><th>标定</th><th>启用</th><th>校准</th><th>当前可用</th></tr></thead><tbody>${l.backups.map(b=>backupRow(s,l,b)).join('')}</tbody></table></div>`:empty(l.status==='signed'?'本布置审签时未备点，签后不能补登。':'审签前在右侧登记备点，随布置一并签署。')}
  ${l.status!=='signed'?`<form id="backup-form"><label>登记随签备点（可多选；不能与主测点重复，须已标定且启用）</label><div class="checks">${s.probes.filter(p=>!l.probe_ids.includes(p.id)).map(p=>`<label class="check"><input type="checkbox" name="backup_id" value="${p.id}" ${(l.backups||[]).some(b=>b.probe_id===p.id)?'checked':''} ${!p.enabled||!p.calibrated?'disabled':''}><span><b class="mono">${esc(p.code)}</b><small>${p.calibrated?'已标定':'未标定'} / ${p.enabled?'启用':'停用'}</small></span></label>`).join('')}</div><div class="actions"><button ${s.user.role==='viewer'||l.status==='calculating'?'disabled':''}>保存备点（随布置审签）</button></div></form>`:''}

  <div class="sectionhead" style="margin-top:26px"><h2>开车前主测点替换</h2><span class="mono">ONE POINT AT A TIME</span></div>
  ${l.status!=='signed'?empty('布置审签后才能在备点中退回一个主测点。'):open?`<p class="noteblock">当前已有${open.state==='signed'?'已签':'待签'}替换 ${esc(open.from_probe_code)} → ${esc(open.to_probe_code)}。同一时刻只换一个主点${open.state==='proposed'?'，需负责人签发达标记录':''}；要换另一个主点须先退回原组合。</p>`:replaceable.length?`<form id="substitution-form"><div class="formgrid"><div><label>被替换主测点</label><select name="from_probe_id">${l.probe_ids.map(id=>`<option value="${id}">${esc(probeCode(s,id))} / ${ZONES[s.probes.find(p=>p.id===id)?.zone]}</option>`).join('')}</select></div><div><label>退回备点（须同翼段、当前可用）</label><select name="to_probe_id">${replaceable.map(b=>`<option value="${b.probe_id}" data-zone="${b.zone}">${esc(b.probe_code)} / ${ZONES[b.zone]}</option>`).join('')}</select></div></div><div class="actions"><button class="primary" ${s.user.role==='viewer'?'disabled':''}>用原留出集验证并提交</button><small>通道数不变；替换组合在原训练集拟合，原留出集的 MAE 不得超过原组合的签发阈值。提交后由负责人签发。</small></div></form>`:empty('没有可用备点（须随布置已签、已标定、启用且当前证书有效）。')}
  ${(l.substitutions||[]).length?`<div class="tablewrap" style="margin-top:14px"><table><thead><tr><th>#</th><th>替换</th><th>留出/阈值 N</th><th>判定</th><th>状态 / 签发人</th><th>操作</th></tr></thead><tbody>${l.substitutions.map(x=>substitutionRow(s,l,x)).join('')}</tbody></table></div>`:''}

  ${l.effective_probe_ids&&l.effective_probe_ids.join()!==l.probe_ids.join()?`<div class="metricstrip"><div>原审签组合<b>${l.probe_ids.map(id=>esc(probeCode(s,id))).join(' / ')}</b></div><div>当前开车组合<b>${l.effective_probe_ids.map(id=>esc(probeCode(s,id))).join(' / ')}</b></div></div>`:''}
  </section><aside class="section"><h2>审签检查</h2>${Object.entries(ZONES).map(([k,v])=>`<div class="checksdetail"><span>${v}覆盖</span><b>${l.probe_ids.some(id=>s.probes.find(p=>p.id===id)?.zone===k)?'已覆盖':'缺失'}</b></div>`).join('')}<div class="checksdetail"><span>全部已标定</span><b>${l.probe_ids.every(id=>s.probes.find(p=>p.id===id)?.calibrated)?'通过':'待标定'}</b></div><div class="checksdetail"><span>通道预算</span><b>${l.probe_ids.length<=l.max_channels?'符合':'超额'}</b></div><div class="actions"><button id="sign-layout" class="primary" ${s.user.role!=='admin'||l.status!=='ready'?'disabled':''}>${l.status==='signed'?'布置已审签':'负责人审签（含备点）'}</button></div><p class="muted" style="margin-top:22px">${l.signed_by?'审签人 '+esc(l.signed_by):'工程师完成选点与备点，试验负责人最终审签。所有条件在后端再次核查。'}</p>${l.source_checksum?`<p class="muted">来源校验<br><span class="mono">${esc(l.source_checksum.slice(0,24))}…</span></p>`:''}<p class="muted">替换只临时代替一个主点，不改原审签布置与来源；退回后备点恢复可用。</p></aside></div>`:empty('尚无布置方案。请先到互信息排序页设定通道预算，生成精简布置。')}`}

export function bind(s,reload){
  document.querySelector('#layout-picker').onchange=async e=>{s.layoutId=Number(e.target.value);await reload()};
  const l=layout(s);if(!l)return;
  const f=document.querySelector('#selection-form');
  f.onchange=()=>document.querySelector('#chosen-count').textContent=`已选 ${f.querySelectorAll('[name=probe_id]:checked').length} / ${l.max_channels} 通道`;
  f.onsubmit=async ev=>{ev.preventDefault();const probe_ids=[...new FormData(f).getAll('probe_id')].map(Number);try{await send('/layouts/'+l.id+'/probes',{probe_ids},'PUT');notify('选点已保存，正在重新核算精简误差');await reload()}catch(x){notify(x.message)}};
  const bf=document.querySelector('#backup-form');
  if(bf)bf.onsubmit=async ev=>{ev.preventDefault();const probe_ids=[...new FormData(bf).getAll('backup_id')].map(Number);try{await send('/layouts/'+l.id+'/backups',{probe_ids},'PUT');notify('备点已登记，审签时一并签署');await reload()}catch(x){notify(x.message)}};
  const sf=document.querySelector('#substitution-form');
  if(sf)sf.onsubmit=async ev=>{ev.preventDefault();const d=Object.fromEntries(new FormData(sf));d.from_probe_id=Number(d.from_probe_id);d.to_probe_id=Number(d.to_probe_id);try{const x=await send('/layouts/'+l.id+'/substitutions',d);notify(`替换验证完成：留出 MAE ${x.holdout_mae_n} / 阈值 ${x.error_limit_n} N，${x.passed?'达标，待负责人签发':'未达标，不能签发'}`);await reload()}catch(x){notify(x.message)}};
  document.querySelectorAll('[data-sub-sign]').forEach(b=>b.onclick=async()=>{try{await send('/layout-substitutions/'+b.dataset.subSign+'/sign');notify('替换已签发，开车将按当前组合核对');await reload()}catch(x){notify(x.message)}});
  document.querySelectorAll('[data-sub-withdraw]').forEach(b=>b.onclick=async()=>{try{await send('/layout-substitutions/'+b.dataset.subWithdraw+'/withdraw');notify('已退回原布置组合');await reload()}catch(x){notify(x.message)}});
  document.querySelector('#sign-layout').onclick=async()=>{try{await send('/layouts/'+l.id+'/sign');notify('布置与备点已审签，来源与方案冻结');await reload()}catch(x){notify(x.message)}}
}
