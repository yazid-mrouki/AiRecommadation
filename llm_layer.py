# -*- coding: utf-8 -*-
"""
Couche LLM "expert humain" par-dessus le moteur embeddings.
  - Le moteur recupere des CANDIDATS propres (embeddings + regles).
  - Le LLM CHOISIT les meilleurs + EXPLIQUE, comme un vendeur expert IoT.
  - Il ne pioche QUE dans les candidats reels -> aucune invention de produit.
Multi-fournisseurs (auto-detecte la cle dispo) : Gemini / Groq / Anthropic / OpenAI / Hugging Face.
Repli automatique sur le classement du moteur si aucun LLM ou en cas d'erreur.
"""
import os, re, json, urllib.request

# --- Detection d'un LLM AUTO-HEBERGE (Ollama / vLLM / LM Studio / LocalAI...) :
#     gratuit, ILLIMITE (pas de quota d'API), PRIVE (les donnees ne sortent pas du serveur).
#     Pour la societe : faire tourner Ollama sur un serveur interne et pointer LLM_BASE_URL dessus.
_LOCAL_URL = None
def _local_url():
    global _LOCAL_URL
    if _LOCAL_URL is not None: return _LOCAL_URL
    url = os.environ.get("LLM_BASE_URL")            # ex: http://mon-serveur:11434/v1
    if url:
        _LOCAL_URL = url.rstrip("/"); return _LOCAL_URL
    try:                                            # auto-detection d'Ollama sur le port par defaut
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=0.6)
        _LOCAL_URL = "http://localhost:11434/v1"
    except Exception:
        _LOCAL_URL = ""
    return _LOCAL_URL

def _providers_available():
    """Liste ORDONNEE des providers reellement configures (pour la cascade : si l'un sature, on prend le suivant)."""
    out = []
    if _local_url():                        out.append("local")    # prive + illimite -> en tete
    if os.environ.get("GEMINI_API_KEY"):    out.append("gemini")
    if os.environ.get("GROQ_API_KEY"):      out.append("groq")
    if os.environ.get("ANTHROPIC_API_KEY"): out.append("anthropic")
    if os.environ.get("OPENAI_API_KEY"):    out.append("openai")
    if os.environ.get("HF_TOKEN"):          out.append("hf")
    return out
def llm_provider():
    provs = _providers_available()
    return provs[0] if provs else None
_LAST_PROVIDER = None      # provider qui a REELLEMENT repondu (pour le tag d'affichage)

HF_MODEL    = "meta-llama/Llama-3.3-70B-Instruct"
LOCAL_MODEL = os.environ.get("LLM_MODEL", "qwen2.5:7b-instruct")   # modele Ollama par defaut

# --- ROTATION multi-cles Groq : plusieurs cles gratuites -> quand une SATURE (429), bascule auto
#     vers la suivante (multiplie le quota). Nomme-les GROQ_API_KEY, GROQ_API_KEY_2, _3...
#     (ou une seule GROQ_API_KEYS="k1,k2,k3").
_GROQ_ROT = 0
def _groq_keys():
    ks = [os.environ.get("GROQ_API_KEY")] + [os.environ.get("GROQ_API_KEY_%d" % n) for n in range(2, 9)]
    if os.environ.get("GROQ_API_KEYS"): ks += os.environ["GROQ_API_KEYS"].split(",")
    seen, out = set(), []
    for k in ks:
        k = (k or "").strip()
        if k and k not in seen: seen.add(k); out.append(k)
    return out
def _is_rate_limit(e):
    m = str(e).lower()
    return any(t in m for t in ("429", "rate limit", "rate_limit", "quota", "too many", "exceed"))
def _groq_call(prompt, max_tokens, temperature):
    global _GROQ_ROT
    import time
    from openai import OpenAI
    keys = _groq_keys()
    if not keys: raise RuntimeError("aucune cle Groq")
    # modele LEGER par defaut = larges limites gratuites (evite le 429 du 70B sur des rafales d'appels).
    model = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")
    last = None
    for rnd in range(3):                               # quelques tours avec back-off si TOUTES saturees
        for off in range(len(keys)):
            idx = (_GROQ_ROT + off) % len(keys)
            try:
                c = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=keys[idx])
                r = c.chat.completions.create(model=model,
                      messages=[{"role":"user","content":prompt}], max_tokens=max_tokens, temperature=temperature)
                _GROQ_ROT = idx                        # reste sur la cle qui marche
                return r.choices[0].message.content
            except Exception as e:
                last = e
                if _is_rate_limit(e): continue         # cle saturee -> cle suivante
                raise                                  # autre erreur (mauvaise cle/reseau) -> remonte
        time.sleep(2.0 * (rnd + 1))                    # toutes saturees -> on patiente (fenetre/minute) puis retry
    _GROQ_ROT = (_GROQ_ROT + 1) % len(keys)
    raise last

_PROVIDER_ROT = 0
def llm_chat(prompt, max_tokens=700, temperature=0.2, retries=1):
    """ROUND-ROBIN + FAILOVER : repartit la charge sur TOUS les providers cloud configures (gemini/groq/hf)
    -> leurs quotas gratuits s'ADDITIONNENT ; si l'un SATURE (429), on passe au suivant. 'local' (Ollama)
    est illimite -> on le garde en tete sans rotation. _LAST_PROVIDER = celui qui a repondu (pour le tag)."""
    global _LAST_PROVIDER, _PROVIDER_ROT
    import time
    provs = _providers_available()
    if not provs: raise RuntimeError("Aucun LLM configure")
    if provs[0] == "local":                          # Ollama illimite -> toujours en premier
        ordered = provs
    else:                                            # cloud -> on tourne le point de depart a chaque appel
        nprov = len(provs)
        ordered = [provs[(_PROVIDER_ROT + k) % nprov] for k in range(nprov)]
        _PROVIDER_ROT = (_PROVIDER_ROT + 1) % nprov
    last = None
    for prov in ordered:
        for attempt in range(retries + 1):
            try:
                r = _call_provider(prov, prompt, max_tokens, temperature)
                _LAST_PROVIDER = prov
                return r
            except Exception as e:
                last = e
                if _is_rate_limit(e): break          # provider sature/quota -> provider SUIVANT
                if attempt < retries: time.sleep(2.0)
                else: break
    raise last

def _call_provider(p, prompt, max_tokens=700, temperature=0.2):
    if p == "local":    # serveur LLM PRIVE auto-heberge (Ollama/vLLM/LM Studio) -- gratuit, illimite
        from openai import OpenAI
        c = OpenAI(base_url=_local_url(), api_key=os.environ.get("LLM_API_KEY", "ollama"))
        r = c.chat.completions.create(model=LOCAL_MODEL,
              messages=[{"role":"user","content":prompt}], max_tokens=max_tokens, temperature=temperature)
        return r.choices[0].message.content
    if p == "gemini":   # endpoint OpenAI-compatible de Google -> un seul SDK (openai) pour 3 fournisseurs
        from openai import OpenAI
        c = OpenAI(base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                   api_key=os.environ["GEMINI_API_KEY"])
        r = c.chat.completions.create(model=os.environ.get("GEMINI_MODEL", "gemini-2.0-flash"),
              messages=[{"role":"user","content":prompt}], max_tokens=max_tokens, temperature=temperature)
        return r.choices[0].message.content
    if p == "groq":
        return _groq_call(prompt, max_tokens, temperature)   # rotation multi-cles (429 -> cle suivante)
    if p == "anthropic":
        import anthropic
        c = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        r = c.messages.create(model="claude-3-5-haiku-latest", max_tokens=max_tokens,
              messages=[{"role":"user","content":prompt}])
        return r.content[0].text
    if p == "openai":
        from openai import OpenAI
        c = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        r = c.chat.completions.create(model="gpt-4o-mini",
              messages=[{"role":"user","content":prompt}], max_tokens=max_tokens, temperature=temperature)
        return r.choices[0].message.content
    if p == "hf":
        from huggingface_hub import InferenceClient
        c = InferenceClient(model=HF_MODEL, token=os.environ["HF_TOKEN"])
        r = c.chat_completion(messages=[{"role":"user","content":prompt}],
              max_tokens=max_tokens, temperature=temperature)
        return r.choices[0].message.content
    raise RuntimeError("Aucun LLM configure")

def _parse_json(text):
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if not m: return []
    try: return json.loads(m.group(0))
    except Exception:
        try: return json.loads(m.group(0).replace("'", '"'))
        except Exception: return []

# Definitions de niveau INGENIEUR (pas du simple "meme rayon") :
_KINDDEF = {
 "similaires": (
   "Un SIMILAIRE = MEME objet physique + MEME fonction EXACTE + MEME role systeme + MEME usage reel "
   "+ MEMES interfaces. PAS 'meme domaine', PAS 'meme categorie'. "
   "TEST : un ingenieur peut-il echanger A<->B SANS changer le projet ? Si NON -> rejette. "
   "Ex DHT11 : OUI={DHT22, AM2302, SHT31} ; NON={thermostat (=systeme complet), capteur temp corporelle, ecran}. "
   "Ex ESP32 : OUI={ESP32-S3, ESP8266, NodeMCU} ; NON={module relais ESP32, capteur, ecran}. "
   "Ex Ruban LED RGB 12V : OUI={ruban RGB 12V, RGBW 12V, ruban adressable} ; NON={alimentation 12V (=complement, pas similaire)}."),
 "complementaires": (
   "Un COMPLEMENTAIRE participe a la MEME CHAINE SYSTEME REELLE et au MEME CONTEXTE d'usage. "
   "Question d'expert : que l'utilisateur achete-t-il juste AVANT/APRES pour le MEME montage ? "
   "Le CONTEXTE est decisif : drone != robot != domotique != automobile. "
   "Ex DHT11 : {Arduino/ESP32, ecran LCD, breadboard, cables dupont}. "
   "Ex Ruban LED RGB : {alimentation 12V, controleur RGB, connecteurs LED, amplificateur RGB}. "
   "Ex Helice DRONE : {moteur brushless, ESC, batterie LiPo, controleur de vol} -- "
   "PAS un servo generique, PAS une Air Mouse, PAS un Sonoff domotique. "
   "Si le produit n'est PAS du meme contexte/chaine -> rejette."),
}

def llm_pick(source_title, source_cat, df, kind, n=6, source_attrs=None):
    """df = candidats (pre-filtres par le moteur). Le LLM raisonne en ARCHITECTE IoT : il VALIDE la
    compatibilite (regles dures), rejette le hors-systeme, classe, justifie FACTUELLEMENT. Pioche que dans df."""
    if df is None or len(df) == 0: return df, "vide"
    titres = list(df["product_title"])
    def _cand(i):                                # candidat STRUCTURE : categorie + role -> le LLM raisonne mieux
        row = df.iloc[i]
        rz = row.get("reasoning") if "reasoning" in df.columns else None
        role = rz.get("system_position", "?") if isinstance(rz, dict) else "?"
        return f"{i+1}. [{str(row.get('category','?'))[:11]} | {role}] {row['product_title']}"
    lignes = "\n".join(_cand(i) for i in range(len(titres)))
    attrs_txt = ", ".join(f"{k}={v}" for k,v in (source_attrs or {}).items()) or "(non specifie)"
    prompt = (
      f"Tu es un ARCHITECTE IoT SENIOR. Tu raisonnes par REGLES TECHNIQUES (tension, protocole/bus, "
      f"type d'E/S, architecture MCU), pas par mots-cles ni par usage imagine.\n\n"
      f'PRODUIT REGARDE : "{source_title}"  (famille: {source_cat} ; specs: {attrs_txt})\n\n'
      f"CANDIDATS (du meme magasin, deja pre-filtres) :\n{lignes}\n\n"
      f"{_KINDDEF[kind]}\n\n"
      f"REGLES DURES (a appliquer STRICTEMENT) :\n"
      f"- Compatibilite TENSION : 3.3 V / 5 V logique ne se melange pas avec 220 V / industriel.\n"
      f"- Compatibilite PROTOCOLE/E-S : I2C/SPI/UART/analogique doivent etre coherents.\n"
      f"- ARCHITECTURE : ESP32, Arduino (AVR), STM32, Raspberry NE sont PAS des substituts directs "
      f"(architectures differentes) -> seulement la MEME famille est 'similaire'.\n"
      f"- HORS-SYSTEME INTERDIT : ne propose pas un produit qui n'appartient pas reellement au systeme "
      f"(ex: ecran TFT n'est PAS un complement d'un ruban LED ; un micro n'est PAS un complement d'un DHT11).\n"
      f"- CONTEXTE D'USAGE DECISIF : drone/FPV != robot/RC != domotique != automobile. Un complement doit etre "
      f"du MEME monde (ex: helice de DRONE -> moteur brushless / ESC / batterie LiPo / controleur de vol ; "
      f"JAMAIS un servo generique, une Air Mouse ou un Sonoff domotique).\n"
      f"- MONDE COHERENT : si le PRODUIT REGARDE est un produit FINI grand-public (telecommande TV, enceinte "
      f"Bluetooth, detecteur de fumee autonome, montre) ou NON-electronique (peinture, gaine, nettoyant), ne "
      f"propose PAS de module maker nu (Arduino, capteur, ESP32, breadboard) : mondes differents -> REJETTE.\n"
      f"- PANIER REEL (pertinence > compatibilite) : propose ce qu'un humain achete NATURELLEMENT avec ce "
      f"produit (accessoires UNIVERSELS : breadboard, cables dupont, ecran LCD/OLED, alimentation adaptee, "
      f"capteurs/relais courants), PAS un composant de NICHE juste 'compatible' (un seul MOSFET BSS138, un "
      f"convertisseur XL6009) sauf s'il est vraiment central au montage. 'compatible' != 'achat naturel'.\n"
      f"- DISTANCE LIMITEE : un complement doit etre dans la MEME chaine systeme, a 2 sauts max "
      f"(capteur->carte->afficheur OK ; capteur->moteur direct INTERDIT).\n"
      f"- JUSTIFICATION par les ATTRIBUTS SAILLANTS du produit (ruban LED: tension / RGB-RGBW / longueur ; "
      f"carte: architecture / tension logique / interfaces ; capteur: grandeur mesuree / interface / precision ; "
      f"batterie: chimie / tension / capacite), PAS 'compatible tension et protocole' generique. "
      f"LEXIQUE STRICT : 'compatible' / 'non compatible' / 'necessite adaptation (<raison>)'. "
      f"BANNIS 'peut servir a', 'pourrait', 'dans certains cas', 'utilisable pour' : jamais d'usage invente.\n"
      f"REGLES DE SORTIE :\n"
      f"- UNIQUEMENT dans la liste, par numero. N'invente AUCUN produit.\n"
      f"- PRECISION AVANT QUANTITE : donne 1 a 3 recommandations PARFAITES (confidence >= 80). "
      f"Si AUCUN candidat n'est vraiment valide, renvoie une liste VIDE []. JAMAIS de remplissage (max {n}).\n"
      f"- confidence 0-100 = certitude de COMPATIBILITE reelle (pas une impression).\n"
      f'Reponds en JSON STRICT, rien d\'autre :\n'
      f'[{{"n": <numero>, "confidence": <70-100>, "raison": "<relation technique factuelle, 1 phrase>"}}]'
    )
    try:
        data = _parse_json(llm_chat(prompt, max_tokens=900))
        rows, seen = [], set()
        for d in data:
            k = int(d.get("n", 0)) - 1
            if 0 <= k < len(titres) and k not in seen:
                try: conf = int(float(d.get("confidence", 80)))
                except Exception: conf = 80
                conf = max(0, min(100, conf))
                if conf < 70: continue          # REGLE DURE : on ne garde que la compatibilite reelle (>=70)
                seen.add(k); rows.append((k, conf, str(d.get("raison","")).strip()))
            if len(rows) >= n: break
        if not rows: raise ValueError("aucun choix LLM valide")
        out = df.iloc[[k for k,_,_ in rows]].copy()
        out["confidence"] = [c for _,c,_ in rows]
        out["raison"]     = [r for _,_,r in rows]
        return out.reset_index(drop=True), "llm:" + (_LAST_PROVIDER or llm_provider() or "?")
    except Exception as e:                              # REPLI : classement du moteur (score -> confiance)
        out = df.head(n).copy()
        out["confidence"] = (out["score"]*100).round().clip(0,100).astype(int) if "score" in out.columns else 70
        out["raison"] = ""
        return out.reset_index(drop=True), f"repli-moteur ({type(e).__name__})"

def recommend_expert(engine, query, n=6, pool=12, in_stock_only=True):
    """n = nb final (4-8 conseille). pool = nb de candidats fournis au LLM (le moteur pre-filtre)."""
    res = engine.recommend(query, n=pool, in_stock_only=in_stock_only)
    if res is None: return None
    sa = res.get("source_attrs")
    sim, sm = llm_pick(res["source_title"], res["source_cat"], res["similars"], "similaires", n, source_attrs=sa)
    comp, cm = llm_pick(res["source_title"], res["source_cat"], res["complements"], "complementaires", n, source_attrs=sa)
    res["similars"], res["complements"] = sim, comp
    res["mode_sim"], res["mode_comp"] = sm, cm
    return res
