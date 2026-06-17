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
    # ETAPE 2 (TYPE SYSTEME) : role dans la chaine, calcule sur la categorie FINALE (post-affinage).
    asp=g["a_system_position"]
    df["attrs"]=[{**a,"system_position":asp(c,a)} for a,c in zip(df["attrs"],df["category"])]
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
                "electronique":"module_fn","moteur":"motor","led":"led_form","rf":"rftech","mobilite":"mobility_part"}
    # "REASONING FILTER" : un COMPLEMENT doit etre un maillon ADJACENT valide de la chaine systeme.
    #   role_source -> {roles de complement admis}. On bloque les incoherences de role meme si le
    #   texte/la tension coincident (ex: interface 'ruban LED' -> capteur 'thermostat 12V' = REFUSE).
    CHAIN_EDGES = {
        "alimentation": {"alimentation","controle","capteur","traitement","actionneur","interface","communication"},
        "controle":     {"alimentation","capteur","traitement","actionneur","interface","communication"},
        "capteur":      {"alimentation","controle","traitement","actionneur","interface"},
        "traitement":   {"alimentation","controle","capteur","traitement","actionneur","interface"},
        "actionneur":   {"alimentation","controle","capteur","traitement","actionneur","interface","communication"},
        "interface":    {"alimentation","controle","traitement","interface"},  # PAS 'capteur' NI 'actionneur' (ruban LED -> moteur = faux)
        "communication":{"alimentation","controle"},
    }
    # Interconnexions VIDEO / grand public : ni similaire ni complement IoT (HDMI/VGA/DVI...).
    VIDEO_TERMINAL = re.compile(r'\b(hdmi|vga|dvi|peritel|displayport|lightning|playstation|ps2)\b')
    # PROFIL DE CONTEXTE : par contexte d'usage et par role de complement -> mots-cles EXIGES (sinon
    # le bon role mais le mauvais objet) et INTERDITS (objet du mauvais monde). Rend la chaine REELLE.
    CONTEXT_PROFILE = {
        "drone": {
            "actionneur": {"req": ("brushless","helice","esc","kv","2204","2205","2206","2207","2306","a2212","a2208","gemfan"),
                           "forbid": ("servo","nema","pas a pas","stepper","pompe","ventilateur")},
            "alimentation": {"req": ("lipo","esc","bec","xt60","xt30"),
                             "forbid": ("secteur","220v","mural")},
        },
    }
    # AFFINITE D'ACHAT (panier reel) : ce qu'un humain achete NATURELLEMENT avec un produit de cette
    # categorie -> on prefere l'accessoire UNIVERSEL (breadboard/dupont/LCD) au composant de NICHE
    # (MOSFET/XL6009) meme s'il est techniquement compatible. 'compatible' != 'pertinent a l'achat'.
    PURCHASE_AFFINITY = {
      "carte":    {"breadboard":0.5,"plaque essai":0.5,"dupont":0.5,"jumper":0.45,"cavalier":0.45,
                   "lcd":0.4,"oled":0.4,"afficheur":0.4,"capteur":0.4,"relais":0.35,"alimentation":0.3,"resistance":0.3},
      "capteur":  {"arduino":0.5,"esp32":0.5,"raspberry":0.45,"breadboard":0.45,"dupont":0.45,"jumper":0.4,
                   "lcd":0.4,"oled":0.4,"afficheur":0.35,"resistance":0.3},
      "led":      {"alimentation":0.5,"controleur":0.5,"dimmer":0.45,"telecommande":0.45,"amplificateur":0.45,
                   "connecteur":0.4,"transformateur":0.4,"profile":0.3,"ruban":0.3},
      "moteur":   {"driver":0.5,"l298":0.5,"a4988":0.5,"esc":0.5,"controleur":0.45,"alimentation":0.4,
                   "batterie":0.4,"lipo":0.4,"roue":0.3},
      "mobilite": {"moteur":0.5,"driver":0.45,"batterie":0.45,"lipo":0.45,"esc":0.45,"roue":0.4,"helice":0.4,
                   "capteur":0.35,"controleur":0.35},
      "batterie": {"chargeur":0.5,"support":0.45,"porte pile":0.45,"holder":0.45,"bms":0.4,"boitier":0.35},
      "composant":{"breadboard":0.5,"plaque essai":0.5,"dupont":0.45,"support":0.4,"resistance":0.35},
      "electronique":{"arduino":0.45,"esp32":0.45,"breadboard":0.4,"dupont":0.4,"resistance":0.3,"afficheur":0.35,"alimentation":0.3},
      "alimentation":{"arduino":0.45,"esp32":0.45,"raspberry":0.45,"ruban":0.4,"led":0.35,"boitier":0.3,"jack":0.3},
      "chargeur": {"batterie":0.5,"pile":0.45,"accu":0.4,"cable":0.3},
      "rf":       {"arduino":0.5,"esp32":0.5,"antenne":0.45,"dupont":0.4,"raspberry":0.4},
    }
    # Composants de NICHE : compatibles mais rarement un achat NATUREL avec une carte/un ruban/un capteur.
    NICHE_COMP = re.compile(r'\b(mosfet|bss138|bss\d|irf\d|2n\d{3,4}|bc\d{3}|xl6009|mt3608|lm2596|xl4015|'
                            r'optocoupleur|opto|darlington|uln2003|zener|diac|scr|thyristor|'
                            r'pt100|pt1000|thermocouple|max6675|max31855|4-20ma|rj45)\b')   # composants/capteurs de NICHE
    SUPPORT_ROLES = {"connectique","mecanique"}     # cables / boitiers / supports : admis avec tout role
    ROLE_LABEL = {"alimentation":"alimentation (energie)","controle":"controle (MCU)","capteur":"capteur (entree)",
        "traitement":"traitement / module","actionneur":"actionneur (sortie)","interface":"interface / affichage",
        "communication":"communication (RF)","connectique":"connectique","mecanique":"mecanique / support",
        "outil":"outil (hors systeme)","autre":"autre"}
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
        r'pince coupante|pince a denuder|pince a sertir|pince a bec|coupe cable|coupe boulon|coffret|'
        r'pompe a graisse|graisse|pompe a huile|fer a souder|poste a souder|station de soudage|'
        r'burineur|cloueur|agrafeur|deboucheur|nettoyeur haute pression|karcher|pulverisateur|'
        r'tournevisseuse|riveteur|scie sabre|scie circulaire|ponceur|gonfleur|manometre)\b')
    # Bruit "complement" : items industriels / domotique batiment qui ne sont PAS des complements
    # IoT-dev (un ESP32 ne se complete pas avec un detecteur de fumee secteur ou un capteur inductif).
    COMP_NOISE = re.compile(r'\b(hdmi|vga|dvi|peritel|displayport|'
        r'inductif|capacitif|plafonnier|micro ?onde|fin de course|'
        r'detecteur de fumee|detecteur de mouvement a micro|sirene|cctv|surveillance|telerupteur|'
        r'controle d acces|serrure|badge|portail|barriere|interphone|parlophone|prise intelligente|'
        # produits finis GRAND PUBLIC / domotique : pas des briques d'un montage IoT
        r'sonoff|air ?fly ?mouse|air mouse|fly mouse|tv box|android tv|smart tv|box tv|'
        r'incubateur|incubator|webcam|casque|ecouteur|montre connectee|aspirateur robot|'
        # instruments FINIS + actionneurs domestiques mal etiquetes (jamais un complement d'achat) :
        r'microscope|loupe|oscilloscope|stereoscope|telescope|jumelles|'
        r'humidificateur|nebuliseur|atomiseur|diffuseur|lnb|'
        r'disjoncteur|contacteur|sectionneur|variateur)\b')
    # Seuils. En mode TF-IDF on abaisse car les scores sont plus bas.
    def _floors(self):
        # Similaires classes par le cosinus E5 (compresse 0.75-0.90) -> seuils hauts.
        if self.is_sparse:
            return dict(SIM_ALT=0.18, SIM_NODEF=0.12, COMP=0.06, LOOKUP=0.30)
        sim = dict(SIM_ALT=0.86, SIM_NODEF=0.86)
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
        # titre BRUT (garde 'de'/'a'/'d'' et lettres seules) -> pour outils/bruit (ex: 'pompe a graisse')
        self._title_raw=[norm_raw(t) for t in self._title]
        self._handle=self.products["product_handle"].astype(str).str.lower().tolist()
        self._skul=self.products["sku"].astype(str).str.lower().tolist()
        use_st = HAS_ST if use_st is None else (use_st and HAS_ST)
        self.ce=None  # plus de cross-encoder : il produisait des scores trompeurs (0.00 sur un bon similaire)
        if use_st:
            if verbose: print("Chargement E5 (embeddings semantiques)...")
            self.emb=SentenceTransformer(self.EMB_MODEL)
            self.X=self._encode_cached(list(self.products["clean_profile"]), verbose)
            self.is_sparse=False; mode="semantique E5"
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
    def _efftool(self, j):
        """Outil EFFECTIF = marque-outil connue OU titre de type outil/industriel (sur titre BRUT)."""
        return bool(self._tool[j]) or bool(self.TOOL_LIKE.search(self._title_raw[j]))
    # mots trop generiques pour constituer un "lien de famille" entre deux produits
    GENERIC = {"cable","fil","fils","male","femelle","female","module","kit","pour","avec","vers","set",
        "jeu","jeux","lot","pcs","piece","pieces","broche","broches","pin","pins","noir","blanc","blanche",
        "rouge","bleu","bleue","vert","verte","jaune","gris","rose","digital","numerique","mini","micro",
        "pro","plus","haute","qualite","sans","type","modele","serie","serial","interface","version","couleur","metre","metres",
        "watt","volt","ampere","original","universel","universelle","adaptateur","connecteur",
        "plastique","acier","metal","metallique","inox","aluminium","laiton","nylon","cuivre","silicone",
        "etanche","flexible","longueur","largeur","blanc","noire","petit","grand","nouveau","nouvelle"}
    # Bus / protocoles / connecteurs : ressemblent a des tokens-modele mais ne prouvent AUCUNE famille
    # (un micro I2C et une EEPROM I2C partagent 'i2c' sans etre de la meme famille).
    BUS_WORDS = {"i2c","spi","uart","i2s","ttl","pwm","usb","rj45","spdif","jtag","gpio","rs232","rs485"}
    def _salient(self, j):
        """Tokens 'modele' (lettre+chiffre, ex: esp32, 18650, l298, sg90) -- forte preuve de famille."""
        return {w for w in self._title_raw[j].split()
                if self.STRONG.match(w) and w not in self.BUS_WORDS
                and not re.fullmatch(r'\d+(v|mah|ah|mm|cm|w|a|ma|k)?', w)}
    def _sig_words(self, j):
        return {w for w in self._title_clean[j].split() if len(w)>=4 and w not in self.GENERIC}
    def _family_overlap(self, i, j, min_words=1):
        """Vrai lien de famille : un token-modele partage OU >=min_words mots significatifs partages.
        min_words=2 pour les categories tres bruitees (mobilite) ou un seul mot d'usage (ex 'drone')
        ne suffit pas a faire un substitut (une helice n'est pas un moteur de drone)."""
        if self._salient(i) & self._salient(j): return True
        return len(self._sig_words(i) & self._sig_words(j)) >= min_words
    def _compat_status(self, sa, ja):
        """Statut DETERMINISTE (machine), pas de langage flou : compatible / necessite adaptation."""
        if sa.get("board") and ja.get("board")==sa["board"]: return "compatible (meme carte/MCU)"
        if sa.get("connector") and ja.get("connector")==sa["connector"]: return "compatible (meme connecteur)"
        sd, jd = sa.get("voltage_domain"), ja.get("voltage_domain")
        if sd and jd and sd==jd: return "compatible (meme domaine tension)"
        if sd and jd and sd!=jd: return "necessite adaptation (tension %s vs %s)" % (sd, jd)
        return "compatible (role complementaire dans la chaine systeme)"
    def _spec_diffs(self, i, j):
        """Differences TECHNIQUES entre deux substituts (capacite, tension, puissance, nombre...)."""
        si, sj = self._specs[i] or {}, self._specs[j] or {}
        out=[]
        for k in sorted(set(si)|set(sj)):
            if si.get(k)!=sj.get(k): out.append("%s: %s vs %s" % (k, si.get(k,"?"), sj.get(k,"?")))
        return out[:4]
    def _sim_reason(self, i, j, cat, defining, src_def):
        """Bloc de raisonnement DETERMINISTE pour un SIMILAIRE (= substitut technique)."""
        role=self._attrs[i].get("system_position")
        nature=cat + (" / %s=%s" % (defining, src_def) if (defining and src_def is not None) else "")
        diffs=self._spec_diffs(i, j) or ["variante (parametres proches)"]
        return {"relation":"SIMILAIRE (substitut technique)",
                "role":self.ROLE_LABEL.get(role, role), "system_position":role,
                "physical_nature":nature, "differences":diffs,
                "conclusion":"meme role systeme (%s) + meme nature, parametres differents -> substituable" % role}
    def _comp_reason(self, sa, src_role, j):
        """Bloc de raisonnement DETERMINISTE pour un COMPLEMENT (= maillon de la chaine systeme)."""
        ja=self._attrs[j]; jrole=ja.get("system_position")
        status=self._compat_status(sa, ja)
        return {"relation":"COMPLEMENTAIRE (chaine systeme)",
                "role":self.ROLE_LABEL.get(jrole, jrole), "system_position":jrole,
                "chain_step":"%s -> %s" % (src_role, jrole), "compatibility":status,
                "conclusion":"role DIFFERENT (%s) dans la meme chaine ; %s" % (jrole, status)}
    @staticmethod
    def _kw_hit(tc, kws):
        """Match de mot-cle par MOT ENTIER (evite 'resistance' dans 'photoresistance')."""
        for k in kws:
            if re.search(r'(?<![a-z0-9])'+re.escape(k)+r'(?![a-z0-9])', tc): return True
        return False
    _UNIVERSAL = ("breadboard","plaque essai","dupont","jumper","cavalier")  # le panier de base de TOUT montage
    def _affinity(self, cat, tj):
        """Affinite d'ACHAT (0-0.55) : a quel point ce complement est un achat NATUREL avec la source."""
        table = self.PURCHASE_AFFINITY.get(cat, {})
        a = max((w for k, w in table.items() if k in tj), default=0.0)
        if any(u in tj for u in self._UNIVERSAL): a = max(a, 0.55)   # accessoire universel -> prioritaire
        return a
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
        src_role=self._attrs[i].get("system_position")   # Etape 2 : role de la source dans la chaine
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
            # Substitut = MEME type strict (pas de cross-type) pour les familles ou un attribut
            # definissant distinct = produit non substituable : carte (board), batterie (form_factor),
            # rf (rftech), capteur (un capteur de gaz != un de debit), led (une ampoule != un ruban),
            # mobilite (un vehicule != un autre).
            if cat in ("carte","mobilite","batterie","rf","capteur","led","composant"):
                tier2=[]   # composant : une resistance/diode/diac n'est PAS un substitut d'un condensateur
        else:
            tier1=[j for j in pool if sc[j]>=self.F["SIM_NODEF"]]; tier2=[]
        pk,pv=primary_spec(self._specs[i]); ups=[]
        if pk:
            ups=[j for j in tier1 if primary_spec(self._specs[j])[0]==pk and primary_spec(self._specs[j])[1]>pv]
            ups=sorted(ups, key=lambda j:(primary_spec(self._specs[j])[1], sc[j]), reverse=True)
        rest=sorted([j for j in tier1 if j not in ups], key=lambda j:sc[j], reverse=True)
        tier2=sorted(tier2, key=lambda j:sc[j], reverse=True)
        cand=ups+rest+tier2
        # GARDE-FOU : pour les categories SANS attribut definissant fiable (mecanique, connectique,
        # alimentation... + mobilite dont 'vehicle' est trop grossier), le seul cosinus E5 attrape des
        # produits qui partagent juste des mots de surface (cable DVI pour du Dupont, ecrou pour un
        # boitier). On exige un vrai LIEN DE FAMILLE (token-modele ou mot significatif partage),
        # sinon on ne propose RIEN (mieux vaut vide que faux).
        # Garde-fou "famille" UNIQUEMENT pour les categories ou le seul cosinus attrape des produits
        # qui partagent juste des mots de surface (cable DVI vs Dupont, ecrou vs boitier, drone-moteur
        # vs helice). PAS pour alimentation/mesure : leurs substituts ont des noms varies (multitension
        # / convertisseur / regulateur) sans mot commun mais sont bien substituables -> on garde le cosinus.
        FAMILY_GUARD = ("connectique","mecanique","mobilite","outillage","electrique")
        # electronique SANS attribut definissant (module_fn=None : dimmer, micro, convertisseur de signal)
        # tombe aussi sous garde-fou, sinon le seul cosinus apparie par tension/surface (dimmer -> serrure 12V).
        guard = (cat in FAMILY_GUARD) or (cat=="electronique" and src_def is None)
        if guard and (self._salient(i) or self._sig_words(i)):
            mw = 2 if cat=="mobilite" else 1     # mobilite tres bruitee -> exiger 2 mots communs
            cand=[j for j in cand if self._family_overlap(i, j, min_words=mw)]
        # diversite douce : on retire seulement les RE-LISTINGS quasi-identiques (garde les variantes)
        similars=self._diverse(cand, n, thr=0.985 if not self.is_sparse else 0.97)

        # ===== COMPLEMENTAIRES =====
        # On calcule les complements des que la categorie a des regles (comp_cats non vide).
        # Les vraies categories d'outils (outillage/mecanique/electrique) ont des regles VIDES
        # -> naturellement aucun complement. Mais un objet de marque-outil tombe dans une
        # categorie IoT (ex: fer a souder TOTAL -> 'soudure') garde ses complements (etain/flux).
        comp=[]; comp_scores={}
        comp_cats=self.comp_map.get(cat,[])
        # Source = interconnexion video / produit fini grand public (HDMI/VGA/DVI/Lightning/PS...) :
        # ce n'est PAS le coeur d'un systeme IoT -> aucun complement (sauf une vraie carte MCU).
        if cat!="carte" and self.VIDEO_TERMINAL.search(self._title_raw[i]): comp_cats=[]
        if comp_cats:
            broad=set(self.comp_broad.get(cat,[]))
            ckw=self.comp_keywords.get(cat,[]); excl=self.comp_exclude.get(cat,[])
            volt_ok=cat not in ("batterie","chargeur")
            sdom=sa.get("voltage_domain")          # domaine tension de la source (logic/lv/mains)
            sctx=sa.get("context")                 # contexte d'usage source (drone/robot/rc) -> meme monde
            raw=[]
            for ci,cc in enumerate(comp_cats):
                cc_broad=cc in broad
                for j in self.cat_to_idx.get(cc,[]):
                    # un complement n'est JAMAIS un outil, ni du bruit industriel / domotique batiment
                    if j==i or not ok(j) or self._efftool(j): continue
                    tj=self._title_clean[j]
                    if any(b in tj for b in self.BLACKLIST) or self.COMP_NOISE.search(self._title_raw[j]): continue
                    if excl and any(e in tj for e in excl): continue
                    # REGLE DURE tension : un appareil IoT (logic/lv) ne se complete pas avec du SECTEUR (mains).
                    if self._attrs[j].get("voltage_domain")=="mains" and sdom in ("logic","lv"): continue
                    # REASONING FILTER (chaine systeme) : le role du complement doit etre un maillon
                    # ADJACENT valide du role source (sinon role incoherent -> rejet, ex: ruban LED -> thermostat).
                    jrole=self._attrs[j].get("system_position")
                    if src_role in self.CHAIN_EDGES and jrole not in self.SUPPORT_ROLES \
                       and jrole not in self.CHAIN_EDGES[src_role]: continue
                    jctx=self._attrs[j].get("context")
                    # CONTEXTE D'USAGE : un drone ne se complete pas avec du materiel robot/RC (et inversement).
                    # On filtre les MONDES incompatibles pour les categories ou le contexte est decisif.
                    if sctx and jctx and jctx!=sctx and cat in ("mobilite","moteur","carte","rf"): continue
                    # PROFIL DE CONTEXTE : dans ce contexte+role, exige le bon objet et rejette l'interdit.
                    _prof=self.CONTEXT_PROFILE.get(sctx,{}).get(jrole)
                    if _prof:
                        if any(f in tj for f in _prof["forbid"]): continue
                        if _prof["req"] and not any(r in tj for r in _prof["req"]): continue
                    ja=self._attrs[j]; hard=0.0; qual=False   # qual = a-t-il un VRAI signal de compatibilite ?
                    # ALIMENTATION : la tension doit CONVENIR a la source (un ruban 12V veut du 12V, pas 42V/3V ;
                    # un MCU/capteur logique s'alimente en <=12V, jamais en 42V).
                    if jrole=="alimentation" and ja.get("voltage_bucket"):
                        _svb=sa.get("voltage_bucket")
                        if _svb and ja["voltage_bucket"]!=_svb: continue
                        if (not _svb) and cat in ("carte","capteur","electronique","rf") and ja["voltage_bucket"]>12: continue
                    if sctx and jctx==sctx: hard+=0.5; qual=True   # MEME contexte (drone -> brushless/ESC/LiPo du meme monde)
                    if sa.get("board") and ja.get("board")==sa["board"]: hard+=0.6; qual=True
                    if sa.get("connector") and ja.get("connector")==sa["connector"]: hard+=0.5; qual=True
                    if sa.get("form_factor") and sa["form_factor"] in tj: hard+=0.6; qual=True
                    if sa.get("chemistry") and ja.get("chemistry")==sa["chemistry"]: hard+=0.3; qual=True
                    if self._kw_hit(tj, ckw): hard+=0.5; qual=True
                    if cc_broad: hard+=0.3; qual=True        # categorie compagnon (ex: capteur pour une carte)
                    # La TENSION SEULE ne qualifie PAS (sinon tout produit 12V passe : thermostat, projecteur,
                    # kit acces...). Elle n'est qu'un BONUS de rang quand il y a deja un autre signal.
                    if volt_ok and sa.get("voltage_bucket") and ja.get("voltage_bucket")==sa["voltage_bucket"]: hard+=0.4
                    # AFFINITE D'ACHAT (panier reel) : l'accessoire UNIVERSEL passe devant le composant de niche.
                    aff=self._affinity(cat, tj)
                    if aff>0: hard+=aff; qual=True            # un companion NATUREL qualifie aussi
                    # composant de NICHE (MOSFET/XL6009/opto...) : compatible mais rarement un achat naturel -> demote
                    if cat not in ("composant","electronique") and self.NICHE_COMP.search(self._title_raw[j]): hard-=0.5
                    if not qual or hard<=0: continue          # aucune pertinence reelle -> rejete
                    raw.append((j, min(hard,1.0), ci))
            # Classement par COMPATIBILITE DURE (board/connecteur/mot-cle...), cosinus E5 en tie-break.
            # Le score AFFICHE est cette compatibilite (0-1) : eleve = vrai complement, bas = lien faible.
            order=sorted(raw, key=lambda c:(-c[1], -float(S[c[0]]), c[2]))
            comp_scores={j:h for j,h,_ in order}
            ranked=self._diverse([j for j,_,_ in order], len(order), thr=0.94 if not self.is_sparse else 0.85)
            # DIVERSITE PAR ROLE SYSTEME : couvrir des maillons DIFFERENTS de la chaine
            # (capteur -> 1 carte + 1 afficheur + 1 actionneur + 1 alim, PAS 4 cartes identiques de role).
            # DIVERSITE PAR ROLE, mais 2 connectiques admis (dupont + breadboard = panier naturel d'un montage).
            seen={}; keep=[]
            for j in ranked:
                role=self._attrs[j].get("system_position")
                cap=2 if role=="connectique" else 1
                if seen.get(role,0)>=cap: continue
                seen[role]=seen.get(role,0)+1; keep.append(j)
                if len(keep)>=n: break
            for j in ranked:                       # completer si moins de n maillons distincts
                if j not in keep: keep.append(j)
                if len(keep)>=n: break
            comp=keep[:n]

        allsc={**{j:sc.get(j,float(S[j])) for j in similars}}
        if comp: allsc.update(comp_scores)
        sim_df = self._rows(similars, allsc)
        if len(sim_df):                           # raisonnement DETERMINISTE par similaire (substitut)
            sim_df["reasoning"] = [self._sim_reason(i, j, cat, defining, src_def) for j in similars]
        comp_df = self._rows(comp, allsc)
        if len(comp_df):                          # statut + raisonnement DETERMINISTES par complement
            comp_df["compat_status"] = [self._compat_status(sa, self._attrs[j]) for j in comp]
            comp_df["reasoning"]     = [self._comp_reason(sa, src_role, j) for j in comp]
        return {"source_idx":i,"source_title":self._title[i],"source_cat":cat,"source_attrs":sa,
                "source_role":src_role,"is_tool":bool(stool),"similars":sim_df,"complements":comp_df}
