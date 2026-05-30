"""Three-way cross-reference, all scored against the organizer's corpus labels:
  A = our backend  (in-process verify.py)
  B = backend-cheick (teammate's app.verifier.verify)
  C = friend's reference verifier (test_suite_2 oracle)"""
import json, os, sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, os.path.join(ROOT, "backend-cheick"))
sys.path.insert(0, os.path.join(ROOT, "test_suite_2"))

from verify import verify_chain as A_verify              # ours
from app.verifier import verify as B_verify              # backend-cheick
from provtests import reference_verifier as C            # friend oracle

PCT_TOL, PCT_ZERO = 0.5, 5.0
def _ids_by(anoms):
    d={}
    for a in anoms or []: d.setdefault(a.get("attestation_id"),set()).add(a.get("type"))
    return d
def score(kind, exp, t4, resp):
    if kind.startswith("t4_"):
        truth=set(t4); fl={a.get("attestation_id") for a in resp.get("anomalies",[])}
        tp=len(truth&fl); pr=tp/len(fl) if fl else 0; rc=tp/len(truth) if truth else 1
        return 2*pr*rc/(pr+rc) if (pr+rc) else 0
    try: diff=abs(float(resp.get("canadian_content_percentage",-999))-exp["canadian_content_percentage"])
    except: diff=1e9
    pct=1.0 if diff<=PCT_TOL else max(0.0,1-(diff-PCT_TOL)/(PCT_ZERO-PCT_TOL))
    desig=1.0 if resp.get("designation")==exp["designation"] else 0.0
    em,rm=_ids_by(exp["anomalies"]),_ids_by(resp.get("anomalies")); ei,ri=set(em),set(rm); tp=ei&ri
    if not ei and not ri: f1=1.0
    elif not ei or not ri: f1=0.0
    else:
        p,r=len(tp)/len(ri),len(tp)/len(ei); f1=2*p*r/(p+r) if (p+r) else 0.0
    cl=(sum(1 for i in tp if em[i]&rm[i])/len(tp)) if tp else (1.0 if not ei else 0.0)
    return 0.30*pct+0.35*f1+0.20*desig+0.15*cl

rows=[json.loads(l) for l in open(os.path.join(ROOT,"training_corpus.jsonl"))]
limit=int(sys.argv[1]) if len(sys.argv)>1 else 0
if limit: rows=rows[:limit]

agg=defaultdict(lambda:[0.0,0.0,0.0,0])
tot=[0.0,0.0,0.0]
clean_fp=[0,0,0]
for row in rows:
    lab=row["labels"]; kind=lab.get("attack","clean"); t4=lab.get("t4_perturbed",[])
    for i,fn in enumerate((A_verify,B_verify,C.verify_chain)):
        try: resp=fn(json.loads(json.dumps(row["chain"])))
        except Exception as e: resp={"error":str(e)}
        s=score(kind,lab,t4,resp)
        tot[i]+=s; agg[kind][i]+=s
        if kind=="clean" and resp.get("anomalies"): clean_fp[i]+=1
    agg[kind][3]+=1

n=len(rows)
print(f"\nTHREE-WAY CROSS-REFERENCE  ({n} corpus cases, scored vs organizer labels)\n")
print(f"  A  our backend       : {tot[0]/n*100:5.1f}%   clean over-flags {clean_fp[0]}/705")
print(f"  B  backend-cheick     : {tot[1]/n*100:5.1f}%   clean over-flags {clean_fp[1]}/705")
print(f"  C  friend reference   : {tot[2]/n*100:5.1f}%   clean over-flags {clean_fp[2]}/705\n")
print(f"{'category':26s}  A     B     C     n")
for k in sorted(agg):
    a,b,c,m=agg[k]
    print(f"{k:26s} {a/m*100:5.1f} {b/m*100:5.1f} {c/m*100:5.1f} {m:4d}")
