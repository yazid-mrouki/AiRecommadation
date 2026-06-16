# -*- coding: utf-8 -*-
"""
Moteur de recommandation IoT v2 -- testable en standalone.
  - Recherche produit ROBUSTE : index/handle/SKU/titre exact -> substring -> semantique -> fuzzy
  - SIMILAIRES   : meme famille ; garde-fou sur l'attribut DEFINISSANT ; rappel ameliore
                   par re-ranking cross-encoder ; detection d'upgrade par spec.
  - COMPLEMENTAIRES : compatibles, AUTRE famille ; PLANCHER de pertinence reel (fini sim=0.00) ;
                      blacklist industriel + blacklist par categorie (exclure_mots_cles) ; jamais un outil.
Fonctionne en mode SEMANTIQUE (sentence-transformers, E5 + cross-encoder) ou en repli TF-IDF.
"""
import pandas as pd, numpy as np, re, unicodedata, warnings, time
from pathlib import Path
from sklearn.neighbors import NearestNeighbors
from sklearn.feature_extraction.text import TfidfVectorizer
warnings.filterwarnings("ignore")

try:
    from sentence_transformers import SentenceTransformer, CrossEncoder
    HAS_ST = True
except Exception:
    HAS_ST = False
try:
    from rapidfuzz import process as _rf_process, fuzz as _rf_fuzz
    HAS_FUZZ = True
except Exception:
    HAS_FUZZ = False

# ---------------------------------------------------------------- preprocessing
def normalize_text(text):
    text = "" if pd.isna(text) else str(text)
    text = unicodedata.normalize("NFKD", text).encode("ascii","ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9\s]"," ",text)
    stop = {"de","des","du","la","le","les","un","une","et","au","aux","pour","avec","sur","dans","par","ou","en"}
    return " ".join(t for t in text.split() if len(t)>1 and t not in stop)
def norm_raw(text):
    text = "" if pd.isna(text) else str(text)
    text = unicodedata.normalize("NFKD", text).encode("ascii","ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+"," ",text).strip()

# Spec d'upgrade (defini nativement pour que le moteur marche meme charge depuis un pickle)
UPGRADE_SPECS = ["capacity_mah","capacity_ah","power_w","count"]
def primary_spec(specs):
    specs = specs or {}
    for k in UPGRADE_SPECS:
        if k in specs: return k, specs[k]
    return None, 0.0

def build_products(csv="inventory_export.csv", verbose=True):
    df_raw = pd.read_csv(csv); df = df_raw.copy(); df.columns = df.columns.str.lower().str.strip()
    g = {"normalize_text":normalize_text, "norm_raw":norm_raw, "pd":pd, "np":np, "re":re, "unicodedata":unicodedata}
    exec(open("pipeline_categorize.py",encoding="utf-8").read(), g)
    for k in ("infer_category","extract_specs","extract_attrs","is_tool_brand","primary_spec","TYPE_ATTRIBUTES"):
        globals()[k] = g.get(k)
    infer_category=g["infer_category"]; extract_specs=g["extract_specs"]; extract_attrs=g["extract_attrs"]; is_tool_brand=g["is_tool_brand"]
    df["product_handle"]=df["handle"].astype(str).str.strip(); df["product_title"]=df["title"].astype(str).str.strip()
    df["sku"]=df["sku"].astype(str).str.strip() if "sku" in df.columns else ""
    for col in ["available (not editable)","on hand (current)","on hand (new)"]:
        if col in df.columns:
            df[col]=df[col].replace("not stocked",0); df[col]=pd.to_numeric(df[col],errors="coerce").fillna(0).astype(int)
    df["clean_title"]=df["product_title"].apply(normalize_text); df["category"]=df["product_title"].apply(infer_category)
    _mask=df["category"]=="autre"
    if _mask.any():
        _known=df.loc[~_mask]; _v=TfidfVectorizer(max_features=3000).fit(df["clean_title"])
        _nn=NearestNeighbors(n_neighbors=1,metric="cosine").fit(_v.transform(_known["clean_title"]))
        _,_ind=_nn.kneighbors(_v.transform(df.loc[_mask,"clean_title"])); df.loc[_mask,"category"]=_known["category"].to_numpy()[_ind[:,0]]
    df["specs"]=df["product_title"].apply(extract_specs); df["attrs"]=df.apply(lambda r: extract_attrs(r["product_title"],r["specs"]),axis=1)
    df["is_tool"]=df["product_title"].apply(is_tool_brand)
    g2={"df":df,"pd":pd,"np":np,"re":re,"normalize_text":normalize_text,"norm_raw":norm_raw}
    exec(open("pipeline_refine.py",encoding="utf-8").read(), g2); df=g2["df"]
    g3={"pd":pd,"Path":Path,"normalize_text":normalize_text}
    exec(open("pipeline_rules.py",encoding="utf-8").read(), g3)
    rule_maps = {k:g3[k] for k in ("TYPE_ATTRIBUTES","COMPLEMENTARITY_MAP","COMPLEMENT_BROAD","COMPLEMENT_KEYWORDS","COMPLEMENT_EXCLUDE")}
    globals()["TYPE_ATTRIBUTES"]=g3["TYPE_ATTRIBUTES"]; globals()["primary_spec"]=g["primary_spec"]
    products=df.drop_duplicates(subset=["product_handle"]).copy()
    inv=df.groupby("product_handle").agg({"available (not editable)":"sum","on hand (current)":"sum","on hand (new)":"sum"}).reset_index()
    inv.columns=["product_handle","available_total","on_hand_current","on_hand_new"]
    products=products.merge(inv,on="product_handle",how="left"); products["available_total"]=products["available_total"].fillna(0).astype(int)
    products["product_profile"]=products["product_title"].fillna("")+" categorie "+products["category"].fillna("")
    products=products[["product_handle","product_title","category","sku","specs","attrs","is_tool","clean_title","product_profile","available_total"]].reset_index(drop=True)
    if verbose: print(f"OK {len(products)} produits uniques | en stock: {int((products['available_total']>0).sum())} | 'autre'={100*(products['category']=='autre').mean():.1f}%")
    return products, rule_maps

# ---------------------------------------------------------------- engine
class SmartRecoEngine:
    EMB_MODEL    = "intfloat/multilingual-e5-base"
    RERANK_MODEL = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
    STRONG = re.compile(r'^(?=.*[a-z])(?=.*\d)[a-z0-9]{3,}$')
    BLACKLIST = {"220v","380v","secteur","automate","simatic","plc","disjoncteur","contacteur",
                 "sectionneur","industrial","triphase","cn3791","variateur","profibus","fpga","altera","cyclone","cbb65","climatiseur"}
    # Attribut DEFINISSANT : doit coincider pour qu'un produit soit un VRAI substitut.
    DEFINING = {"batterie":"form_factor","carte":"board","composant":"component","capteur":"sensor",
                "electronique":"module_fn","moteur":"motor","led":"led_form","rf":"rftech","mobilite":"vehicle"}
    # Indices FORTS qu'un produit est un OUTIL / industriel (au-dela des marques connues) :
    # ces items polluent les recos quand ils sont mal categorises (foret en 'composant', etc.).
    TOOL_LIKE = re.compile(r'\b(foret|forets|meche|meches|ponceuse|souffleur|meuleuse|disqueuse|'
        r'tronconneuse|perceuse|visseuse|rabot|decapeur|compresseur|pistolet|peinture|burin|truelle|'
        r'riveteuse|agrafeuse|massette|marteau|tournevis|cutter|sangle|echelle|escabeau|brouette|cric|'
        r'palan|compression moteur|moteur essence|poste a souder|poste de soudure|\bmma\b|450kg|'
        r'\bscie\b|lame de scie|cisaille|nettoyeur|electrogene|aspirateur|taraud|filiere|mandrin|'
        r'extracteur|arrache|culasse|injecteur|vilebrequin|soupape|frein|etrier|rotule|cardan|'
        r'cle mixte|cle plate|cle a pipe|cle polygonale|cle a molette|cle dynamo|cle a ergot|'
        r'cle a choc|cle hexagonale|cle torx|cle allen|jeu de cle|pince multiprise|pince universelle|'
        r'pince coupante|pince a denuder|pince a sertir|pince a bec|coupe cable|coupe boulon|coffret)\b')
    # Seuils (calibres en phase 3). En mode TF-IDF on abaisse car les scores sont plus bas.
    def _floors(self):
        # Les seuils dependent de la SOURCE du score :
        #   - TF-IDF        : cosinus epars, faibles
        #   - cross-encoder : sigmoid bien separee (pertinent ~0.9 / bruit ~0.02)
        #   - E5 seul       : cosinus compresse (0.75-0.90) -> seuils hauts
        # (LOOKUP utilise toujours le cosinus embeddings, jamais le CE.)
        if self.is_sparse:
            return dict(SIM_ALT=0.18, SIM_NODEF=0.12, COMP=0.06, LOOKUP=0.30)
        # E5. Les SIMILAIRES sont scores par le cross-encoder si dispo (sigmoid bien separee),
        # sinon par le cosinus E5 (compresse 0.75-0.90).
        sim = dict(SIM_ALT=0.40, SIM_NODEF=0.35) if self.ce is not None else dict(SIM_ALT=0.86, SIM_NODEF=0.86)
        # Les COMPLEMENTAIRES n'utilisent JAMAIS le cross-encoder (il penalise une autre famille)
        # -> plancher sur le cosinus E5, quel que soit le mode.
        return dict(COMP=0.85, LOOKUP=0.82, **sim)

    def __init__(self, products, rule_maps, use_st=None, use_reranker=True, verbose=True):
        self.products = products.reset_index(drop=True)
        self.comp_map     = rule_maps["COMPLEMENTARITY_MAP"]
        self.comp_broad   = rule_maps["COMPLEMENT_BROAD"]
        self.comp_keywords= rule_maps["COMPLEMENT_KEYWORDS"]
        self.comp_exclude = rule_maps["COMPLEMENT_EXCLUDE"]
        self.type_attrs   = rule_maps["TYPE_ATTRIBUTES"]
        self.products["clean_profile"]=self.products["product_profile"].fillna("").apply(normalize_text)
        self.products["strong"]=self.products["clean_profile"].apply(lambda s:{w for w in s.split() if self.STRONG.match(w)})
        self.cat_to_idx={c:list(g.index) for c,g in self.products.groupby("category")}
        self._cat=self.products["category"].tolist(); self._attrs=self.products["attrs"].tolist()
        self._tool=self.products["is_tool"].tolist(); self._stock=self.products["available_total"].tolist()
        self._strong=self.products["strong"].tolist(); self._title=self.products["product_title"].tolist()
        self._title_clean=self.products["clean_title"].tolist(); self._specs=self.products["specs"].tolist()
        self._handle=self.products["product_handle"].astype(str).str.lower().tolist()
        self._skul=self.products["sku"].astype(str).str.lower().tolist()
        use_st = HAS_ST if use_st is None else (use_st and HAS_ST)
        self.ce=None
        if use_st:
            if verbose: print("Chargement E5 (embeddings semantiques)...")
            self.emb=SentenceTransformer(self.EMB_MODEL)
            self.X=self._encode_cached(list(self.products["clean_profile"]), verbose)
            self.is_sparse=False; mode="semantique E5"
            if use_reranker:
                if verbose: print("Chargement cross-encoder (re-ranking)...")
                self.ce=CrossEncoder(self.RERANK_MODEL); mode+=" + cross-encoder"
        else:
            self.vec=TfidfVectorizer(max_features=5000, ngram_range=(1,2))
            self.X=self.vec.fit_transform(self.products["clean_profile"]); self.is_sparse=True; mode="TF-IDF (repli)"
        self.F=self._floors()
        if verbose: print(f"OK Moteur pret -- {len(self.products)} produits -- mode {mode}")

    def _encode_cached(self, profiles, verbose):
        """Encode E5 avec cache disque (cle = modele + contenu) pour iterer vite en local."""
        import hashlib, os
        key = hashlib.md5((self.EMB_MODEL + "||" + "\n".join(profiles)).encode("utf-8")).hexdigest()[:16]
        path = f"_emb_{key}.npy"
        if os.path.exists(path):
            if verbose: print(f"  (embeddings charges du cache {path})")
            return np.load(path)
        X = self.emb.encode(["passage: "+p for p in profiles], normalize_embeddings=True,
                            batch_size=64, show_progress_bar=verbose).astype(np.float32)
        try: np.save(path, X)
        except Exception: pass
        return X

    # ---- similarites
    def _sims(self, i):
        if self.is_sparse: return (self.X @ self.X[i].T).toarray().ravel()
        return self.X @ self.X[i]
    def _sims_vec(self, qv):
        if self.is_sparse: return (self.X @ qv.T).toarray().ravel()
        return self.X @ qv
    def _pair_sim(self, a, b):
        if self.is_sparse: return float((self.X[a] @ self.X[b].T).toarray().ravel()[0])
        return float(self.X[a] @ self.X[b])
    def _diverse(self, idxs, k, thr):
        """Garde au plus k indices en evitant les quasi-doublons (cosinus > thr)."""
        picked=[]
        for j in idxs:
            if len(picked)>=k: break
            if all(self._pair_sim(j,p)<=thr for p in picked): picked.append(j)
        return picked
    def _tool_like(self, tc):
        return bool(self.TOOL_LIKE.search(tc))
    def _efftool(self, j):
        """Outil EFFECTIF = marque-outil connue OU titre de type outil/industriel."""
        return bool(self._tool[j]) or self._tool_like(self._title_clean[j])
    @staticmethod
    def _kw_hit(tc, kws):
        """Match de mot-cle par MOT ENTIER (evite 'resistance' dans 'photoresistance')."""
        for k in kws:
            if re.search(r'(?<![a-z0-9])'+re.escape(k)+r'(?![a-z0-9])', tc): return True
        return False
    def _qvec(self, text):
        if self.is_sparse: return self.vec.transform([normalize_text(text)])
        return self.emb.encode(["query: "+normalize_text(text)], normalize_embeddings=True)[0].astype(np.float32)
    def _rerank(self, query_title, idxs):
        """Retourne {idx: score[0,1]} via cross-encoder ; sinon {} (repli sur semantique)."""
        if self.ce is None or not idxs: return {}
        pairs=[(query_title, self._title[j]) for j in idxs]
        raw=np.asarray(self.ce.predict(pairs, show_progress_bar=False), dtype=np.float64)
        sc=1.0/(1.0+np.exp(-raw))
        return {j:float(s) for j,s in zip(idxs, sc)}

    # ---- recherche produit ROBUSTE
    def get_product_index(self, q, return_conf=False):
        if isinstance(q,(int,np.integer)):
            ok = 0<=int(q)<len(self.products); return (int(q) if ok else None) if not return_conf else ((int(q),1.0) if ok else (None,0.0))
        qs=str(q).strip(); ql=qs.lower()
        if ql in self._handle:  i=self._handle.index(ql); return (i,1.0) if return_conf else i
        if ql in self._skul and ql.strip():  i=self._skul.index(ql); return (i,1.0) if return_conf else i
        nq=normalize_text(qs)
        if nq in self._title_clean:  i=self._title_clean.index(nq); return (i,1.0) if return_conf else i
        m=self.products[self.products["product_title"].str.contains(re.escape(qs), case=False, na=False)]
        if len(m): i=int(m.index[0]); return (i,0.95) if return_conf else i
        # semantique
        S=self._sims_vec(self._qvec(qs)); j=int(np.argmax(S)); conf=float(S[j])
        if conf>=self.F["LOOKUP"]: return (j,conf) if return_conf else j
        # fuzzy lexical
        if HAS_FUZZ:
            best=_rf_process.extractOne(nq, self._title_clean, scorer=_rf_fuzz.token_set_ratio)
            if best and best[1]>=80:
                i=self._title_clean.index(best[0]); return (i,best[1]/100.0) if return_conf else i
        return (j,conf) if return_conf else j   # dernier recours : meilleur semantique

    def _rows(self, idx, S):
        cols=["product_title","category","attrs","specs","available_total"]
        if not idx: return pd.DataFrame(columns=cols+["score"])
        out=self.products.loc[idx, cols].copy(); out["score"]=[round(float(S.get(j,0.0)),3) for j in idx]
        return out.reset_index(drop=True)

    def recommend(self, query, n=3, in_stock_only=True):
        i=self.get_product_index(query)
        if i is None: return None
        cat=self._cat[i]; sa={k:v for k,v in self._attrs[i].items() if v is not None}; stool=self._tool[i]
        src_efftool=self._efftool(i)   # l'objet source est-il un outil (marque OU type) ?
        def ok(j): return (not in_stock_only) or self._stock[j]>0
        S=self._sims(i)

        # ===== SIMILAIRES =====
        # On compare outils-avec-outils : une perceuse -> perceuses ; une resistance -> JAMAIS un foret.
        pool=[j for j in self.cat_to_idx.get(cat,[]) if j!=i and ok(j) and self._efftool(j)==src_efftool]
        pool=sorted(pool, key=lambda j:S[j], reverse=True)[:60]
        rr=self._rerank(self._title[i], pool)
        sc={j: rr.get(j, float(S[j])) for j in pool}     # score unifie [0,1]-ish
        defining=self.DEFINING.get(cat); src_def=self._attrs[i].get(defining) if defining else None
        if src_def is not None:
            tier1=[j for j in pool if self._attrs[j].get(defining)==src_def]
            tier2=[j for j in pool if self._attrs[j].get(defining)!=src_def and sc[j]>=self.F["SIM_ALT"]]
            # batterie : un substitut d'une AUTRE taille doit au moins partager la CHIMIE
            # (jamais une AA alcaline proposee comme similaire d'une 18650 lithium).
            if cat=="batterie":
                sch=self._attrs[i].get("chemistry")
                tier2=[j for j in tier2 if self._attrs[j].get("chemistry")==sch]
        else:
            tier1=[j for j in pool if sc[j]>=self.F["SIM_NODEF"]]; tier2=[]
        pk,pv=primary_spec(self._specs[i]); ups=[]
        if pk:
            ups=[j for j in tier1 if primary_spec(self._specs[j])[0]==pk and primary_spec(self._specs[j])[1]>pv]
            ups=sorted(ups, key=lambda j:(primary_spec(self._specs[j])[1], sc[j]), reverse=True)
        rest=sorted([j for j in tier1 if j not in ups], key=lambda j:sc[j], reverse=True)
        tier2=sorted(tier2, key=lambda j:sc[j], reverse=True)
        # diversite douce : on retire seulement les RE-LISTINGS quasi-identiques (garde les variantes)
        similars=self._diverse(ups+rest+tier2, n, thr=0.985 if not self.is_sparse else 0.97)

        # ===== COMPLEMENTAIRES =====
        # On calcule les complements des que la categorie a des regles (comp_cats non vide).
        # Les vraies categories d'outils (outillage/mecanique/electrique) ont des regles VIDES
        # -> naturellement aucun complement. Mais un objet de marque-outil tombe dans une
        # categorie IoT (ex: fer a souder TOTAL -> 'soudure') garde ses complements (etain/flux).
        comp=[]; comp_scores={}
        comp_cats=self.comp_map.get(cat,[])
        if comp_cats:
            broad=set(self.comp_broad.get(cat,[]))
            ckw=self.comp_keywords.get(cat,[]); excl=self.comp_exclude.get(cat,[])
            volt_ok=cat not in ("batterie","chargeur")
            raw=[]
            for ci,cc in enumerate(comp_cats):
                cc_broad=cc in broad
                for j in self.cat_to_idx.get(cc,[]):
                    # un complement n'est JAMAIS un outil (marque ou type) ni du bruit industriel
                    if j==i or not ok(j) or self._efftool(j) or any(b in self._title_clean[j] for b in self.BLACKLIST): continue
                    tj=self._title_clean[j]
                    if excl and any(e in tj for e in excl): continue
                    ja=self._attrs[j]; hard=0.0
                    if sa.get("board") and ja.get("board")==sa["board"]: hard+=0.6
                    if sa.get("connector") and ja.get("connector")==sa["connector"]: hard+=0.5
                    if sa.get("form_factor") and sa["form_factor"] in tj: hard+=0.6
                    if sa.get("chemistry") and ja.get("chemistry")==sa["chemistry"]: hard+=0.3
                    if volt_ok and sa.get("voltage_bucket") and ja.get("voltage_bucket")==sa["voltage_bucket"]: hard+=0.4
                    kw=1 if self._kw_hit(tj, ckw) else 0
                    if kw: hard+=0.5
                    if cc_broad: hard+=0.4
                    raw.append((j, min(hard,1.0), ci, kw))
            pre=sorted(raw, key=lambda c:(c[1], S[c[0]]), reverse=True)[:80]
            # NB : pas de cross-encoder ici. Le CE mesure la similarite MEME-sujet et penalise
            # donc les bons complements (autre famille). On classe par compatibilite DURE
            # (board/connecteur/tension/mot-cle) dominante ; le cosinus E5 sert de tie-break.
            # Un complement DOIT avoir un signal de compatibilite reel (hard>=0.3) : ni le simple
            # cosinus, ni rien, ne suffit -> fini le filler "photoresistance pour toute carte".
            scored=[]
            for (j,hard,ci,kw) in pre:
                sem=float(S[j])
                if hard < 0.30: continue
                scored.append((j, 0.70*hard+0.30*sem, ci, sem))
            order=[j for j,_,_,_ in sorted(scored, key=lambda x:(-x[1], x[2]))]
            comp_scores={j:sm for j,_,_,sm in scored}
            comp=self._diverse(order, n, thr=0.94 if not self.is_sparse else 0.85)

        allsc={**{j:sc.get(j,float(S[j])) for j in similars}}
        if comp: allsc.update(comp_scores)
        return {"source_idx":i,"source_title":self._title[i],"source_cat":cat,"source_attrs":sa,
                "is_tool":bool(stool),"similars":self._rows(similars,allsc),"complements":self._rows(comp,allsc)}
