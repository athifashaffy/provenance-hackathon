"""Full calibration sweep for the statistical-outlier thresholds.

Grids (RATE_Z, HOURS_Z), reimports verify.py for each setting, scores the WHOLE
corpus with the official harness formula, and reports overall score + the F1
breakdown (hard / t4 / clean over-flagging). The corpus IS the official
generator's output, so its clean-vs-t4 trade-off is the real held-out predictor.

Usage:
  python analysis/calibrate.py            # full grid
  python analysis/calibrate.py 3.7 3.0    # evaluate one (RATE_Z, HOURS_Z)
"""
import json, os, sys, importlib, statistics
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "backend"))
CORPUS = os.path.join(ROOT, "training_corpus.jsonl")
ROWS = [json.loads(l) for l in open(CORPUS)]

PCT_TOL, PCT_ZERO = 0.5, 5.0
def _ids_by(anoms):
    d = {}
    for a in anoms or []:
        d.setdefault(a.get("attestation_id"), set()).add(a.get("type"))
    return d

def score_case(kind, exp, t4, resp):
    if kind.startswith("t4_"):
        truth=set(t4); fl={a.get("attestation_id") for a in resp.get("anomalies",[])}
        tp=len(truth&fl); pr=tp/len(fl) if fl else 0; rc=tp/len(truth) if truth else 1
        return 2*pr*rc/(pr+rc) if (pr+rc) else 0
    diff=abs(float(resp.get("canadian_content_percentage",-999))-exp["canadian_content_percentage"])
    pct=1.0 if diff<=PCT_TOL else max(0.0,1-(diff-PCT_TOL)/(PCT_ZERO-PCT_TOL))
    desig=1.0 if resp.get("designation")==exp["designation"] else 0.0
    em,rm=_ids_by(exp["anomalies"]),_ids_by(resp.get("anomalies")); ei,ri=set(em),set(rm); tp=ei&ri
    if not ei and not ri: f1=1.0
    elif not ei or not ri: f1=0.0
    else:
        p,r=len(tp)/len(ri),len(tp)/len(ei); f1=2*p*r/(p+r) if (p+r) else 0.0
    cl=(sum(1 for i in tp if em[i]&rm[i])/len(tp)) if tp else (1.0 if not ei else 0.0)
    return 0.30*pct+0.35*f1+0.20*desig+0.15*cl

def evaluate(rate_z, hours_z):
    os.environ["AEGIS_RATE_Z"]=str(rate_z); os.environ["AEGIS_HOURS_Z"]=str(hours_z)
    import verify; importlib.reload(verify)
    vc=verify.verify_chain
    total=0.0; bycat=defaultdict(lambda:[0.0,0])
    # micro F1 accounting for the breakdown table
    hard_tp=hard_fp=hard_fn=0; t4_tp=t4_fp=t4_fn=0; clean_overflag=0
    for row in ROWS:
        lab=row["labels"]; kind=lab.get("attack","clean"); t4=lab.get("t4_perturbed",[])
        resp=vc(json.loads(json.dumps(row["chain"])))
        s=score_case(kind,lab,t4,resp); total+=s; bycat[kind][0]+=s; bycat[kind][1]+=1
        flagged={a["attestation_id"] for a in resp.get("anomalies",[])}
        if kind=="clean":
            if flagged: clean_overflag+=1
        elif kind.startswith("t4_"):
            truth=set(t4); t4_tp+=len(truth&flagged); t4_fn+=len(truth-flagged); t4_fp+=len(flagged-truth)
        else:
            truth={a["attestation_id"] for a in lab["anomalies"]}
            hard_tp+=len(truth&flagged); hard_fn+=len(truth-flagged); hard_fp+=len(flagged-truth)
    return total/len(ROWS)*100, bycat, (hard_tp,hard_fp,hard_fn), (t4_tp,t4_fp,t4_fn), clean_overflag

def f1(tp,fp,fn):
    p=tp/(tp+fp) if (tp+fp) else 0; r=tp/(tp+fn) if (tp+fn) else 0
    return p, r, (2*p*r/(p+r) if (p+r) else 0)

if len(sys.argv)==3:
    rz,hz=float(sys.argv[1]),float(sys.argv[2])
    ov,bycat,hard,t4,cof=evaluate(rz,hz)
    print(f"\nRATE_Z={rz} HOURS_Z={hz}  ->  overall {ov:.2f}%\n")
    print(f"{'category':26s} avg     n")
    for k in sorted(bycat):
        v=bycat[k]; print(f"{k:26s} {v[0]/v[1]*100:5.1f}  {v[1]:4d}")
    hp,hr,hf=f1(*hard); tp,tr,tf=f1(*t4)
    allf=f1(hard[0]+t4[0],hard[1]+t4[1],hard[2]+t4[2])
    print(f"\nanomaly-detection F1 (micro over attestation_ids):")
    print(f"{'group':22s} prec   recall  f1     tp/fp/fn")
    print(f"{'hard (rule-based)':22s} {hp:.3f}  {hr:.3f}  {hf:.3f}  {hard[0]}/{hard[1]}/{hard[2]}")
    print(f"{'t4 (statistical)':22s} {tp:.3f}  {tr:.3f}  {tf:.3f}  {t4[0]}/{t4[1]}/{t4[2]}")
    print(f"{'all non-clean':22s} {allf[0]:.3f}  {allf[1]:.3f}  {allf[2]:.3f}  {hard[0]+t4[0]}/{hard[1]+t4[1]}/{hard[2]+t4[2]}")
    print(f"clean over-flagging: {cof}/705 cases ({cof/705*100:.1f}%)")
    sys.exit(0)

print("RATE_Z HOURS_Z  overall   t4cost  t4lab  cleanFP  all-nonclean-F1")
best=None
for hz in (3.0,2.8,2.6,2.4,2.2):
    for rz in (3.7,3.2,2.8,2.6,2.4,2.2):
        ov,bycat,hard,t4,cof=evaluate(rz,hz)
        tc=bycat["t4_cost_outlier"]; tl=bycat["t4_labour_outlier"]
        allf=f1(hard[0]+t4[0],hard[1]+t4[1],hard[2]+t4[2])[2]
        tag=""
        if best is None or ov>best[0]: best=(ov,rz,hz); tag=" <-- best"
        print(f"{rz:5}  {hz:5}   {ov:6.2f}%  {tc[0]/tc[1]*100:5.1f} {tl[0]/tl[1]*100:5.1f}   {cof:3d}     {allf:.3f}{tag}")
print(f"\nBEST: overall {best[0]:.2f}% at RATE_Z={best[1]} HOURS_Z={best[2]}")
