from datetime import datetime,timezone

from fastapi import HTTPException
from sqlalchemy import select,delete

from .models import Layout,Probe,Sweep,Pressure
from .backup_models import LayoutBackup,LayoutSubstitution
from .calibration_service import locked
from .constants import SUBSTITUTION_ERROR_FACTOR,SUBSTITUTION_TRAIN_MIN
from .services import pack,selected,audit


def signed_layout(s,id):
    l=locked(s,Layout,id)
    if l.status!='signed':raise HTTPException(409,'只有已审签布置才能登记备点或替换主测点')
    return l


def _sub_query(layout_id,state,lock):
    q=select(LayoutSubstitution).where(LayoutSubstitution.layout_id==layout_id,LayoutSubstitution.state==state).order_by(LayoutSubstitution.id.desc())
    return q.with_for_update() if lock else q


def active_substitution(s,layout_id,lock=False):
    """当前生效的已签替换，最多一个。"""
    return s.scalar(_sub_query(layout_id,'signed',lock))


def open_substitution(s,layout_id,exclude_id=None,lock=True):
    """待签或已签的替换都占用“同一时刻只换一个主点”的名额。"""
    q=select(LayoutSubstitution).where(LayoutSubstitution.layout_id==layout_id,LayoutSubstitution.state.in_(('proposed','signed')))
    if exclude_id is not None:q=q.where(LayoutSubstitution.id!=exclude_id)
    return s.scalar((q.order_by(LayoutSubstitution.id.desc()).with_for_update())if lock else q.order_by(LayoutSubstitution.id.desc()))


def effective_ids(s,layout_id,lock=False,strict=True):
    ids=selected(s,layout_id);sub=active_substitution(s,layout_id,lock)
    if sub:
        if sub.from_probe_id not in ids or sub.to_probe_id in ids:
            if strict:raise HTTPException(409,'已签替换与布置测点不一致，不能开车')
            return ids,None
        ids=[sub.to_probe_id if i==sub.from_probe_id else i for i in ids]
    return ids,sub


def layout_backups(s,layout_id,lock=False):
    q=select(LayoutBackup).where(LayoutBackup.layout_id==layout_id).order_by(LayoutBackup.probe_id)
    return list(s.scalars(q.with_for_update() if lock else q))


def certificate_valid(s,probe):
    """只读判断：页面展示与备点可用性用，不取得证书行锁。"""
    from .calibration_models import CalibrationCertificate
    from .calibration_service import validate
    x=s.scalar(select(CalibrationCertificate).where(CalibrationCertificate.probe_id==probe.id,CalibrationCertificate.state=='issued')
               .order_by(CalibrationCertificate.issued_at.desc(),CalibrationCertificate.id.desc()))
    if not x:return False
    try:validate(x);return True
    except HTTPException:return False


def backup_views(s,layout_id):
    primaries=set(selected(s,layout_id));sub=active_substitution(s,layout_id)
    out=[]
    for b in layout_backups(s,layout_id):
        p=s.get(Probe,b.probe_id);ok=certificate_valid(s,p)
        used=bool(sub and sub.to_probe_id==b.probe_id)
        out.append(pack(b)|{'probe_code':p.code,'zone':p.zone,'calibrated':p.calibrated,'enabled':p.enabled,'certificate_valid':ok,
                            'is_primary':p.id in primaries,'in_signed_substitution':used,
                            'available':b.signed and p.enabled and p.calibrated and ok and p.id not in primaries and not used})
    return out


def register(s,layout_id,probe_ids,u):
    l=locked(s,Layout,layout_id)
    if l.status=='calculating':raise HTTPException(409,'贡献计算进行中，暂不能登记备点')
    if l.status=='signed':raise HTTPException(409,'布置已审签，备点须随审签登记，签后不能补登')
    primaries=set(selected(s,l.id));probes=[locked(s,Probe,i) for i in probe_ids]
    if any(p.id in primaries for p in probes):raise HTTPException(409,'主测点不能同时登记为备点')
    if any(not p.enabled or not p.calibrated for p in probes):raise HTTPException(409,'备点须为已标定且启用的测点')
    s.execute(delete(LayoutBackup).where(LayoutBackup.layout_id==l.id))
    for p in probes:s.add(LayoutBackup(layout_id=l.id,probe_id=p.id,signed=False))
    s.flush();audit(s,u,'登记布置备点 '+l.code);return backup_views(s,l.id)


def sign_backups(s,l):
    """审签布置时一并签署备点；签后不可补登或改写。"""
    primaries=set(selected(s,l.id));rows=layout_backups(s,l.id,lock=True)
    for b in rows:
        p=locked(s,Probe,b.probe_id)
        if p.id in primaries:raise HTTPException(409,f'备点{p.code}已被选为主通道，请重新登记备点')
        if not p.enabled or not p.calibrated:raise HTTPException(409,f'备点{p.code}未标定或已停用，不能随布置审签')
        b.signed=True


def _matrix(s,probe_ids,sweep_codes):
    rows=s.execute(select(Sweep.code,Sweep.lift,Pressure.probe_id,Pressure.pascal)
                   .join(Pressure,Pressure.sweep_id==Sweep.id)
                   .where(Sweep.code.in_(sweep_codes),Pressure.probe_id.in_(probe_ids))).all()
    lift={code:y for code,y,_,_ in rows};values={(code,pid):v for code,_,pid,v in rows}
    missing=[c for c in sweep_codes if c not in lift]
    if missing:raise HTTPException(409,'原留出记录缺少升力，不能验证替换组合')
    x=[];y=[]
    for code in sweep_codes:
        row=[]
        for pid in probe_ids:
            if (code,pid) not in values:raise HTTPException(409,'原训练或留出集缺少替换组合的压力记录，不能验证')
            row.append(values[(code,pid)])
        x.append(row);y.append(lift[code])
    return x,y


def holdout_mae(s,probe_ids,train_codes,holdout_codes):
    """只在原布置的训练记录上拟合，原留出记录只用于评估；不做新拆分。"""
    import numpy as np
    from sklearn.linear_model import Ridge
    from sklearn.metrics import mean_absolute_error
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    xt,yt=_matrix(s,probe_ids,train_codes);xh,yh=_matrix(s,probe_ids,holdout_codes)
    model=make_pipeline(StandardScaler(),Ridge(alpha=1.0));model.fit(np.array(xt),np.array(yt))
    return float(mean_absolute_error(np.array(yh),model.predict(np.array(xh))))


def original_holdout(l):
    e=l.evidence or {}
    train=e.get('train_sweep_codes')or[];holdout=e.get('holdout_sweep_codes')or[]
    if len(train)<SUBSTITUTION_TRAIN_MIN or not holdout:raise HTTPException(409,'原布置缺少训练/留出集证据，不能验证替换组合')
    return train,holdout


def evaluate(s,layout,combination):
    train,holdout=original_holdout(layout)
    base=holdout_mae(s,selected(s,layout.id),train,holdout)
    replacement=holdout_mae(s,combination,train,holdout)
    limit=base*SUBSTITUTION_ERROR_FACTOR
    passed=replacement<=limit+1e-9
    return {'base_holdout_mae_n':round(base,6),'replacement_holdout_mae_n':round(replacement,6),
            'error_factor':SUBSTITUTION_ERROR_FACTOR,'error_limit_n':round(limit,6),
            'passed':passed,'train_sweep_codes':train,'holdout_sweep_codes':holdout,'seed':(layout.evidence or {}).get('seed')}


def combination(s,layout_id,from_probe_id,to_probe_id):
    ids=selected(s,layout_id)
    if from_probe_id not in ids:raise HTTPException(409,'被替换测点不在已签布置中')
    if to_probe_id in ids:raise HTTPException(409,'替换测点已在已签布置中，通道数不能增加')
    if len(ids)>s.get(Layout,layout_id).max_channels:raise HTTPException(409,'原布置已超通道预算')
    return [to_probe_id if i==from_probe_id else i for i in ids]


def propose(s,layout_id,d,u):
    l=signed_layout(s,layout_id)
    if open_substitution(s,l.id):raise HTTPException(409,'同一时刻只允许一个替换，请先退回原组合')
    combination(s,l.id,d.from_probe_id,d.to_probe_id)
    backup=next((b for b in layout_backups(s,l.id) if b.probe_id==d.to_probe_id),None)
    if not backup or not backup.signed:raise HTTPException(409,'替换测点必须是随布置审签的备点')
    target=locked(s,Probe,d.to_probe_id)
    if not target.enabled:raise HTTPException(409,f'{target.code}已经停用，不能作为替换备点')
    if not target.calibrated:raise HTTPException(409,f'{target.code}尚未标定，不能替换主测点')
    if not certificate_valid(s,target):raise HTTPException(409,f'{target.code}缺少当前有效校准证书，不能替换主测点')
    comb=combination(s,l.id,d.from_probe_id,d.to_probe_id)
    if {s.get(Probe,i).zone for i in comb}!={'root','mid','tip'}:raise HTTPException(409,'替换后仍须覆盖翼根、翼中、翼尖')
    report=evaluate(s,l,comb)
    now=datetime.now(timezone.utc).isoformat()
    source=s.get(Probe,d.from_probe_id)
    x=LayoutSubstitution(layout_id=l.id,from_probe_id=source.id,to_probe_id=target.id,state='proposed',
                         train_rows=len(report['train_sweep_codes']),holdout_rows=len(report['holdout_sweep_codes']),
                         holdout_mae_n=report['replacement_holdout_mae_n'],error_limit_n=report['error_limit_n'],
                         passed=report['passed'],created_by=u.email,created_at=now,
                         evidence=report|{'from_probe_code':source.code,'to_probe_code':target.code,
                                          'combination_probe_ids':comb,'combination_probe_codes':[s.get(Probe,i).code for i in comb],
                                          'base_probe_ids':selected(s,l.id)})
    s.add(x);s.flush();audit(s,u,f'提交主测点替换 {source.code}→{target.code}（{"达标" if x.passed else "未达标"}）');return view(s,x)


def view(s,x):
    return pack(x)|{'from_probe_code':(x.evidence or {}).get('from_probe_code')or s.get(Probe,x.from_probe_id).code,
                    'to_probe_code':(x.evidence or {}).get('to_probe_code')or s.get(Probe,x.to_probe_id).code,
                    'layout_code':s.get(Layout,x.layout_id).code}


def sign(s,id,u):
    preview=s.get(LayoutSubstitution,id)
    if not preview:raise HTTPException(404,'替换记录不存在')
    layout=locked(s,Layout,preview.layout_id)
    x=locked(s,LayoutSubstitution,id)
    if x.state!='proposed':raise HTTPException(409,'只有待签替换可以签发，已签或已退回不能重复签署')
    if layout.status!='signed':raise HTTPException(409,'原布置未处于已审签状态，不能签发替换')
    if open_substitution(s,layout.id,exclude_id=x.id):raise HTTPException(409,'同一时刻只允许一个替换，请先退回原组合')
    comb=combination(s,layout.id,x.from_probe_id,x.to_probe_id)
    target=locked(s,Probe,x.to_probe_id)
    backup=next((b for b in layout_backups(s,layout.id) if b.probe_id==x.to_probe_id),None)
    if not backup or not backup.signed:raise HTTPException(409,'替换测点不再是已签备点')
    if not target.enabled or not target.calibrated:raise HTTPException(409,f'{target.code}未启用或未标定，不能签发替换')
    if not certificate_valid(s,target):raise HTTPException(409,f'{target.code}缺少当前有效校准证书，不能签发替换')
    proposal=evaluate(s,layout,comb)
    if not proposal['passed']:raise HTTPException(409,'替换组合用原留出集复核未达标，不能审签')
    evidence=dict(x.evidence or {})
    if not evidence.get('from_probe_code'):evidence['from_probe_code']=s.get(Probe,x.from_probe_id).code
    evidence.update(proposal)
    evidence.update({'to_probe_code':target.code,'combination_probe_ids':comb,
                     'combination_probe_codes':[s.get(Probe,i).code for i in comb]})
    x.holdout_mae_n=proposal['replacement_holdout_mae_n'];x.error_limit_n=proposal['error_limit_n']
    x.train_rows=len(proposal['train_sweep_codes']);x.holdout_rows=len(proposal['holdout_sweep_codes'])
    x.passed=True;x.evidence=evidence
    x.state='signed';x.signed_by=u.email;x.signed_at=datetime.now(timezone.utc).isoformat()
    audit(s,u,f'负责人签发主测点替换 {x.evidence["from_probe_code"]}→{target.code}');return view(s,x)


def withdraw(s,id,u):
    preview=s.get(LayoutSubstitution,id)
    if not preview:raise HTTPException(404,'替换记录不存在')
    locked(s,Layout,preview.layout_id);x=locked(s,LayoutSubstitution,id)
    if x.state=='withdrawn':raise HTTPException(409,'替换已经退回原组合，不能重复退回')
    if x.state=='signed':x.note=(x.note+'\n' if x.note else '')+'退回原组合 '+datetime.now(timezone.utc).isoformat()+' / '+u.email
    x.state='withdrawn';audit(s,u,'退回原布置组合 '+str(x.id));return view(s,x)


def layout_decorations(s,l):
    subs=list(s.scalars(select(LayoutSubstitution).where(LayoutSubstitution.layout_id==l.id).order_by(LayoutSubstitution.id.desc())))
    ids,sub=effective_ids(s,l.id,strict=False)
    return {'backups':backup_views(s,l.id),'substitutions':[view(s,x) for x in subs],
            'effective_probe_ids':ids,'active_substitution':view(s,sub) if sub else None}
