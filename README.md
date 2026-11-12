# Endesa X JuiceBox & Victron ESS Integration for Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1+-blue.svg)](https://www.home-assistant.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=relust&repository=ha-endesa-juicebox&category=integration)

Integrare nativă Home Assistant pentru stațiile de încărcare **Endesa X / Enel X JuiceBox (Waybox EU)** cu control 100% local, reglare dinamică a surplusului solar fotovoltaic și sincronizare hardware cu **Victron Energy (Cerbo GX / MultiPlus-II ESS)**.

---

## Caracteristici Principale

- **Control 100% Local (Fără Cloud):** Comunicare directă prin HTTP și WebSocket pe rețeaua locală, eliminând dependența de serverele Enel X/Endesa sau abonamente.
- **Reglare Instantanee a Curentului (6A – 32A):** Modulare în sub-secundă direct în memoria microcontrolerului, fără repornirea stației.
- **Reglare Automată a Surplusului Solar (Mod Auto):** Urmărește dinamic surplusul fotovoltaic în trepte de 1A, protejând bateria casei conform pragului minim configurat (ex: 60%).
- **Conexiune Directă Hardware Victron Cerbo GX:** Citește parametrii esențiali (producție PV, SoC baterie casă, consum L1, rețea L1) direct prin **Modbus TCP nativ (port 502)** în <20ms, fără a crea senzori duplicați în Home Assistant.
- **Protecție Inteligentă la Suprasarcină Invertor (Off-Grid Guard):** În cazul unei căderi de rețea publică sau a unei alarme hardware de suprasarcină, curentul EV este redus automat sau pus pe pauză dacă sarcina depășește limita sigură (4.5 kW).
- **Plug & Charge cu Anti-Flapping:** Detectează conectarea fizică reală a cablului (cu protecție debounce de 12 secunde împotriva micro-întreruperilor Wi-Fi) și comută automat pe încărcare.
- **Telemetrie Completă și Energie:** Tensiune, curent, putere activă și totalizator de energie (compatibil cu Home Assistant Energy Dashboard).
- **Estimare Dinamică Baterie și Autonomie EV:** Calcul dinamic SoC (%) și kilometri adăugați în timp real pentru vehicule electrice (optimizat pentru Nissan Leaf 62 kWh).

---

## Arhitectură Sistem

```
 ┌──────────────────────┐                     ┌──────────────────────────────┐
 │   Endesa X JuiceBox  │ <── HTTP / WS ────> │   Home Assistant             │
 │   192.168.0.173      │                     │   custom_components/         │
 └──────────────────────┘                     │   endesa_juicebox            │
                                              └──────────────┬───────────────┘
                                                             │
                  ┌──────────────────────────────────────────┴─────────────────────────┐
                  │ Direct Modbus TCP (502)                  │ Virtual EVCS via MQTT   │
                  ▼                                          ▼                         │
 ┌──────────────────────────────────┐       ┌──────────────────────────────────────────┴┐
 │   Victron Cerbo GX (Venus OS)    │ <───> │  dbus-mqtt-ev-charger driver              │
 │   192.168.0.135:502 / 1883       │       │  (Expune stația nativ în Victron GUI)     │
 └──────────────────────────────────┘       └───────────────────────────────────────────┘
```

---

## Instalare prin HACS (Home Assistant Community Store)

### Metoda 1: Instalare cu 1 Click
Apasă pe butonul de mai jos pentru a deschide direct depozitul în instanța ta Home Assistant:

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=relust&repository=ha-endesa-juicebox&category=integration)

### Metoda 2: Adăugare Manuală ca Custom Repository
1. Deschide **HACS** în Home Assistant.
2. Mergi la **Integrations** (Integrări).
3. Apasă pe cele trei puncte din colțul dreapta-sus și selectează **Custom repositories** (Depozite personalizate).
4. Introdu URL-ul:
   ```
   https://github.com/relust/ha-endesa-juicebox
   ```
5. La **Category**, selectează **Integration**.
6. Apasă pe **Add** (Adaugă), apoi deschide integrarea și apasă **Download** (Descarcă).
7. Repornește Home Assistant.

---

## Configurare

1. În Home Assistant, mergi la **Settings** > **Devices & Services** > **Add Integration**.
2. Caută **Endesa X JuiceBox**.
3. Completează datele de conectare:
   - **Host:** IP-ul local al stației (ex: `192.168.0.173`)
   - **Password:** Parola interfeței web a stației (implicit `000000`)
   - **Auto Start on Plug-in:** Activare Plug & Charge la cuplarea cablului.
   - **Enable Victron MQTT:** Activare punte către Cerbo GX (implicit activat).

---

## Parametri Configurabili (Options)

| Entitate | Descriere | Valori |
| :--- | :--- | :--- |
| `number.juicebox_charging_current` | Limită curent setată de utilizator | 6A – 32A |
| `number.prag_minim_baterie_casa` | Nivel minim baterie casă înainte de a aloca solar mașinii | 20% – 100% (default 60%) |
| `number.toleranta_nori` | Timp de grație la trecerea norilor înainte de oprire | 1 – 15 minute (default 3 min) |
| `switch.juicebox_auto_start` | Comutare Plug & Charge automat | On / Off |
| `switch.juicebox_charging` | Pornire / Oprire manuală încărcare | On / Off |

---

## Integrare cu Victron Venus OS (Cerbo GX)

Pentru afișarea completă a stației în interfața Victron (GUI-v2, VRM, Touch 50/70):
1. Instalează driverul `dbus-mqtt-ev-charger` pe Cerbo GX via SSH:
   ```bash
   wget -O - https://raw.githubusercontent.com/mr-manuel/venus-os_dbus-mqtt-ev-charger/master/setup.sh | bash
   ```
2. Configurează IP-ul brokerului MQTT către Home Assistant (port 1883).
3. Stația JuiceBox va apărea instant în Victron ca un EV Charging Station oficial, permițând comutarea modului (Manual / Auto) și afișarea sesiunii de energie în timp real.

---

## Licență

Acest proiect este licențiat sub [MIT License](LICENSE).
Dezvoltat și menținut de [@relust](https://github.com/relust).
