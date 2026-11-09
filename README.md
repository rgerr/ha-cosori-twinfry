# COSORI TwinFry voor Home Assistant

Custom integration voor de **COSORI Dual Blaze TwinFry 10L (CAF-TF101S-AEUR)**
via de VeSync-cloud. Ook de 2026-uitvoering met keramische coating
(**CAF-TF101S-AEUR-C**) en de CAF-TF102S worden herkend. Beide kookzones
worden afzonderlijk gevolgd en bediend, en een kookproces kan vanuit Home Assistant worden gestart: native via de
VeSync-API of, als de airfryer op zijn fysieke startknop wacht, met een
**SwitchBot Bot (Button Pusher)**.

> **Status: op hardware getest (CAF-TF101S-AEUR, 8 november 2026).**
> Native starten, stoppen, match-start, mand eruit en stroomuitval werken.
> Nog niet getest: een kookproces gestart in de app of op het apparaat, en de
> SwitchBot-route (voor dit type niet nodig). Zie
> [docs/hardware-validation.md](docs/hardware-validation.md).

## Wat het doet

- **Per zone**: status, programma, ingestelde temperatuur, ingestelde tijd,
  resterende tijd, "klaar om"-tijdstip, kookt ja/nee, gebeurtenissen
  (gestart, klaar, gestopt, gepauzeerd, hervat, klaar om te starten).
- **Bediening per zone**: start, stop, programmakeuze, temperatuur, kooktijd.
- **Apparaat**: start beide zones, match-start (instellingen zone 1 in beide
  zones), stop beide zones, gecombineerde status, sync-modus, online,
  laatste geslaagde update, resultaat van de laatste start.
- **Services** `cosori_twinfry.start_cook` en `cosori_twinfry.stop_cook`
  voor scripts (ook voor de hele mand zonder scheidingswand).
- **Startmethode** Native, SwitchBot of Automatisch.

Wat er bewust níét is: een sensor voor de actuele temperatuur (de TwinFry
rapporteert die niet), pauzeren/hervatten vanuit HA en voorverwarmen (de API
heeft er geen opdracht voor; pauzeren gaat door een mand uit te trekken).

## Hoe een start werkt

Een start telt pas als geslaagd wanneer **VeSync na de opdracht meldt dat de
zone kookt**. Een geaccepteerde API-opdracht alleen is geen start.

1. Verse statuspoll: bereikbaar en online?
2. Instellingen valideren (programma, temperatuurbereik, tijd).
3. Zone moet inactief zijn (voorkomt dubbele starts).
4. Opdracht sturen.
5. Pollen tot de zone `Bezig` is, met time-out.

Met **SwitchBot** wordt het programma klaargezet (`readyStart`), wacht de
integratie tot de airfryer *Klaar (wacht op startknop)* meldt, drukt de Bot
de normale startknop in en controleert daarna weer of de zone kookt.
**Automatisch** probeert eerst native en gebruikt de Bot alleen als de
airfryer op zijn knop wacht of de native opdracht niets doet.

Beveiligingen:

- Eén start tegelijk; een tweede wordt geweigerd, niet in de wachtrij gezet.
- Een zone die kookt, gepauzeerd is of waarvan de mand eruit is, wordt nooit
  opnieuw gestart.
- De Bot drukt alleen als de doelzone bevestigd *Klaar* is **en geen andere
  zone actief is** (de Start/Pauze-knop zou een lopende zone kunnen pauzeren;
  dat is nog niet op hardware vastgesteld).
- Stoppen werkt altijd, ook tijdens een lopende start.
- Niets start automatisch: elke start komt van een knop, script of service
  die jij bewust aanroept.

## Installatie

### Via HACS (custom repository)

1. HACS → ⋮ → *Custom repositories* → URL van deze repository, type
   *Integration*.
2. Zoek **COSORI TwinFry** en installeer.
3. Herstart Home Assistant.

### Handmatig

Kopieer `custom_components/cosori_twinfry` naar
`/config/custom_components/cosori_twinfry` (bij jouw Synology-installatie:
`/docker/homeassistant/custom_components/`) en herstart Home Assistant.

### Vereisten

- Home Assistant **2026.10** of nieuwer (getest met 2026.10.4).
- `pyvesync>=3.5.0,<3.6` wordt automatisch geïnstalleerd. 3.5.0 is de eerste
  release met TwinFry-ondersteuning.
- **Let op bij de officiële VeSync-integratie**: HA 2026.10 pint die op
  pyvesync 3.4.2. Gebruik je beide tegelijk, dan kunnen ze elkaars versie
  overschrijven. De HA-ontwikkelversie gebruikt al 3.5.0; tot die versie
  uitkomt is het advies de airfryer niet ook in de officiële integratie te
  hebben en die integratie alleen te gebruiken als je hem voor andere
  apparaten nodig hebt — controleer dan na een herstart de logboeken.

## Instellen

*Instellingen → Apparaten & diensten → Integratie toevoegen → COSORI TwinFry*

- E-mailadres en wachtwoord van de VeSync-app.
- Land van het account (ISO-code, standaard het land van je HA, bijv. `NL`).
- Meerdere airfryers in het account? Je kiest er één per integratie-item.

### Opties (Configureren)

| Optie | Standaard | Uitleg |
| --- | --- | --- |
| Startmethode | Native | Native, SwitchBot of Automatisch |
| SwitchBot Bot | – | `button.*` (SwitchBot Cloud, press mode) of `switch.*` (SwitchBot Bluetooth, press mode). Een Bot in *switch mode* wordt geweigerd. |
| Wachttijd vóór indrukken | 2 s | Tussen *Klaar* bevestigd en de druk |
| Time-out wachten op 'klaar' | 20 s | |
| Time-out bevestiging start | 45 s | Ook gebruikt voor stoppen |
| Poll-interval tijdens koken | 15 s | |
| Poll-interval in rust | 60 s | |

De **drukduur** van de Bot is niet vanuit Home Assistant instelbaar (de
SwitchBot-integraties bieden daar geen entiteit of service voor). Stel die in
de SwitchBot-app in; een korte druk is voldoende.

## Entiteiten

Zone 1 = linker mand, zone 2 = rechter mand. Voorbeeld-ID's bij apparaatnaam
"TwinFry" en Nederlands als systeemtaal:

| Entiteit | Voorbeeld |
| --- | --- |
| Zone-status | `sensor.twinfry_zone_1_status` |
| Programma | `sensor.twinfry_zone_1_programma` |
| Ingestelde temperatuur / tijd | `sensor.twinfry_zone_1_ingestelde_temperatuur`, `…_ingestelde_tijd` |
| Resterende tijd / klaar om | `sensor.twinfry_zone_1_resterende_tijd`, `…_klaar_om` |
| Kookt | `binary_sensor.twinfry_zone_1_kookt` |
| Gebeurtenis | `event.twinfry_zone_1_gebeurtenis` |
| Start / stop | `button.twinfry_start_zone_1`, `button.twinfry_stop_zone_1` |
| Klaargezette instellingen | `select.twinfry_zone_1_programmakeuze`, `number.twinfry_zone_1_temperatuur`, `number.twinfry_zone_1_kooktijd` |
| Apparaat | `sensor.twinfry_status`, `button.twinfry_start_beide_zones`, `button.twinfry_match_start_zone_1_in_beide`, `button.twinfry_stop_beide_zones` |
| Diagnostisch | `sensor.twinfry_laatste_start`, `sensor.twinfry_laatste_geslaagde_update`, `sensor.twinfry_sync_modus`, `binary_sensor.twinfry_online` |

De *programmakeuze*, *temperatuur* en *kooktijd* zijn de instellingen voor de
**volgende** start van die zone. Ze veranderen een lopend kookproces niet.
Een programma kiezen laadt de standaardtemperatuur en -tijd uit de VeSync-app.

| Programma | Temperatuur (°C) | Standaard |
| --- | --- | --- |
| Airfry | 120–205 | 200 °C, 20 min |
| Braden | 120–205 | 190 °C, 30 min |
| Bakken | 80–205 | 160 °C, 25 min |
| Grillen | 205–240 | 240 °C, 10 min |
| Opwarmen | 40–205 | 165 °C, 15 min |
| Drogen | 35–95 | 55 °C, 6 uur |

Kooktijd: 1–60 min, bij Drogen 1–720 min (de airfryer kan strengere grenzen
hebben; een weigering wordt gemeld).

Bij een mislukte poll worden de zone-entiteiten **niet beschikbaar** in plaats
van oude waarden te tonen. In rust zijn temperatuur, tijd en programma
`onbekend`.

## Services

```yaml
action: cosori_twinfry.start_cook
data:
  device_id: <apparaat-ID>
  zone: zone_1          # zone_1, zone_2, both, match, whole
  program: airfry       # optioneel
  temperature: 200      # optioneel
  duration: 18          # optioneel, minuten
  method: auto          # optioneel, eenmalig andere startmethode
response_variable: resultaat   # {started, method, steps}
```

```yaml
action: cosori_twinfry.stop_cook
data:
  device_id: <apparaat-ID>
  zone: both            # zone_1, zone_2, both
```

Daarnaast vuurt de integratie het event `cosori_twinfry_event` met `zone`,
`event`, `status` en `program`.

## Dashboard en automatiseringen

- [dashboards/twinfry-dashboard.yaml](dashboards/twinfry-dashboard.yaml):
  sections-dashboard met twee zones, status, resterende tijd, programma en
  start/stop (met bevestiging), alleen standaardkaarten.
- [docs/automations.yaml](docs/automations.yaml): meldingen bij klaar,
  voortijdig gestopt, resterende tijd onder een instelbare grens, mislukte
  start, en een script voor starten na een expliciete opdracht.

## Bekende beperkingen

1. **Getest op één apparaat** (CAF-TF101S-AEUR, firmware onbekend). Niet
   getest: een kookproces gestart in de app of op het apparaat, de
   SwitchBot-route, de CAF-TF101S-AEUR-C en de CAF-TF102S.
2. **Geen actuele temperatuur**: het apparaat rapporteert die niet.
3. **Geen pauze/hervat/voorverwarmen** vanuit HA (geen API).
4. **Sync met verschillende tijden** (beide zones tegelijk klaar) wordt niet
   ondersteund; pyvesync kent alleen gelijke instellingen (match-start).
5. **SwitchBot drukt niet terwijl een andere zone actief is.** Beide zones
   met verschillende instellingen via de Bot starten kan daardoor niet; met
   gelijke instellingen wel (één programma, één druk).
6. Instellingen van een lopend kookproces wijzigen kan niet.
7. De SwitchBot-route gebruikt een kleine uitbreiding op private
   pyvesync-helpers; daarom is pyvesync op `<3.6` vastgezet. Ontbreken de
   helpers, dan werkt alleen de SwitchBot-route niet (met melding).
8. Cloud-afhankelijk: zonder internet of bij een VeSync-storing is er geen
   status en geen bediening.
9. De drukduur van de Bot is niet vanuit HA instelbaar.

## Ontwikkeling

```bash
pip install -r requirements_test.txt
pytest
```

Home Assistant draait niet op Windows; gebruik Linux, WSL of de
meegeleverde GitHub Actions-workflows (`tests.yml` en `validate.yml` met
hassfest en de HACS-validatie). Hassfest meldt tot HA met pyvesync 3.5.0
uitkomt een conflict met de vastgepinde 3.4.2 van HA 2026.10; die stap mag
daarom voorlopig falen zonder de workflow rood te maken. Vertalingen worden gegenereerd met
`python scripts/gen_translations.py custom_components/cosori_twinfry`.

Documentatie:

- [docs/technical-research.md](docs/technical-research.md) – broncode-onderzoek
  van pyvesync, HA Core en de bestaande forks.
- [docs/architecture.md](docs/architecture.md) – ontwerp, statusprincipe,
  startstrategie, foutafhandeling.
- [docs/hardware-validation.md](docs/hardware-validation.md) – testprotocol
  voor de echte airfryer.

## Licentie

MIT, zie [LICENSE](LICENSE).
