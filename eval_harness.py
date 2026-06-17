# -*- coding: utf-8 -*-
"""
Harnais d'evaluation du moteur de reco.
  (A) GOLD curated  -> precision similaires/complements + pertinence (eval_gold.py)
  (B) Siblings auto -> rappel objectif sur tout le catalogue (tokens-modele partages)
Usage:
  python eval_harness.py tfidf        # repli TF-IDF
  python eval_harness.py semantic     # E5 sans reranker
  python eval_harness.py rerank       # E5 + cross-encoder  (defaut)
"""
import sys, re, time, pickle
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
import numpy as np, pandas as pd
import reco_v2 as R
from eval_gold import GOLD

MODE = sys.argv[1] if len(sys.argv)>1 else "rerank"

def load():
    try:
        products = pd.read_pickle("_products.pkl"); rule_maps = pickle.load(open("_rulemaps.pkl","rb"))
    except Exception:
        products, rule_maps = R.build_products()
    return products, rule_maps

def build(products, rule_maps, mode):
    if mode=="tfidf":   return R.SmartRecoEngine(products, rule_maps, use_st=False)
    if mode=="semantic":return R.SmartRecoEngine(products, rule_maps, use_st=True, use_reranker=False)
    return R.SmartRecoEngine(products, rule_maps, use_st=True, use_reranker=True)

def hit(title_clean, tokens):
    # MOT ENTIER (et non sous-chaine) : "lcd" ne doit PAS valider via "Stylo 3D LCD" par hasard,
    # ni "resistance" via "photoresistance". L'eval ne doit pas se valider elle-meme sur un mot.
    return any(re.search(r'(?<![a-z0-9])'+re.escape(t)+r'(?![a-z0-9])', title_clean) for t in tokens)

def eval_gold(engine, verbose=True):
    from reco_v2 import normalize_text
    rows=[]; sim_p=[]; sim_found=[]; comp_p=[]; comp_good=[]; comp_viol=0
    for g in GOLD:
        res = engine.recommend(g["q"], n=3, in_stock_only=False)
        if res is None:
            rows.append((g["q"],"INTROUVABLE")); sim_found.append(0); continue
        src_ok = (res["source_cat"]==g["cat"])
        sims = [normalize_text(t) for t in res["similars"]["product_title"]]
        comps= list(zip([normalize_text(t) for t in res["complements"]["product_title"]],
                        res["complements"]["category"]))
        # similaires -- si la BONNE reponse est VIDE (pas de substitut en stock), vide=1.0, tout item=faux
        if g.get("sim_expect_empty"):
            sp = 1.0 if len(sims)==0 else 0.0; s_corr = 0 if len(sims)==0 else -1
        else:
            s_corr = sum(1 for s in sims if hit(s, g["sim_ok"]))
            sp = s_corr/len(sims) if sims else 0.0
        sim_p.append(sp); sim_found.append(1 if (sp>0) else 0)
        # complements
        c_corr=0; c_bad=0; c_goodhit=0
        for ct, cat in comps:
            in_cat = cat in g["comp_cats"]
            bad = hit(ct, g["comp_bad"])
            if bad: c_bad+=1
            if in_cat and not bad: c_corr+=1
            if hit(ct, g["comp_good"]): c_goodhit=1
        cp = c_corr/len(comps) if comps else (1.0 if not g["comp_cats"] else 0.0)
        comp_p.append(cp); comp_good.append(c_goodhit); comp_viol+=c_bad
        rows.append((g["q"][:42], f"src={'OK' if src_ok else res['source_cat']:>4} | simP={sp:.2f} found={s_corr} | compP={cp:.2f} good={c_goodhit} bad={c_bad}",
                     res["source_title"][:46],
                     " ; ".join(res["similars"]["product_title"].str[:34].tolist()),
                     " ; ".join(res["complements"]["product_title"].str[:34].tolist())))
    n=len(GOLD)
    print(f"\n========== GOLD curated ({n} cas) -- mode={MODE} ==========")
    print(f"  Similaires  : precision={np.mean(sim_p):.0%} | trouve >=1 bon = {np.mean(sim_found):.0%}")
    print(f"  Complements : precision={np.mean(comp_p):.0%} | a >=1 bon complement = {np.mean(comp_good):.0%} | fautes graves (bad) = {comp_viol}")
    glob = np.mean(sim_p+comp_p)
    print(f"  >>> SCORE GLOBAL (moy. precision sim+comp) = {glob:.1%}")
    if verbose:
        print("\n  --- detail par cas ---")
        for r in rows:
            if len(r)==2: print(f"   X {r[0]} -> {r[1]}"); continue
            print(f"   - {r[0]:<42} {r[1]}")
            print(f"       src: {r[2]}")
            print(f"       sim: {r[3]}")
            print(f"       cmp: {r[4]}")
    return glob

NOISE = re.compile(r'^\d+(v|mah|ah|mm|cm|w|a|ma|g|kg|mhz|khz|ghz|nm|ml|k|p|x|pcs|tpi|rpm|bp\d?|pin|broches)$')
STRONG = re.compile(r'^(?=.*[a-z])(?=.*\d)[a-z0-9]{3,}$')
def salient(title):
    from reco_v2 import norm_raw
    return {w for w in norm_raw(title).split() if STRONG.match(w) and not NOISE.match(w)}

def eval_siblings(engine, in_stock=True, max_q=None):
    P=engine.products
    tok2idx={}
    for i,t in enumerate(P["product_title"]):
        for w in salient(t): tok2idx.setdefault(w,[]).append(i)
    cat=engine._cat
    # gold[i] = autres produits partageant un token-modele ET meme categorie
    gold={}
    for i in range(len(P)):
        gi=set()
        for w in salient(P["product_title"].iloc[i]):
            for j in tok2idx.get(w,[]):
                if j!=i and cat[j]==cat[i]: gi.add(j)
        if gi: gold[i]=gi
    qs=[i for i in gold if (not in_stock or engine._stock[i]>0)]
    if max_q: qs=qs[:max_q]
    rec=0; prec=[]; t0=time.time()
    for c,i in enumerate(qs):
        res=engine.recommend(i, n=3, in_stock_only=False)
        if res is None: continue
        got=set(res["similars"].index)  # not reliable; use titles
        sim_titles=res["similars"]["product_title"].tolist()
        gold_titles={P["product_title"].iloc[j] for j in gold[i]}
        ncorr=sum(1 for t in sim_titles if t in gold_titles)
        if ncorr>0: rec+=1
        if sim_titles: prec.append(ncorr/len(sim_titles))
    print(f"\n========== Siblings AUTO ({len(qs)} requetes, {'stock' if in_stock else 'tout'}) -- mode={MODE} ==========")
    print(f"  Recall@3 (>=1 sibling retrouve) = {rec/len(qs):.0%}")
    print(f"  Precision@3 moyenne             = {np.mean(prec):.0%}")
    print(f"  ({time.time()-t0:.0f}s)")

if __name__=="__main__":
    MAXQ = int(sys.argv[2]) if len(sys.argv)>2 else 400
    products, rule_maps = load()
    eng = build(products, rule_maps, MODE)
    eval_gold(eng, verbose=True)
    eval_siblings(eng, in_stock=True, max_q=MAXQ)
