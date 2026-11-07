# Technisch onderzoek – COSORI Dual Blaze TwinFry 10L (CAF-TF101S-AEUR)

Datum onderzoek: 7 november 2026. Uitgangspunt is de **broncode**, niet de README's.
Alle bevindingen hieronder zijn terug te voeren op een bestand en (waar relevant)
een regel in de genoemde commit.

## 1. Onderzochte bronnen

| Bron | Commit / versie | Datum |
| --- | --- | --- |
| `webdjoe/pyvesync` (branch `dev`) | `0b657bd` | 5 nov 2026 |
| `pyvesync` op PyPI | `3.5.0` | – |
| `home-assistant/core` (branch `dev`) | `f8cdb14` | 7 nov 2026 |
| Home Assistant release | `2026.10.4` (geïnstalleerd in testomgeving) | – |
| `lackas/ha-core` (branch `vesync-air-fryer`) | `96e8eb1` | 26 apr 2026 |
| `RedsGT/hass-vesync-enhanced` | `9d32305` | 16 mei 2026 |

De wheel van **pyvesync 3.5.0 op PyPI is byte-voor-byte gelijk aan `dev`-HEAD**
(`diff -r --strip-trailing-cr` zonder verschillen). Er is dus geen ongepubliceerde
TwinFry-code: de officiële release bevat alles wat er is.

pyvesync **3.4.2** (de versie die HA Core 2026.10.4 vastpint) bevat **géén**
ondersteuning voor de TF101S (`VeSyncDualAirFryer` en `CAF-TF101S` komen er niet in voor).

## 2. Ondersteuning CAF-TF101S / CAF-TF102S in pyvesync 3.5.0

`pyvesync/device_map.py` (`air_fryer_modules`):

| Kenmerk | CAF-TF101S | CAF-TF102S | CAF-DC111S-AEU |
| --- | --- | --- | --- |
| Klasse | `VeSyncDualAirFryer` | `VeSyncDualAirFryer` | `VeSyncDualAirFryer` |
| `dev_types` | `CAF-TF101S-AEU`, `CAF-TF101S` | `CAF-TF102S` | `CAF-DC111S-AEU` |
| Features | `DUAL_CHAMBER`, `WHOLE_CHAMBER` | `DUAL_CHAMBER`, `WHOLE_CHAMBER` | `DUAL_CHAMBER` |
| Programma's | AirFry, Roast, Bake, Grill, Reheat, **Dry** | idem **zonder Dry** | + Proof, andere bereiken |
| Statussen | standby, ready, cooking, cookStop, pullOut | idem | + `hold` (Sync-wachten) |
| Eenheid / tijd | °C / seconden | °C / seconden | °C / seconden |
| Hardware-capture | ja (startMultiCook, endCook, status) | **nee** | ja |

`CAF-TF101S-AEUR` staat niet letterlijk in `dev_types`, maar `get_device_config()`
valt terug op het type zonder laatste segment (`CAF-TF101S`) en vindt dan de
TF101S-map. Gecontroleerd in de testomgeving:
`get_device_config('CAF-TF101S-AEUR') → ('CAF-TF101S', 'VeSyncDualAirFryer')`.

Let op de naamverwarring: pyvesync's `VeSyncDualBlazeFryer` is de **CAF-P583S**
(één mand, twee verwarmingselementen). De "Dual Blaze **TwinFry**" (CAF-TF101S) is
`VeSyncDualAirFryer`.

### Programma's en temperatuurbereik TF101S (°C, stap 5)

| Programma (`api_mode`) | recipeId | Bereik | Standaard | Standaardtijd |
| --- | --- | --- | --- | --- |
| AirFry | 14 | 120–205 | 200 | 20 min |
| Roast | 13 | 120–205 | 190 | 30 min |
| Bake | 9 | 80–205 | 160 | 25 min |
| Grill | 20 | 205–240 | 240 | 10 min |
| Reheat | 16 | 40–205 | 165 | 15 min |
| Dry | 21 | 35–95 | 55 | 6 uur |

pyvesync controleert temperatuur (afronden op stap, dan bereik per programma) maar
**geen maximale kooktijd** ("there is no upper limit", `docs/devices/kitchen.md`).

## 3. API van `VeSyncDualAirFryer` (`devices/vesynckitchen.py`)

Alle aanroepen gaan via `bypassV2` met `subDeviceNo: 0`.

| Doel | Payload-methode | Data | pyvesync-methode |
| --- | --- | --- | --- |
| Status | `getAirfryerMultiStatus` | `{}` | `update()` / `get_details()` |
| Starten | `startMultiCook` | `accountId, cookConfigs[], readyStart, syncType, tempUnit, workChamber` | `set_mode()` / `set_mode_from_recipe()` |
| Stoppen | `endCook` | `{chamber}` | `end(chamber)` |

`cookConfigs[]` bevat per kamer: `chamber, cookSetTime (s), cookTemp, mode, recipeId, recipeName, recipeType`.

Kamers (`AirFryerChamber`): `1` = links, `2` = rechts, `3` = WHOLE (scheidingswand
eruit), `4` = BOTH (beide kamers, zelfde instellingen, Sync).

Niet aanwezig voor dit model: **pauze, hervatten, voorverwarmen en
actuele temperatuur**. `stop()`/`resume()` geven `False`; de status bevat geen
temperatuurmeting (`current_temp` blijft `None`). Pauzeren gebeurt fysiek door een
mand uit te trekken (`pullOut`/`cookStop`).

### `state_chamber_1` en `state_chamber_2`

Elk een `FryerState`. `get_details()` vult ze uit `statusList`:

- Een kamer die niet in de lijst staat wordt `standby`.
- WHOLE wordt gerapporteerd als één item met `chamber: 3`; dat komt in
  `state_chamber_1`, kamer 2 wordt `standby`.
- Een onbekende `cookStatus` laat de vorige status van die kamer staan.
- Een mislukte of onleesbare poll laat **beide kamerstatussen ongewijzigd**
  (alleen `connection_status` en `last_update_ts` worden bijgewerkt).
- `cook_time_remaining` telt lokaal af vanaf de laatste poll.

### `set_mode()` en `end()`

- `set_mode(cook_time_s, cook_temp, cook_mode=..., chamber=...)` bouwt een recept,
  valideert programma/temperatuur/tijd **vóór** er een request gaat, en roept
  `set_mode_from_recipe()` aan. Ongeldige invoer → `False` zonder request.
- Bij een geslaagd antwoord zet pyvesync de kamerstatus **lokaal op `COOKING`**,
  zonder te pollen. Dat is een **optimistische status**; deze integratie gebruikt
  die lokale waarde daarom nooit.
- `end(chamber)`: `BOTH` stopt beide; `CHAMBER_1` tijdens een WHOLE-sessie stopt WHOLE.
- Een geweigerde opdracht geeft `False`; `device.last_response` bevat de reden
  (o.a. `BYPASS_LEFT_ZONE_COOKING`, `BYPASS_RIGHT_ZONE_COOKING`,
  `BYPASS_ALL_ZONE_COOKING`, `BYPASS_SYNC_FINISH_FAIL_*`).

## 4. Native starten: wat is bewezen en wat niet

Het verschil tussen *instellen* en *starten* zit in het veld **`readyStart`**:

- `readyStart: false` → bedoeld om direct te starten.
- `readyStart: true` → het programma wordt klaargezet; de airfryer gaat naar status
  **`ready`** ("Cook programmed, waiting for the start button", `const.py`
  `AirFryerCookStatus.READY`). De TF101S-statusmap kent `ready`.

pyvesync verstuurt **altijd `readyStart: false`**. Over de TF101S zegt de eigen
testsuite van pyvesync letterlijk (`src/tests/test_fryer_captures.py`, test
`test_tf101s_start_sets_cooking`):

> "No TF101S capture with readyStart false; cooking is inferred from CS158."

en `docs/devices/kitchen.md`: *"the other models are assumed to behave the same."*

Conclusie per niveau:

| Niveau | Status voor CAF-TF101S |
| --- | --- |
| Request-structuur `startMultiCook` | **Bewezen** (capture 17-01-2026, WHOLE) |
| Request-structuur `endCook` | **Bewezen** (capture 17-01-2026, WHOLE) |
| Statusstructuur `getAirfryerMultiStatus` | **Bewezen** (captures) |
| API accepteert `readyStart: false` | Waarschijnlijk, niet aangetoond |
| Airfryer begint direct te koken met `readyStart: false` | **Niet aangetoond** (afgeleid van CS158) |
| Airfryer gaat naar `ready` met `readyStart: true` | Niet aangetoond voor TF101S (wel DC601S-capture) |
| Fysieke bevestiging (startknop) vereist | **Onbekend** |

Het is dus reëel mogelijk dat de EU-TwinFry een opdracht accepteert maar
in `ready` blijft wachten op de startknop, of de opdracht negeert. Daarom:

1. de integratie beschouwt een HTTP-/API-succes nooit als start;
2. een start is pas geslaagd als een **nieuwe, geslaagde poll** de kamer als
   `cooking` rapporteert;
3. de integratie herkent de toestand `ready` expliciet, en kan dan (alleen als
   jij dat hebt ingesteld) de SwitchBot de fysieke startknop laten indrukken.

Voor de SwitchBot-route is `readyStart: true` nodig. pyvesync heeft daar geen
publieke parameter voor; de integratie bevat daarom een kleine, geïsoleerde
uitbreiding (`custom_components/cosori_twinfry/fryer_ext.py`) die hetzelfde
`startMultiCook`-request bouwt met pyvesync's eigen modellen en validatie, met
alleen `readyStart` anders. De uitbreiding gebruikt twee private pyvesync-helpers
(`_prepare_recipe`, `_build_cook_configs`) en is daarom vastgezet op
`pyvesync>=3.5.0,<3.6` en gedekt door tests die het verstuurde request controleren.

## 5. SYNC en MATCH

`AirFryerSyncType`: `OFF = 0`, `MATCH = 1` ("Match", APK `SYNC_COOK`),
`SYNC = 2` ("Sync", APK `SYNC_FINISH`, beide kamers tegelijk klaar).

- pyvesync start `BOTH` als `workChamber 4`, `syncType 2` met **identieke**
  instellingen voor beide kamers. Dit is praktisch "Match": hetzelfde programma
  in beide manden, tegelijk klaar.
- MATCH (1) wordt door pyvesync nooit verstuurd; Sync met **verschillende** tijden
  ("A Sync cook with different times can only be started from the app or the
  fryer") wordt niet ondersteund.
- Uitlezen: `sync_chambers` is alleen `True` bij `syncType 2`. De integratie leest
  `syncType` daarom zelf uit het ruwe poll-antwoord om ook MATCH te tonen.

In deze integratie: knop **"Match-start (zone 1-instellingen in beide zones)"**
gebruikt `BOTH`. Sync met verschillende tijden is bewust niet nagebouwd.

## 6. Officiële Home Assistant-integratie (`vesync`)

- HA 2026.10.4: `pyvesync==3.4.2` → TF101S wordt **niet** herkend.
- HA `dev` (7 nov 2026): `pyvesync==3.5.0`; de luchtfriteuse krijgt sensoren
  (`cook_status`, `cook_set_temp`, `cook_set_time`, resterende tijd) die alleen
  `device.state` lezen = **kamer 1**. Geen kamer 2, geen bediening.
- Code gebruikt inmiddels `probatio` (opvolger van voluptuous) en Python ≥ 3.14.2.

## 7. Overige implementaties

- **lackas/ha-core `vesync-air-fryer`**: voegt sensoren voor beide kamers toe
  (status, set-temp, resterende tijd), geen bediening. Hangt af van een
  **git-branch** (`pyvesync @ git+https://github.com/lackas/pyvesync@air-fryer-refactor`)
  → ongeschikt als releasebasis.
- **RedsGT/hass-vesync-enhanced**: vervangt het `vesync`-domein volledig,
  richt zich op de CAF-P583S (één mand), bediening via switch/number/select
  voor één kamer, en hangt af van een **git-branch** van pyvesync. Geen
  TF101S-kamerondersteuning.

Geen van beide is een bruikbare basis; deze integratie gebruikt alleen de
officiële pyvesync-release en een eigen domein (`cosori_twinfry`), zodat de
officiële `vesync`-integratie niet wordt overschreven.

## 8. SwitchBot Bot (Button Pusher) in Home Assistant

| Integratie | Entiteit voor de Bot | Indrukken | Opmerkingen |
| --- | --- | --- | --- |
| `switchbot` (Bluetooth) | `switch.*` | `switch.turn_on` (in **press mode** = één druk) | attribuut `switch_mode` (`false` = press mode), `last_run_success` |
| `switchbot_cloud` | `button.*` in press mode, `switch.*` in switch mode | `button.press` | via SwitchBot-cloud + hub |

- In **switch mode** houdt `turn_on` de arm ingedrukt. De integratie weigert
  daarom een `switch`-entiteit met `switch_mode: true`.
- **Pulsduur**: PySwitchbot 3.1.0 kent `set_long_press(duration)`, maar Home
  Assistant biedt daar geen entiteit of service voor. De pulsduur (hold time) is
  dus **niet vanuit HA instelbaar**; stel die in de SwitchBot-app in. De integratie
  biedt wel een instelbare wachttijd vóór het indrukken.

## 9. Gevolgen voor het ontwerp

1. pyvesync `==3.5.x` als enige bibliotheek; geen fork, geen git-afhankelijkheid.
2. Statussen alleen uit geslaagde polls; nooit uit pyvesync's lokale
   optimistische status na een opdracht.
3. Start = opdracht → herhaald pollen → `cooking` bevestigd, met time-out.
4. Startmethode Native / SwitchBot / Automatisch; SwitchBot alleen na bevestigde
   `ready`-status, en alleen als geen andere zone actief is (de Start/Pauze-knop
   zou een lopende zone kunnen pauzeren — gedrag niet aangetoond).
5. Geen sensor voor actuele temperatuur: het apparaat rapporteert die niet.
6. Conflict: pyvesync 3.5.0 naast de officiële `vesync`-integratie op HA-versies
   die nog 3.4.2 vastpinnen; zie README.

## 10. Hardwarevalidatie

**Geen van de functies is in dit project op een fysieke CAF-TF101S-AEUR getest.**
Er waren geen VeSync-inloggegevens beschikbaar, en in de gekoppelde Home
Assistant-instantie waren geen VeSync- of SwitchBot-entiteiten zichtbaar. Alle
tests draaien tegen de echte pyvesync-code met een gesimuleerde airfryer
(HTTP-laag gemockt). Het protocol voor de hardwarevalidatie staat in
`docs/hardware-validation.md`.
