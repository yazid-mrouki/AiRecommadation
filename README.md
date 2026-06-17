# Moteur de recommandation IoT (projet local)

Recommande, pour un catalogue de ~5774 produits IoT/électronique, des produits **similaires**
(substitut technique) et **complémentaires** (chaîne système réelle + panier d'achat), avec un
raisonnement de niveau **ingénieur IoT**.

- **Moteur déterministe** (règles + embeddings E5) : ~99 % de précision sur le jeu de test, 0 faute.
- **Cerveau LLM local** (Ollama) optionnel : choisit les meilleurs + explique, **gratuit / illimité / privé**.

---

## 1. Installation (VS Code, Windows/Mac/Linux)

```bash
# dans le dossier du projet
python -m venv .venv
# Windows :
.venv\Scripts\activate
# Mac/Linux :
source .venv/bin/activate

pip install -r requirements.txt
```

> Windows : si erreur **SSL** au 1er téléchargement du modèle E5 → `pip install pip-system-certs`.

Le 1er lancement télécharge le modèle d'embeddings (~1 Go, une seule fois) et met en cache les
vecteurs (`_emb_*.npy`) → les lancements suivants sont rapides.

---

## 2. LLM local avec Ollama (recommandé — zéro quota)

```bash
# 1) installe Ollama : https://ollama.com/download
# 2) télécharge un modèle (Apache-2.0, usage commercial OK) :
ollama pull qwen2.5:7b       # ou  qwen2.5:3b  si peu de RAM
# 3) Ollama tourne en service ; sinon :
ollama serve
```

Ollama sur `localhost:11434` est **auto-détecté** : rien à configurer. Sans Ollama, le moteur
tourne **seul** (déterministe).

---

## 3. Lancer

```bash
python main.py                      # mode interactif : tape un produit
python main.py "Arduino UNO"        # une requête directe
python main.py "ruban led rgb 12v"
python main.py "DHT11"
```

Sortie : SIMILAIRES + COMPLÉMENTAIRES avec rôle système, chaîne, et (si LLM) justification.
Tag `[cerveau IoT: llm:local]` = LLM actif ; `[moteur seul]` = mode déterministe.

---

## 4. Évaluer la précision

```bash
python eval_harness.py semantic     # précision sur le jeu de test étiqueté (gold) + recall siblings
```

---

## Fichiers

| Fichier | Rôle |
|---|---|
| `main.py` | application (interactif + requête) |
| `reco_v2.py` | moteur : recherche, similaires, compléments, scoring (rôle système / contexte / panier) |
| `pipeline_categorize.py` | catégorisation + attributs + rôle système + contexte |
| `pipeline_refine.py` | affinage des catégories |
| `pipeline_rules.py` | règles de complémentarité (génère `regles_recommandation.csv`, éditable) |
| `llm_layer.py` | cerveau LLM (Ollama local en priorité ; Groq/Gemini/HF en secours, round-robin) |
| `cluster_pipeline.py` | couche clusters (substitut_key) + export `product_clusters.json` |
| `eval_gold.py` / `eval_harness.py` | jeu de test étiqueté + mesure |
| `inventory_export.csv` | catalogue (entrée) |

Config LLM : copie `.env.example` → `.env` (optionnel ; Ollama local est auto-détecté).
