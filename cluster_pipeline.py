# -*- coding: utf-8 -*-
"""
COUCHE CLUSTERS -- "nettoyer 1 fois -> clusteriser -> servir".
  - substitute_key(p)  : signature TECHNIQUE canonique d'un produit (= sa classe de substituts).
  - build_clusters()   : groupe les 5774 produits en ~clusters d'equivalence (deterministe, 99%).
  - enrich_with_llm()  : OPTIONNEL -- raffine les cles vagues via un LLM (cache disque, fait 1 fois).
  - build_chain_graph(): aretes cluster->cluster (chaine systeme, au niveau cluster pas produit).
  - ClusterReco        : sert similaires (= meme cluster) + complements (= clusters de role adjacent).
Le moteur et le LLM travaillent alors sur du PROPRE -> rapide, deterministe, explicable, editable.
"""
import json, os, re
from collections import defaultdict

# ---- clef secondaire pour les categories SANS attribut definissant (eclate les gros sacs "None") ----
# (un 'outillage/None' de 2046 produits -> tournevis / pince / cle / foret ... = vrais sous-groupes)
SECONDARY = {
 "outillage": ["tournevis","pince","cle","clef","foret","meche","scie","marteau","douille","cliquet",
   "lime","cutter","perceuse","visseuse","meuleuse","ponceuse","rabot","burin","etau","cisaille",
   "brucelle","mandrin","embout","extracteur","agrafeuse","riveteuse","decapeur","pistolet","niveau",
   "truelle","spatule","pinceau","rouleau","echelle","cric","palan","aspirateur","compresseur",
   "laser","filament","graisseur","coffret","masque","gant","metre","equerre"],
 "mecanique": ["vis","ecrou","boulon","rondelle","rivet","roulement","engrenage","courroie","poulie",
   "ressort","rail","profile","entretoise","boitier","coque","dissipateur","radiateur","colonnette",
   "equerre","charniere","glissiere","tige","support","palier","bague"],
 "connectique": ["dupont","jumper","cosse","domino","bornier","borne","header","barrette","nappe",
   "gaine","cable","fil","connecteur","prise","cordon","rallonge","adaptateur","carte memoire","micro sd"],
 "soudure": ["fer","etain","flux","panne","tresse","pate","pompe","loupe","troisieme main","dessoudage"],
 "led": ["ruban","bande","ampoule","lampe","projecteur","spot","matrice","afficheur","voyant","neon",
   "horloge","barre","guirlande","reglette","dalle","tube"],
 "alimentation": ["alimentation","regulateur","convertisseur","transformateur","onduleur","buck","boost",
   "decoupage","fusible","panneau","batterie","chargeur","step"],
 "mesure": ["multimetre","pince","oscilloscope","compteur","balance","luxmetre","thermometre","wattmetre",
   "ph","sonde","testeur","frequencemetre","detecteur","amperemetre","voltmetre"],
 "audio": ["haut parleur","enceinte","microphone","ampli","buzzer","casque","ecouteur","jack","mp3"],
 "electrique": ["disjoncteur","contacteur","sectionneur","parafoudre","goulotte","armoire","compteur","telerupteur"],
 "rf": ["antenne","module","carte","badge","lecteur"],
}

def _secondary(cat, title_raw):
    for w in SECONDARY.get(cat, []):
        if w in title_raw: return w
    return None

def substitute_key(cat, attrs, title_raw, DEFINING):
    """Clef de CLASSE DE SUBSTITUTS : meme clef <=> interchangeables. Deterministe."""
    a = attrs or {}
    d = DEFINING.get(cat)
    label = a.get(d) if (d and a.get(d) is not None) else _secondary(cat, title_raw)
    role = a.get("system_position")
    volt = a.get("voltage_domain")
    return "%s|%s|%s|%s" % (cat, role, label if label is not None else "generic", volt or "-")

def build_clusters(products, DEFINING, title_raw_col=None):
    """Assigne un cluster_id a chaque produit (index). Retourne (clusters, prod2cluster, keys)."""
    keys = []
    for i, r in products.iterrows():
        traw = title_raw_col[i] if title_raw_col is not None else str(r["product_title"]).lower()
        keys.append(substitute_key(r["category"], r["attrs"], traw, DEFINING))
    key2id = {}
    prod2cluster = []
    clusters = defaultdict(list)
    for i, k in enumerate(keys):
        cid = key2id.setdefault(k, len(key2id))
        prod2cluster.append(cid)
        clusters[cid].append(i)
    return clusters, prod2cluster, keys

# ---- ENRICHISSEMENT LLM (optionnel, hors-ligne, cache) : raffine les clusters 'generic' encore vagues ----
def enrich_with_llm(products, keys, llm_chat=None, cache_path="_cluster_llm_cache.json", only_generic=True):
    """Pour les produits dont la clef finit par 'generic' (titre vague), demande au LLM une sous-clef
    fonctionnelle propre. CACHE DISQUE -> chaque produit n'est interroge qu'UNE fois. Sans LLM -> no-op."""
    cache = json.load(open(cache_path, encoding="utf-8")) if os.path.exists(cache_path) else {}
    if llm_chat is None:
        return keys, cache  # pas de LLM configure -> on garde le deterministe
    changed = 0
    for i, k in enumerate(keys):
        if only_generic and "|generic|" not in k: continue
        title = str(products.iloc[i]["product_title"])
        if title in cache:
            sub = cache[title]
        else:
            prompt = ("Donne UNIQUEMENT une cle technique courte (1-3 mots, minuscules, sans accents) "
                      "decrivant la FONCTION EXACTE de ce produit electronique/IoT, pour regrouper ses "
                      "substituts. Exemples: 'capteur temperature humidite', 'driver moteur pas a pas', "
                      "'cable hdmi'. Produit: \"%s\"\nCle:" % title[:160])
            try:
                sub = re.sub(r"[^a-z0-9 ]", "", llm_chat(prompt, max_tokens=20).strip().lower())[:40]
            except Exception:
                sub = ""
            cache[title] = sub
        if sub:
            keys[i] = k.rsplit("|", 2)[0] + "|llm:" + sub.replace(" ", "_") + "|" + k.rsplit("|", 1)[-1]
            changed += 1
    try: json.dump(cache, open(cache_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    except Exception: pass
    return keys, {"enriched": changed, "cached": len(cache)}

# ---- graphe de chaine au niveau CLUSTER (roles adjacents) ----
def build_chain_graph(clusters, prod2cluster, products, CHAIN_EDGES, SUPPORT_ROLES):
    """cluster_role[c] = role dominant du cluster ; edges[c] = clusters de role adjacent valide."""
    cluster_role = {}
    for cid, idxs in clusters.items():
        roles = [products.iloc[i]["attrs"].get("system_position") for i in idxs]
        cluster_role[cid] = max(set(roles), key=roles.count)
    by_role = defaultdict(list)
    for cid, role in cluster_role.items(): by_role[role].append(cid)
    edges = {}
    for cid, role in cluster_role.items():
        allowed = CHAIN_EDGES.get(role, set()) | SUPPORT_ROLES
        edges[cid] = [c for r in allowed for c in by_role.get(r, [])]
    return cluster_role, edges

# ---- SERVICE : reco par LOOKUP cluster (rapide, deterministe, explicable) ----
class ClusterReco:
    """Sert : SIMILAIRES = meme cluster ; COMPLEMENTS = meilleurs produits des clusters de role adjacent
    (1 par role -> chaine diversifiee). S'appuie sur un SmartRecoEngine pour le lookup + embeddings + stock."""
    def __init__(self, engine, DEFINING, CHAIN_EDGES, SUPPORT_ROLES, keys=None):
        self.eng = engine; self.P = engine.products
        traw = engine._title_raw
        if keys is None:
            self.clusters, self.p2c, self.keys = build_clusters(self.P, DEFINING, title_raw_col=traw)
        else:                                  # clefs deja enrichies (LLM) fournies
            self.keys = keys
            self.clusters = defaultdict(list); self.p2c=[0]*len(keys); key2id={}
            for i,k in enumerate(keys):
                cid=key2id.setdefault(k,len(key2id)); self.p2c[i]=cid; self.clusters[cid].append(i)
        self.cluster_role, self.edges = build_chain_graph(self.clusters, self.p2c, self.P, CHAIN_EDGES, SUPPORT_ROLES)

    def recommend(self, query, n=4, in_stock_only=False):
        """HYBRIDE : SIMILAIRES = classe de substituts (cluster, propre + couvre les titres vagues) ;
        COMPLEMENTS = moteur hard-compat (board/tension/role, deja role-diversifie et valide)."""
        base = self.eng.recommend(query, n=n, in_stock_only=in_stock_only)
        if base is None: return None
        i = base["source_idx"]; cid = self.p2c[i]; S = self.eng._sims(i)
        ok = lambda j: (not in_stock_only) or self.eng._stock[j] > 0
        sims = sorted([j for j in self.clusters[cid] if j != i and ok(j)], key=lambda j: -float(S[j]))[:n]
        base["source_cluster"] = self.keys[i]
        base["source_role"]    = self.cluster_role[cid]
        base["similars_cluster"] = [self.P.iloc[j]["product_title"] for j in sims]
        base["cluster_size"]   = len(self.clusters[cid])
        return base

def export_clusters(products, keys, cluster_role, prod2cluster, path="product_clusters.json"):
    """Artefact EDITABLE par l'humain : table des clusters (clef, role, taille, exemples) + map produit->cluster."""
    from collections import defaultdict as _dd
    members = _dd(list)
    for i, c in enumerate(prod2cluster): members[c].append(i)
    cl = []
    for cid, idxs in members.items():
        cl.append({"cluster_id": cid, "substitute_key": keys[idxs[0]], "system_role": cluster_role[cid],
                   "size": len(idxs), "examples": [str(products.iloc[j]["product_title"])[:70] for j in idxs[:4]]})
    cl.sort(key=lambda x: -x["size"])
    out = {"meta": {"products": len(products), "clusters": len(cl),
                    "generic_remaining": sum(1 for k in keys if "|generic|" in k)},
           "clusters": cl}
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return out["meta"]
