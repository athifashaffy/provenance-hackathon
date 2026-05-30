"""Cross-reference: grade OUR live backend vs the friend's reference verifier,
both against the organizer's corpus labels, and diff where they disagree."""
import json, os, sys, urllib.request
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUITE2 = os.path.join(ROOT, "test_suite_2")
sys.path.insert(0, SUITE2)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "backend"))

from provtests import reference_verifier as ref   # friend's oracle


BACKEND = os.environ.get("BACKEND_URL", "http://localhost:8000/verify")
CORPUS = os.path.join(ROOT, "training_corpus.jsonl")

# harness per-case scoring (same formula as self_test.py)
PCT_TOL, PCT_ZERO = 0.5, 5.0
def _ids_by(anoms):
    d = {}
    for a in anoms or []:
        d.setdefault(a.get("attestation_id"), set()).add(a.get("type"))
    return d
def score(kind, expected, t4, resp):
    if kind.startswith("t4_"):
        truth=set(t4); flagged={a.get("attestation_id") for a in resp.get("anomalies",[])}
        tp=len(truth&flagged); pr=tp/len(flagged) if flagged else 0; rc=tp/len(truth) if truth else 1
        return 2*pr*rc/(pr+rc) if (pr+rc) else 0
    try: diff=abs(float(resp.get("canadian_content_percentage",-999))-expected["canadian_content_percentage"])
    except: diff=1e9
    pct=1.0 if diff<=PCT_TOL else max(0.0,1-(diff-PCT_TOL)/(PCT_ZERO-PCT_TOL))
    desig=1.0 if resp.get("designation")==expected["designation"] else 0.0
    em,rm=_ids_by(expected["anomalies"]),_ids_by(resp.get("anomalies")); ei,ri=set(em),set(rm); tp=ei&ri
    if not ei and not ri: f1=1.0
    elif not ei or not ri: f1=0.0
    else:
        p,r=len(tp)/len(ri),len(tp)/len(ei); f1=2*p*r/(p+r) if (p+r) else 0.0
    classif=(sum(1 for i in tp if em[i]&rm[i])/len(tp)) if tp else (1.0 if not ei else 0.0)
    return 0.30*pct+0.35*f1+0.20*desig+0.15*classif

def call_backend(chain, timeout=10):
    req=urllib.request.Request(BACKEND, data=json.dumps(chain).encode(),
                               headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())

rows=[json.loads(l) for l in open(CORPUS)]
limit=int(sys.argv[1]) if len(sys.argv)>1 else 0
if limit: rows=rows[:limit]

agg=defaultdict(lambda:[0.0,0.0,0])  # kind -> [ours, theirs, n]
ours_tot=theirs_tot=0.0
disagree=[]
for row in rows:
    lab=row["labels"]; kind=lab.get("attack","clean"); t4=lab.get("t4_perturbed",[])
    try: ours=call_backend(row["chain"])
    except Exception as e: ours={"error":str(e)}
    theirs=ref.verify_chain(row["chain"])
    so=score(kind,lab,t4,ours); st=score(kind,lab,t4,theirs)
    ours_tot+=so; theirs_tot+=st
    agg[kind][0]+=so; agg[kind][1]+=st; agg[kind][2]+=1
    # record material designation/validity disagreements between the two engines
    if (ours.get("designation")!=theirs.get("designation") or
        ours.get("chain_valid")!=theirs.get("chain_valid")):
        if len(disagree)<25:
            disagree.append((kind, ours.get("designation"),theirs.get("designation"),
                             ours.get("chain_valid"),theirs.get("chain_valid"),
                             round(ours.get("canadian_content_percentage",-1),1),
                             round(theirs.get("canadian_content_percentage",-1),1)))

n=len(rows)
print(f"\nCROSS-REFERENCE over {n} corpus cases (scored vs organizer labels)\n")
print(f"  OUR backend:        {ours_tot/n*100:.1f}%")
print(f"  Friend reference:   {theirs_tot/n*100:.1f}%\n")
print(f"{'category':28s} ours   theirs   n")
for k in sorted(agg):
    o,t,c=agg[k]
    flag = '  <-- diff' if abs(o-t)/c>0.03 else ''
    print(f"{k:28s} {o/c*100:5.1f}  {t/c*100:5.1f}  {c:4d}{flag}")
print(f"\nengine designation/validity disagreements: {sum(1 for _ in disagree)} shown (first 25)")
for d in disagree:
    print(f"  [{d[0]:22s}] desig ours={d[1]} theirs={d[2]} | valid ours={d[3]} theirs={d[4]} | pct {d[5]} vs {d[6]}")
