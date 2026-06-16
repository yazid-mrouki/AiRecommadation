# Moteur de recommandation IoT — similaires & complémentaires

Moteur qui parcourt l'inventaire (`inventory_export.csv`) et, pour un produit donné,
recommande :
- les **produits similaires** (substituts du même type),
- les **produits complémentaires** (à acheter avec, d'une autre famille).

Tout est piloté par des règles **éditables** (`regles_recommandation.csv`) et un modèle d'IA sémantique.

## Architecture (v2)

| Étage | Choix | Pourquoi |
|------|-------|----------|
| Catégorisation | règles mots-clés + repli plus-proche-voisin TF-IDF | 0 % de « autre » |
| Attributs | extraction (form_factor, board, chimie, tension, capteur…) | comparer le *type* |
| Recherche produit | exact handle/SKU/titre → sous-chaîne → **sémantique** → fuzzy | ne renvoie plus « introuvable » |
| Similaires | même famille + garde-fou attribut **définissant** + **re-ranking cross-encoder** | précision *et* rappel |
| Complémentaires | compatibilité « dure » (board/connecteur/tension/mot-clé) + plancher sémantique + diversité | compagnons pertinents, pas de bruit |

**Modèles** (téléchargés automatiquement, gratuits) :
- Embeddings : `intfloat/multilingual-e5-base` (multilingue, FR).
- Re-ranking : `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`.
- Repli automatique **TF-IDF** si `sentence-transformers` indisponible (hors-ligne).

> Le cross-encoder n'est utilisé QUE pour les **similaires** (similarité même-sujet).
> Les **complémentaires** sont d'une autre famille par design → le CE les pénaliserait,
> on les classe donc par compatibilité dure + embeddings.

## Résultats mesurés

Jeu de test **étiqueté** (`eval_gold.py`, 24 cas ancrés sur le catalogue) + test de rappel
automatique objectif (siblings par token-modèle partagé sur tout le catalogue).

| Configuration | Précision globale (gold) | Similaires | Rappel siblings@3 | Fautes graves |
|---|---|---|---|---|
| Ancien moteur (éval à la main, 14 cas) | ~77 % | — | — | plusieurs |
| Nouveau — TF-IDF (repli) | 91 % | 94 % | 71 % | 0 |
| Nouveau — sémantique E5 | 98 % | 100 % | 82 % | 0 |
| **Nouveau — E5 + cross-encoder** | **≈98 %** | **100 %** | **95 %** | **0** |

## Utilisation

```python
# dans le notebook AIRecommendationEngine_IoT.ipynb (Colab)
show_smart("ESP32")
show_smart("Batterie 18650")
evaluer()   # affiche la precision mesuree sur le jeu de test
```

Reproduire les métriques hors notebook :
```bash
pip install pandas numpy scikit-learn sentence-transformers rapidfuzz
python eval_harness.py rerank     # E5 + cross-encoder
python eval_harness.py semantic   # E5 seul
python eval_harness.py tfidf      # repli hors-ligne
```

## Régler le moteur

Édite `regles_recommandation.csv` (une ligne par catégorie) :
`complement_categories`, `complement_mots_cles`, `exclure_mots_cles` (blacklist),
`attributs_similaire`. Puis ré-exécute à partir de l'étape moteur.
