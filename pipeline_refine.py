# === Affinage des categories (matching sur titre NORMALISE : sans accents/ponctuation) ===
_tn = df["product_title"].map(norm_raw)

# ============================================================================
# 0) FAUTE "POUR <board>" : un ACCESSOIRE pour Arduino/ESP/RPi mal range en 'carte'
#    (ex: "jeux de fils ... pour arduino") -> remis dans sa VRAIE famille.
#    On ne touche PAS aux vraies cartes (uno/nano/mega/wroom/dev kit) ni au "+ cable" final.
# ============================================================================
_pour = _tn.str.contains(r"pour (arduino|esp32|esp8266|raspberry|rpi|micro ?bit|stm32|nodemcu)|compatible (arduino|raspberry)", na=False)
_board_noun = _tn.str.contains(r"\buno\b|\bnano\b|\bmega\b|wroom|wrover|dev.?kit|carte de developpement|leonardo|\bpico\b|atmega|esp32 s3|esp32 c3|esp 12|jetson", na=False)
_acc = (df["category"]=="carte") & _pour & (~_board_noun)
df.loc[_acc, "category"] = "connectique"                                                                      # defaut : cables / fils
df.loc[(df["category"]=="connectique") & _pour & _tn.str.contains(r"\becran\b|afficheur|\blcd\b|oled|matrice|shield|bouclier|module", na=False), "category"] = "electronique"
df.loc[(df["category"]=="connectique") & _pour & _tn.str.contains(r"boitier|coque|housse|dissipateur|\bsupport\b|ventilateur|radiateur", na=False), "category"] = "mecanique"
df.loc[(df["category"]=="connectique") & _pour & _tn.str.contains(r"\bchargeur\b|\balimentation\b|adaptateur secteur|transformateur", na=False), "category"] = "alimentation"
# retirer le faux board de ces accessoires (sinon ils matchent les cartes a tort)
for _i in df.index[_acc]:
    _a = dict(df.at[_i, "attrs"]); _a["board"] = None; df.at[_i, "attrs"] = _a

# 1) AUDIO (enceintes, transmetteur FM, recepteur audio) -> 'audio'
_audio = _tn.str.contains(r"haut parleur|enceinte|speaker|soundtech|barre de son|"
                          r"transmetteur fm|transmetteur audio|adaptateur audio|recepteur audio|mains libre", na=False)
df.loc[_audio, "category"] = "audio"

# 2) INDUSTRIEL (automates, PLC, disjoncteurs...) -> 'electrique' (aucun complement IoT)
_indus = _tn.str.contains(r"automate|simatic|s7 1200|s7 200|s7 300|\bplc\b|industrial|industruino|"
                          r"disjoncteur|contacteur|sectionneur|variateur|profibus|\bvfd\b|triphas", na=False)
df.loc[_indus, "category"] = "electrique"

# 3) OUTILS (moteur auto + electroportatif) dans 'moteur' -> 'outillage'
_tool = _tn.str.contains(r"compressiometre|compression moteur|soupape|depose|calage|distribution|vilebrequin|"
                         r"culasse|injecteur|support moteur|cale moteur|extracteur|arrache|demonte|"
                         r"cle a choc|visseuse|perceuse|meuleuse|disqueuse|cisaille|souffleur|ponceuse|rabot|"
                         r"\bscie\b|testeur.*moteur", na=False)
df.loc[_tool & (df["category"]=="moteur"), "category"] = "outillage"

# 4) Cartes de developpement (camera incluse) -> 'carte'
_devboard = (_tn.str.contains(r"carte de developpement|carte developpement|dev board|dev kit|wroom|wrover|nodemcu|esp32 cam|esp cam", na=False)
             & _tn.str.contains(r"esp32|esp8266|esp 12|arduino|raspberry|stm32|rp2040|pico|microbit", na=False))
df.loc[_devboard, "category"] = "carte"

# 4b) Une carte ESP32/ESP8266 SANS fonction de module = une CARTE
_espcard = df["attrs"].apply(lambda a: a.get("board") in ("esp32","esp8266","rp2040") and a.get("module_fn") is None) \
           & df["category"].isin(["capteur","rf","electronique"])
df.loc[_espcard, "category"] = "carte"

# 5) Accessoires de BATTERIE -> vraie categorie
df.loc[_tn.str.contains(r"\btesteur\b", na=False) & (df["category"]=="batterie"), "category"] = "mesure"
df.loc[_tn.str.contains(r"\bbms\b|carte de protection|protection batterie", na=False) & (df["category"]=="batterie"), "category"] = "composant"
df.loc[_tn.str.contains(r"boitier|power bank|porte pile", na=False) & (df["category"]=="batterie"), "category"] = "mecanique"

# 6) FPGA / Altera ne sont PAS des Arduino -> corriger le faux attribut board
_fpga = _tn.str.contains(r"fpga|altera|cyclone|spartan|xilinx|lattice", na=False)
for _i in df.index[_fpga]:
    _a = dict(df.at[_i, "attrs"]); _a["board"] = "fpga"; df.at[_i, "attrs"] = _a

# 7) Panneau solaire mal classe : le mot "panneau" CONTIENT "panne" (mot-cle soudure) -> faux match.
_solpan = _tn.str.contains(r"panneau solaire|panneau photovolta|cellule solaire|mono ?cristallin|polycristallin|module solaire", na=False)
df.loc[_solpan, "category"] = "solaire"

# 8) Condensateurs CBB61/CBB65 (ventilateur/demarrage/climatiseur) mal classes 'moteur' -> composant (secteur 220/450V).
_cbb = _tn.str.contains(r"\bcbb6\d\b|condensateur.*(ventilateur|demarrage|moteur|climatiseur)", na=False) & (df["category"]=="moteur")
df.loc[_cbb, "category"] = "composant"

# 9) Faux 'moteur' : rapporteur d'angle (mesure), pompe nettoyant/tuyau/boite vide (outillage/mecanique).
df.loc[_tn.str.contains(r"rapporteur", na=False) & (df["category"]=="moteur"), "category"] = "mesure"
df.loc[_tn.str.contains(r"nettoyant|tuyau|boite vide|separation d ecran", na=False) & (df["category"]=="moteur"), "category"] = "outillage"

_nb_acc = int(_acc.sum())
print(f"OK Affinage : {_nb_acc} accessoires 'pour <board>' reclasses + audio/industriel/outils/ESP/batterie/FPGA + solaire/CBB")