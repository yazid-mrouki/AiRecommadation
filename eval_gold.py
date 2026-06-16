# -*- coding: utf-8 -*-
"""
Jeu de test ETIQUETE (gold standard) -- focalise sur le coeur IoT du catalogue.
Tokens en minuscules SANS accents (comparaison sur clean_title normalise).
Pour chaque cas :
  q          : requete (resolue par la recherche robuste du moteur)
  cat        : categorie attendue de la source (controle de categorisation)
  sim_ok     : un SIMILAIRE est correct si son titre contient >=1 de ces tokens
  comp_cats  : categories AUTORISEES pour un complement
  comp_good  : >=1 complement retourne devrait contenir un de ces tokens (pertinence)
  comp_bad   : aucun complement ne doit contenir un de ces tokens (faute grave)
"""
GOLD = [
 # ---------------- batteries / piles ----------------
 dict(q="Batterie Lithium 18650 3.7V 2600mAh", cat="batterie",
      sim_ok=["18650"], comp_cats=["chargeur","composant","mecanique","connectique"],
      comp_good=["chargeur","18650","bms","support","porte pile","boitier"],
      comp_bad=["diode","triac","resistance","ruban","moteur","foret","disjoncteur"]),
 dict(q="PILE GPU AA ULTRA PLUS BP4", cat="batterie",
      sim_ok=["aa","lr6","pile"], comp_cats=["chargeur","composant","mecanique","connectique"],
      comp_good=["chargeur","support","porte pile","boitier"],
      comp_bad=["diode","triac","ruban led","moteur","foret"]),
 dict(q="PILE RECHARGEABLE D RL20 4500 MAH", cat="batterie",
      sim_ok=["rl20","pile","rechargeable"], comp_cats=["chargeur","composant","mecanique","connectique"],
      comp_good=["chargeur","support","boitier"], comp_bad=["triac","ruban","foret","disjoncteur"]),
 # ---------------- cartes / MCU ----------------
 dict(q="Carte de développement Arduino Nano Officiel", cat="carte",
      sim_ok=["arduino","nano","uno","mega","atmega","leonardo"],
      comp_cats=["capteur","connectique","alimentation","led","electronique","composant"],
      comp_good=["dupont","breadboard","capteur","ecran","lcd","oled","resistance","alimentation","relais"],
      comp_bad=["foret","perceuse","disjoncteur","fpga","altera","cle a choc","visseuse"]),
 dict(q="Kit de Démarrage ESP32 Développement IoT WiFi Bluetooth", cat="carte",
      sim_ok=["esp32","esp8266","wroom","nodemcu"],
      comp_cats=["capteur","connectique","alimentation","led","electronique","composant"],
      comp_good=["dupont","breadboard","capteur","ecran","oled","lcd","relais","alimentation"],
      comp_bad=["foret","perceuse","disjoncteur","fpga","altera","visseuse"]),
 dict(q="Raspberry Pi Zero 2 W avec connecteurs", cat="carte",
      sim_ok=["raspberry","pi","rpi"],
      comp_cats=["capteur","connectique","alimentation","led","electronique","composant"],
      comp_good=["micro sd","carte memoire","dissipateur","alimentation","boitier","dupont","ecran"],
      comp_bad=["foret","perceuse","disjoncteur","fpga","altera"]),
 # ---------------- capteurs ----------------
 dict(q="Capteur de gaz SGP30 qualité de l air", cat="capteur",
      sim_ok=["capteur","gaz","sgp30","co2","mq","tvoc"],
      comp_cats=["carte","connectique","electronique"],
      comp_good=["arduino","esp32","raspberry","dupont","ecran","lcd","oled"],
      comp_bad=["foret","perceuse","fpga","altera","cle a choc"]),
 dict(q="Capteur de débit d eau YF-S401 débitmètre", cat="capteur",
      sim_ok=["capteur","debit","yf","debitmetre"],
      comp_cats=["carte","connectique","electronique"],
      comp_good=["arduino","esp32","dupont","ecran"], comp_bad=["foret","fpga","altera"]),
 # ---------------- LED ----------------
 dict(q="Ruban led RGB STRIP LIGHT 12V 5M", cat="led",
      sim_ok=["ruban","strip","bande","rgb"],
      comp_cats=["alimentation","electronique","connectique"],
      comp_good=["alimentation","controleur","dimmer","transformateur","amplificateur rgb"],
      comp_bad=["foret","vis","capteur","fpga","diode","projecteur"]),
 dict(q="Ruban LED COB 12V 8mm 5M 6500K", cat="led",
      sim_ok=["ruban","cob","bande","strip"],
      comp_cats=["alimentation","electronique","connectique"],
      comp_good=["alimentation","controleur","dimmer","transformateur"],
      comp_bad=["foret","vis","capteur","fpga","projecteur"]),
 # ---------------- electronique / modules ----------------
 dict(q="Module Relais 4 canaux 5V", cat="electronique",
      sim_ok=["relais","relay"],
      comp_cats=["carte","connectique","composant","alimentation"],
      comp_good=["arduino","esp32","raspberry","dupont","alimentation"],
      comp_bad=["foret","perceuse","fpga","altera","projecteur"]),
 dict(q="1602 MODULE AFFICHEUR LCD 2X16 AVEC INTERFACE I2C", cat="electronique",
      sim_ok=["lcd","oled","afficheur","ecran","1602","12864"],
      comp_cats=["carte","connectique","composant","alimentation"],
      comp_good=["arduino","esp32","dupont","resistance","potentiometre"],
      comp_bad=["foret","perceuse","fpga","altera"]),
 # ---------------- moteurs ----------------
 dict(q="Moteur pas à pas NEMA23 JK57HS41", cat="moteur",
      sim_ok=["moteur","nema","pas pas","stepper"],
      comp_cats=["carte","electronique","alimentation","batterie","mecanique"],
      comp_good=["driver","a4988","l298","controleur","arduino","esp32","alimentation"],
      comp_bad=["foret","perceuse","cle a choc","visseuse","meuleuse","fpga"]),
 dict(q="Mini Moteur 45000 RPM 7x20mm", cat="moteur",
      sim_ok=["moteur","motor","rpm"],
      comp_cats=["carte","electronique","alimentation","batterie","mecanique"],
      comp_good=["driver","l298","controleur","batterie","alimentation"],
      comp_bad=["foret","cle a choc","visseuse","meuleuse"]),
 # ---------------- composants ----------------
 dict(q="Diode 1N4007 1A 1000V", cat="composant",
      sim_ok=["diode","1n4007","1n4148","1n5408"],
      comp_cats=["electronique","connectique","carte"],
      comp_good=["breadboard","plaque essai","dupont","support","resistance"],
      comp_bad=["foret","perceuse","fpga","altera","projecteur","cle a choc"]),
 dict(q="Condensateur polyester 0.33µF 100V", cat="composant",
      sim_ok=["condensateur"],
      comp_cats=["electronique","connectique","carte"],
      comp_good=["breadboard","dupont","support","resistance"],
      comp_bad=["foret","fpga","altera","cle a choc"]),
 # ---------------- connectique ----------------
 dict(q="Cable Micro-USB 0.5m", cat="connectique",
      sim_ok=["cable","micro usb","usb"],
      comp_cats=["carte","electronique","composant"],
      comp_good=["arduino","esp32","raspberry","module","breadboard"],
      comp_bad=["foret","vis","fpga","altera"]),
 # ---------------- chargeur ----------------
 dict(q="Chargeur Batterie 18650 - Double", cat="chargeur",
      sim_ok=["chargeur","18650"], comp_cats=["batterie","connectique"],
      comp_good=["18650","batterie","pile","accu","cellule","li-ion","lipo"],
      comp_bad=["foret","vis","peinture","moteur"]),
 # ---------------- alimentation ----------------
 dict(q="Alimentation 12V 2A Adaptateur Secteur", cat="alimentation",
      sim_ok=["alimentation","12v","adaptateur"],
      comp_cats=["carte","connectique","led","electronique","mecanique"],
      comp_good=["arduino","esp32","raspberry","led","ruban","module","boitier","jack"],
      comp_bad=["foret","vis","cle","fpga","altera","triac"]),
 # ---------------- rf ----------------
 dict(q="Module LoRa 433 MHz émetteur récepteur", cat="rf",
      sim_ok=["lora","433","nrf24","rf"],
      comp_cats=["carte","alimentation","connectique"],
      comp_good=["arduino","esp32","raspberry","antenne","dupont","module"],
      comp_bad=["foret","vis","haut parleur","enceinte","fpga"]),
 # ---------------- audio ----------------
 dict(q="Haut Parleur Bluetooth TTD-8244", cat="audio",
      sim_ok=["haut parleur","bluetooth","enceinte","speaker"],
      comp_cats=["connectique","alimentation","chargeur"],
      comp_good=["jack","cable","chargeur","alimentation","aux","micro"],
      comp_bad=["foret","vis","esp32","arduino","relais","fpga","capteur","ruban"]),
 # ---------------- mesure ----------------
 dict(q="Multimètre digital true RMS 1000V", cat="mesure",
      sim_ok=["multimetre","testeur"],
      comp_cats=["composant","connectique"],
      comp_good=["sonde","cordon","pince","fusible","cable","crocodile"],
      comp_bad=["foret","vis","arduino","esp32","fpga"]),
 # ---------------- soudure ----------------
 dict(q="Fer À Souder 40 W TET1406", cat="soudure",
      sim_ok=["fer","souder","soudure"],
      comp_cats=["composant","connectique"],
      comp_good=["etain","flux","panne","tresse","support"],
      comp_bad=["foret","perceuse","arduino","esp32","fpga"]),
 # ---------------- solaire ----------------
 dict(q="Mini panneau solaire portable 12V 2W", cat="solaire",
      sim_ok=["solaire","panneau","photovolta"],
      comp_cats=["batterie","alimentation","chargeur"],
      comp_good=["batterie","controleur","mppt","regulateur","18650","onduleur"],
      comp_bad=["foret","vis","fpga","arduino"]),
]
