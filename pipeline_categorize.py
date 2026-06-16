CATEGORY_RULES = {
 "capteur":     ["capteur","capteurs","senseur","sensor","dht11","dht22","ds18b20","hc-sr04","hcsr04","pir","ultrason","mpu6050","mpu9250","bmp","bme280","mq2","mq3","mq135","ldr","acs712","sct013","gy-","lm35","tof","photoresistance","accelerometre","gyroscope","camera","debimetre","yf-s201","flow","ad8232","ecg","hc-sr501","encodeur","mlx","reed","hx711","load cell","fin de course"],
 "carte":       ["raspberry","rpi","arduino","esp32","esp8266","nodemcu","wemos","microbit","stm32","atmega","jetson","wroom","attiny","carte developpement","mega2560","leonardo"],
 "mobilite":    ["voiture","telecommandee","telecommande","drone","quadcopter","helices","helice","roue","roues","chassis","4wd","2wd","robot","bateau","avion","mecanum","suiveur"],
 "moteur":      ["moteur","motor","servo","servomoteur","stepper","nema17","nema23","28byj","pompe","ventilateur","brushless","pas a pas","mg90","mg90s","mg995","mg996","sg90","ds3218","actionneur","vibreur"],
 "led":         ["led","ruban","bande","ampoule","lampe","lumiere","spectre","rgb","neon","matrice","ws2812","cob","horticole","projecteur","spot","luminaire","strip"],
 "batterie":    ["pile","piles","batterie","battery","18650","21700","26650","14500","lipo","li-po","lithium","accu","alcaline","alkaline","nimh","ni-mh","vape","cr2032","cr2016","cr1620","r20","r14"],
 "chargeur":    ["chargeur","charging","chargement","tp4056","imax"],
 "alimentation":["alimentation","tension","regulateur","regulator","convertisseur","transformateur","decoupage","buck","boost","abaisseur","elevateur","pwm","7805","79l12","onduleur","step-down","step-up","fusible"],
 "rf":          ["433mhz","rf","emetteur","recepteur","bluetooth","ble","wifi","gsm","gprs","gps","nrf24","lora","zigbee","sim800","sim900","antenne","hm-10","nfc","rfid"],
 "electronique":["module","circuit","relais","relay","lcd","oled","hdmi","i2c","spi","74hc","mosfet","registre","potentiometre","potentiometer","ecran","interrupteur","bouton","contacteur","rtc","driver","l298","shield","bouclier","pcb","prototype","perforee","controleur","cnc","gravure","expansion","stc-1000","uln2003","afficheur","segments","tm1637","max7219","clavier","membrane","ft232","rs232","cp2102","ch340","keypad","joystick","dip switch","horloge","ne555"],
 "composant":   ["diode","diodes","resistance","resistances","condensateur","transistor","zener","quartz","cristal","inductance","1n4148","1n4007","thyristor","triac","optocoupleur","triode","optotriac"],
 "connectique": ["cable","cables","fil","fils","connecteur","connecteurs","cosses","cosse","jumper","cavalier","dupont","barette","barrette","prise","borne","bornier","header","nappe","gaine","thermoretractable","domino","carte memoire","micro sd","microsd","sd card","cordon","rallonge","serre cable"],
 "mesure":      ["multimetre","testeur","oscilloscope","amperemetrique","pince ampere","compteur","balance","luxmetre","thermometre","wattmetre","pzem","ph metre","electrode","sonde","frequencemetre","generateur de signal"],
 "soudure":     ["souder","soudure","etain","flux","panne","dessoudage","fer a souder","desoudage"],
 "solaire":     ["solaire","photovoltaique","photovolta","mppt","panneau solaire"],
 "audio":       ["haut-parleur","haut parleur","microphone","amplificateur","buzzer","speaker","ampli","sonore","hp","mp3","jack audio"],
 "outillage":   ["tournevis","cle","cles","clef","pince","pinces","scie","cutter","lame","lames","foret","forets","marteau","coffret","outil","outils","douille","douilles","embout","embouts","percage","brucelle","mandrin","cliquet","perceuse","visseuse","meuleuse","burin","lime","etau","cle mixte","jeu de","pistolet","colle","peinture","disque","brosse","meule","nettoyeur","levage","electrogene","laser","niveau","compresseur","ponceuse","rabot","agrafeuse","riveteuse","decapeur","imprimante","creality","filament","truelle","spatule","pinceau","rouleau","echelle","escabeau","cric","palan","aspirateur","disqueuse","sangle"],
 "mecanique":   ["vis","ecrou","ecrous","boulon","rondelle","rondelles","rivet","roulement","engrenage","courroie","poulie","ressort","rail","profile","entretoise","boitier","coque","dissipateur","heatsink","radiateur","colonnette","equerre","charniere","glissiere","tige filetee"],
 "electrique":  ["disjoncteur","contacteur","sectionneur","chint","parafoudre","goulotte","armoire"],
}
ACCESSORY = {"lcd","oled","ecran","afficheur","ruban","boitier","coque","dissipateur",
             "ventilateur","camera","shield","transformateur","adaptateur","alimentation","chargeur"}
CAT_ORDER = ["chargeur","batterie","led","alimentation","moteur","rf","electronique","composant",
             "connectique","mesure","soudure","solaire","audio","outillage","mecanique","electrique"]

TOOL_BRANDS = {"total","wadfow","harden","yato","tolsen","ingco","stanley","bosch","makita",
               "dewalt","milwaukee","creality","deli"}
def is_tool_brand(title):
    return any(b in norm_raw(title).split() for b in TOOL_BRANDS)

def _has(n, words, kws):
    for k in kws:
        if " " in k:
            if k in n: return True
        elif len(k) <= 3:
            if k in words: return True
        else:
            if any(k in w for w in words) or k in n: return True
    return False

def infer_category(title):
    n = normalize_text(title); words = set(n.split()); wr = set(norm_raw(title).split())
    if _has(n, words, CATEGORY_RULES["mobilite"]): return "mobilite"
    if _has(n, words, CATEGORY_RULES["capteur"]):  return "capteur"
    if _has(n, words, CATEGORY_RULES["carte"]) and not (wr & ACCESSORY): return "carte"
    for cat in CAT_ORDER:
        if _has(n, words, CATEGORY_RULES[cat]): return cat
    if is_tool_brand(title): return "outillage"
    return "autre"

# ============================================================================
# SPECS
# ============================================================================
SPEC_PATTERNS = {
 "capacity_mah":(r'\b(\d+(?:[.,]\d+)?)\s*mah\b',50,100000),
 "capacity_ah": (r'\b(\d+(?:[.,]\d+)?)\s*ah\b',0.2,500),
 "voltage_v":   (r'\b(\d+(?:[.,]\d+)?)\s*v\b',0.5,600),
 "power_w":     (r'\b(\d+(?:[.,]\d+)?)\s*w\b',0.1,5000),
 "count":       (r'\b(\d+)\s*(?:pcs|pieces|broches|pin|leds?|canaux|ch)\b',1,10000),
}
def extract_specs(title):
    t = unicodedata.normalize("NFKD", str(title)).encode("ascii","ignore").decode("ascii").lower().replace("*"," ")
    out={}
    for name,(pat,lo,hi) in SPEC_PATTERNS.items():
        v=[float(x.replace(",",".")) for x in re.findall(pat,t)]; v=[x for x in v if lo<=x<=hi]
        if v: out[name]=max(v)
    return out
UPGRADE_SPECS=["capacity_mah","capacity_ah","power_w","count"]
def primary_spec(specs):
    for k in UPGRADE_SPECS:
        if k in specs: return k,specs[k]
    return None,0.0

# ============================================================================
# BRIQUE 1 -- ATTRIBUTS
# ============================================================================
LIION_FF=["18650","21700","26650","14500","16340","18500","20700"]; COIN_FF=["cr2032","cr2016","cr1620","cr2025","cr2450","lr44","ag13"]
def a_form_factor(n):
    for f in LIION_FF:
        if f in n: return f
    for f in COIN_FF:
        if f in n: return "coin"
    if re.search(r'\b(rl20|pile d)\b',n): return "d"
    if re.search(r'\b(rl14|pile c)\b',n): return "c"
    if re.search(r'\b(aaa|lr03|r03)\b',n): return "aaa"
    if re.search(r'\b(aa|lr6|r6)\b',n): return "aa"
    if re.search(r'\b9v\b',n): return "9v"
    if re.search(r'\bnema\s?17\b',n): return "nema17"
    if re.search(r'\bnema\s?23\b',n): return "nema23"
    if "5mm" in n: return "5mm"
    if "3mm" in n: return "3mm"
    for c in ["5050","2835","3528"]:
        if c in n: return c
    return None
def a_chemistry(n,ff):
    if "lipo" in n or "li-po" in n or "polymer" in n: return "lipo"
    if ff in LIION_FF or "li-ion" in n or "liion" in n or "lithium" in n: return "lithium"
    if "nimh" in n or "ni-mh" in n: return "nimh"
    if "alcaline" in n or "alkaline" in n or ff in ("d","c","aa","aaa","9v"): return "alkaline"
    if "plomb" in n or "agm" in n or "ultracell" in n or "acide" in n: return "lead"
    if "vape" in n or "pod" in n: return "vape"
    if ff=="coin": return "lithium"
    return None
def a_connector(n):
    if "type-c" in n or "type c" in n or "usb-c" in n or "usb c" in n: return "usb_c"
    if "micro usb" in n or "micro-usb" in n or "microusb" in n: return "usb_micro"
    if "type-b" in n or "type b" in n or "usb-b" in n: return "usb_b"
    if "xt60" in n: return "xt60"
    if "jst" in n: return "jst"
    if "hdmi" in n: return "hdmi"
    if "rj45" in n or "ethernet" in n: return "rj45"
    if "jack" in n: return "jack"
    if "usb" in n: return "usb_a"
    return None
def a_connectivity(n):
    if "wifi" in n or "wi-fi" in n: return "sans" if ("sans wifi" in n or "without wifi" in n) else "wifi"
    if "bluetooth" in n or re.search(r'\bble\b',n): return "bluetooth"
    if "433" in n or "nrf24" in n or "lora" in n or "zigbee" in n or re.search(r'\brf\b',n): return "rf"
    if "gsm" in n or "gprs" in n: return "gsm"
    if "gps" in n: return "gps"
    if "sans fil" in n: return "wireless"
    return None
def a_control(n):
    if "application" in n or re.search(r'\bappli\b',n) or re.search(r'\bapp\b',n): return "app"
    if "wifi" in n: return "wifi"
    if "bluetooth" in n: return "bluetooth"
    if "telecommand" in n or "radiocommand" in n or re.search(r'\brc\b',n): return "rc"
    return None
def a_vehicle(n):
    w=set(n.split())
    if "voiture" in n or "automobile" in n: return "voiture"
    if "drone" in n or "quadcopter" in n: return "drone"
    if "bateau" in n: return "bateau"
    if "avion" in n: return "avion"
    if "moto" in w: return "moto"
    if "tank" in w: return "char"
    if "robot" in n: return "robot"
    return None
def a_board(n):
    w=set(n.split())
    if "esp32" in n: return "esp32"
    if "esp8266" in n or "nodemcu" in n or "wemos" in n or "esp-12" in n: return "esp8266"
    if "raspberry" in n or "rpi" in w or "pi" in w: return "raspberry"
    if "arduino" in n: return "arduino"
    if w & {"uno","nano","leonardo","mega"}: return "arduino"
    if "microbit" in n: return "microbit"
    if "stm32" in n: return "stm32"
    if "jetson" in n: return "jetson"
    return None
def a_led_form(n):
    if "ruban" in n or "bande" in n or "strip" in n: return "strip"
    if "ampoule" in n or "spot" in n or re.search(r'\be14\b',n) or re.search(r'\be27\b',n) or "gu10" in n: return "bulb"
    if "matrice" in n or "ws2812" in n or "8x8" in n or "neopixel" in n: return "matrix"
    if "cob" in n or "horticole" in n or "spectre" in n: return "cob"
    if "infrarouge" in n or "850nm" in n or "940nm" in n or re.search(r'\bir\b',n): return "ir"
    if "afficheur" in n or "7 segment" in n or "segments" in n: return "display"
    if "neon" in n: return "neon"
    if "5mm" in n or "3mm" in n: return "discrete"
    if "lampe" in n or "projecteur" in n or "luminaire" in n: return "bulb"
    return None
def a_voltage_bucket(specs):
    v=specs.get("voltage_v")
    if v is None: return None
    for b in (3.3,5,12,24,220):
        if abs(v-b)<=max(0.6,b*0.12): return b
    return round(v)
def a_psu(n):
    if "buck" in n or "abaisseur" in n or "step down" in n: return "buck"
    if "boost" in n or "elevateur" in n or "step up" in n: return "boost"
    if "decoupage" in n or "transformateur" in n or "ac dc" in n: return "acdc"
    if "pwm" in n: return "pwm"
    return None
def a_rftech(n):
    if "433" in n: return "433"
    if "bluetooth" in n or re.search(r'\bble\b',n) or "hm-10" in n: return "bluetooth"
    if "wifi" in n: return "wifi"
    if "gsm" in n or "gprs" in n or "sim800" in n: return "gsm"
    if "gps" in n: return "gps"
    if "lora" in n: return "lora"
    if "zigbee" in n: return "zigbee"
    if "nrf24" in n: return "nrf24"
    if "nfc" in n or "rfid" in n: return "nfc"
    return None
def a_component(n):
    for c in ["resistance","condensateur","transistor","zener","diode","quartz","inductance","optocoupleur","thyristor","triac"]:
        if c in n: return c
    return None
def a_module_fn(n):
    # reconnait la FONCTION d'un circuit / module (registre, timer, rtc, driver, ampli...)
    if "relais" in n or "relay" in n: return "relais"
    if "registre" in n or "decalage" in n or "shift register" in n or "74hc595" in n or "74hc164" in n or "74hc165" in n: return "registre"
    if "rtc" in n or "horloge" in n or "ds1302" in n or "ds3231" in n: return "rtc"
    if "ne555" in n or "timer" in n or re.search(r'\b555\b',n): return "timer"
    if "lcd" in n or "oled" in n or "afficheur" in n or "ecran" in n: return "display"
    if "l298" in n or "uln2003" in n or "driver" in n or "darlington" in n: return "driver"
    if "amplificateur" in n or "opamp" in n or "lm358" in n or "lm741" in n or "tda" in n: return "ampli"
    if "potentiometre" in n or "potentiometer" in n: return "potentiometre"
    if "optocoupleur" in n: return "opto"
    if "convertisseur" in n: return "convertisseur"
    if "interrupteur" in n: return "interrupteur"
    if "bouton" in n: return "bouton"
    if re.search(r'\b74(hc|hct|ls)\d',n): return "logique"
    return None
def a_motor(n):
    if "servo" in n or re.search(r'\b(mg90|mg90s|mg995|mg996|sg90|ds3218)\b',n): return "servo"
    if "stepper" in n or "nema" in n or "28byj" in n or "pas a pas" in n: return "stepper"
    if "pompe" in n: return "pompe"
    if "ventilateur" in n: return "ventilateur"
    if "moteur" in n or "motor" in n: return "dc"
    return None
def a_sensor(n):
    if "camera" in n: return "camera"
    if "dht" in n or "ds18b20" in n or "lm35" in n or "temperature" in n or "thermom" in n: return "temperature"
    if "hc-sr04" in n or "ultrason" in n or "sharp" in n or "tof" in n or "distance" in n: return "distance"
    if "pir" in n or "mouvement" in n or "motion" in n or "hc-sr501" in n: return "motion"
    if "mq" in n or "gaz" in n or "co2" in n or "pollution" in n: return "gaz"
    if "bmp" in n or "bme" in n or "pression" in n: return "pression"
    if "acs712" in n or "sct" in n or "courant" in n: return "courant"
    if "mpu" in n or "gyro" in n or "accel" in n: return "imu"
    if "ldr" in n or "lux" in n: return "lumiere"
    if "humidite" in n or "pluie" in n: return "humidite"
    return None

def extract_attrs(title, specs):
    n = norm_raw(title); ff = a_form_factor(n)
    return {"form_factor":ff,"chemistry":a_chemistry(n,ff),"connector":a_connector(n),
            "connectivity":a_connectivity(n),"control":a_control(n),"vehicle":a_vehicle(n),
            "board":a_board(n),"led_form":a_led_form(n),"voltage_bucket":a_voltage_bucket(specs),
            "psu":a_psu(n),"rftech":a_rftech(n),"component":a_component(n),
            "module_fn":a_module_fn(n),"motor":a_motor(n),"sensor":a_sensor(n)}

# ============================================================================