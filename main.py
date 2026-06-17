# -*- coding: utf-8 -*-
"""
Moteur de recommandation IoT -- APPLICATION LOCALE (VS Code).
  - Lit inventory_export.csv en local.
  - SIMILAIRES = substitut technique ; COMPLEMENTAIRES = chaine systeme + panier reel (regles deterministes).
  - Le LLM LOCAL (Ollama) CHOISIT + EXPLIQUE (gratuit / illimite / prive). Repli moteur si pas de LLM.

Lancer :
  python main.py                     # mode interactif (tape un produit)
  python main.py "Arduino UNO"       # une requete directe
  python main.py "ruban led 12v"     # autre exemple
"""
import os, sys, io
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

# --- .env local (ex: LLM_BASE_URL=http://localhost:11434/v1 pour Ollama) ---
def _load_env(path=".env"):
    if not os.path.exists(path): return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
_load_env()

import reco_v2 as R
from llm_layer import recommend_expert, llm_provider, llm_chat

USE_LLM = True   # True = explications par le LLM local (Ollama) ; False = moteur seul (deterministe)

print("Construction du moteur (lecture inventory_export.csv)...")
products, rule_maps = R.build_products(verbose=True)
engine = R.SmartRecoEngine(products, rule_maps, verbose=True)

# --- detection/test du LLM ---
_p = llm_provider() if USE_LLM else None
if _p:
    try:
        llm_chat("ping", max_tokens=3)
        print(f"\nOK  LLM ACTIF : {_p}  ->  les recommandations seront expliquees par le LLM.\n")
    except Exception as e:
        print(f"\n[!] LLM detecte ({_p}) mais inactif ({type(e).__name__}) -> MOTEUR SEUL.\n"); _p = None
elif USE_LLM:
    print("\n[i] Aucun LLM detecte. Pour l'activer : installe Ollama, puis  'ollama pull qwen2.5:7b'  (ou 3b).")
    print("    Tant qu'il n'y a pas de LLM, on tourne en MOTEUR SEUL (deterministe, toujours fonctionnel).\n")


def show_smart(query, n=6, in_stock_only=False):
    """Affiche SIMILAIRES + COMPLEMENTAIRES. Avec LLM : choix + justification ; sinon moteur seul."""
    use = bool(_p)
    res = (recommend_expert(engine, query, n=n, in_stock_only=in_stock_only) if use
           else engine.recommend(query, n=n, in_stock_only=in_stock_only))
    if res is None:
        print("X  Produit introuvable :", query); return
    tag = f"  [cerveau IoT: {res.get('mode_sim','moteur')}]" if use else "  [moteur seul]"
    print("=" * 100)
    print("SELECTION : " + str(res["source_title"])[:80] +
          f"   [{res['source_cat']} | role: {res.get('source_role')}]" + tag)
    print("=" * 100)
    for titre, dfb, sc in [("PRODUITS SIMILAIRES", res["similars"], "sim"),
                           ("PRODUITS COMPLEMENTAIRES", res["complements"], "compat")]:
        print("\n" + titre + " :")
        if dfb is None or len(dfb) == 0:
            print("   (aucun)"); continue
        for _, r in dfb.iterrows():
            cat = str(r["category"])[:12]; t = str(r["product_title"])[:54]
            head = (f"   - [{cat:<12}] {t:<54}  confiance={int(r['confidence'])}/100"
                    if "confidence" in dfb.columns else
                    f"   - [{cat:<12}] {t:<54}  {sc}={float(r['score']):.2f}")
            chaine = ""
            rz = r["reasoning"] if "reasoning" in dfb.columns else None
            if isinstance(rz, dict):
                chaine = ("  | " + rz.get("chain_step", "")) if sc == "compat" else ("  | role: " + str(rz.get("system_position", "")))
            statut = "  | " + str(r["compat_status"]) if "compat_status" in dfb.columns else ""
            raison = str(r["raison"]) if "raison" in dfb.columns and str(r.get("raison", "")) else ""
            print(head + chaine + statut + ("\n        -> " + raison if raison else ""))
    print()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        show_smart(" ".join(sys.argv[1:]))
    else:
        print("Tape un nom de produit (titre, handle ou SKU). 'quit' pour sortir.")
        print("Exemples : Arduino UNO  |  DHT11  |  ruban led rgb 12v  |  batterie 18650\n")
        while True:
            try:
                q = input("Produit > ").strip()
            except (EOFError, KeyboardInterrupt):
                print(); break
            if q.lower() in ("quit", "exit", "q", ""):
                break
            show_smart(q)
