# Hardwarevalidatie – protocol en resultaten

## Huidige stand (8 november 2026)

| Test | Mock / simulator | Fysieke CAF-TF101S-AEUR |
| --- | --- | --- |
| Detectie van het apparaat | ✅ getest | ✅ werkt (H1) |
| Uitlezen van beide zones | ✅ getest | ✅ werkt (H2) |
| Temperatuur en tijd instellen | ✅ getest (request-inhoud gecontroleerd) | ✅ werkt (H5, H6) |
| Starten zone 1 (native) | ✅ getest | ✅ werkt (H5) |
| Starten zone 2 (native) | ✅ getest | ✅ werkt (H6) |
| Starten zone 2 terwijl zone 1 kookt | ✅ getest | ✅ werkt, zone 1 loopt door (H7) |
| Starten beide zones (één knop) | ✅ getest | ⬜ niet getest |
| Match-start | ✅ getest | ✅ werkt, sync-modus aan (H8) |
| Stoppen per zone | ✅ getest | ✅ werkt (H4) |
| Stoppen beide zones | ✅ getest | ✅ werkt (H9) |
| Mand eruit en terug tijdens koken | ✅ getest | ✅ werkt (H10) |
| Stroom eraf en terug | ✅ getest | ✅ werkt (H11) |
| Kookproces gestart in de app of op het apparaat | ✅ getest | ⬜ niet getest (H3) |
| Starten via SwitchBot | ✅ getest (nep-Bot) | ⬜ niet nodig: native starten werkt |
| Verificatie werkelijke kookstatus | ✅ getest | ✅ werkt |

**Native starten werkt op de TF101S.** De airfryer gaat direct koken; er is
geen druk op de fysieke startknop nodig. De SwitchBot-route blijft
beschikbaar maar is voor dit type niet nodig.

## Voorbereiding

1. Installeer de integratie en stel hem in met startmethode **Native**.
2. Zet in `configuration.yaml` tijdelijk debuglogging aan:

   ```yaml
   logger:
     logs:
       custom_components.cosori_twinfry: debug
       pyvesync: debug
   ```

3. Beide manden leeg en schoon in de airfryer, lade dicht. Blijf tijdens
   alle tests bij het apparaat. Gebruik korte tijden (2–3 min) en
   **Reheat 80 °C** zodat er weinig opwarmt.
4. Download na elke test de diagnostics (apparaatpagina → ⋮ → Diagnostics
   downloaden). `last_raw_status` en `last_start.steps` zijn de bewijslast.

## Testen

Noteer bij elke test: de melding in HA, de sensor *Laatste start* (status +
attribuut `steps`), wat je **op het apparaat** ziet, en de diagnostics.

| # | Handeling | Te beoordelen |
| --- | --- | --- |
| H1 | Integratie toevoegen | Wordt de TwinFry gevonden? Welk `device_type` in diagnostics? |
| H2 | Zonder iets te doen 2 polls afwachten | Beide zones `Inactief`? Online aan? |
| H3 | Start een kookproces met de VeSync-app in zone 1 | Toont HA zone 1 `Bezig`, programma, temperatuur, resterende tijd? |
| H4 | Stop zone 1 via HA | Stopt het apparaat? Status terug naar `Inactief`? |
| H5 | Zone 1: Reheat, 80 °C, 2 min, **Start zone 1** (Native) | Een van drie uitkomsten — zie hieronder. **Dit is de kerntest.** |
| H6 | Herhaal H5 voor zone 2 | idem |
| H7 | Start beide zones (verschillende tijden) | Starten beide? Pauzeert zone 1 bij het starten van zone 2? |
| H8 | Match-start | Starten beide met dezelfde instellingen? Sync-modus? |
| H9 | Stop beide zones | Beide `Inactief`? |
| H10 | Mand uittrekken tijdens koken | Status `Mand eruit`/`Gepauzeerd`, event `paused`; terugduwen → `resumed` |
| H11 | Wifi van de airfryer uit (stekker kort eruit) | Status `offline`, zones unavailable, geen oude waarden |

### Kerntest H5: drie mogelijke uitkomsten

| Uitkomst | Betekenis | Vervolg |
| --- | --- | --- |
| Melding ontbreekt, zone `Bezig`, apparaat verwarmt | Native starten werkt | Startmethode Native houden. Graag melden bij pyvesync (eerste TF101S-bevestiging van `readyStart: false`). |
| Melding *"wacht op zijn startknop"*, zone `Klaar` | Fysieke bevestiging vereist | Druk handmatig op Start en kijk of de zone gaat koken → dan SwitchBot-route testen (S1–S4). |
| Melding *"niet binnen … s bevestigd"*, zone `Inactief` | Opdracht genegeerd | Diagnostics bewaren; test S1 (klaarzet-route). |

### SwitchBot-tests

Voorwaarde: Bot in **press mode**, gemonteerd boven de normale Start-knop
(alleen de knop indrukken, geen andere aanpassingen).

| # | Handeling | Te beoordelen |
| --- | --- | --- |
| S1 | Startmethode SwitchBot, zone 1 starten | Gaat zone 1 eerst naar `Klaar`? Drukt de Bot? Daarna `Bezig`? |
| S2 | Zelfde met zone 2 | Start de knop de rechter zone als alleen die klaarstaat? |
| S3 | Match-start met SwitchBot | Start één druk beide zones? |
| S4 | Bot tijdelijk onbereikbaar (batterij eruit) | Duidelijke fout, geen druk, geen start |
| S5 | Startmethode Automatisch | Gebruikt hij native als dat werkt, en anders de Bot? |

Open vraag voor S1/S2: drukt de Start-knop alleen de klaargezette zone, of
heeft hij ook effect op een zone die al loopt? Tot dit bekend is weigert de
integratie te drukken terwijl een andere zone actief is.

## Resultaten

Getest op 8 november 2026 met een CAF-TF101S-AEUR, startmethode Native,
Opwarmen 80 °C, 2 of 3 minuten, lege manden. Firmwareversie niet uitgelezen
(VeSync gaf er geen door).

| # | Uitkomst | Opmerking |
| --- | --- | --- |
| H1 | ✅ | Gevonden als Dual Blaze TwinFry 10L. |
| H2 | ✅ | Beide zones Stand-by, online aan. |
| H3 | ⬜ | Niet getest. |
| H4 | ✅ | Zone 2 binnen 5 s gestopt, event `stopped`. |
| H5 | ✅ | Start bevestigd na 4 s (`chamber_1_native_accepted`, `chamber_1_cooking_confirmed`), na 2 min vanzelf klaar, event `finished`. Op het display bevestigd. |
| H6 | ✅ | Zone 2 kookt na 6 s. |
| H7 | ✅ | Zone 2 gestart terwijl zone 1 kookte; zone 1 pauzeert niet. Op het display bevestigd. |
| H8 | ✅ | Beide zones koken na 6 s met dezelfde instellingen, sync-modus `sync`. |
| H9 | ✅ | Beide zones binnen 6 s Stand-by, events `stopped`. |
| H10 | ✅ | `paused` bij lade eruit, `resumed` bij terugduwen; klaar-om schuift mee op. |
| H11 | ✅ | Offline gemeld bij de eerstvolgende poll, zones onbeschikbaar, geen oude waarden en geen events; na stroom terug vanzelf weer online. |
| Dubbele start | ✅ | Tweede start op een actieve zone geweigerd. |

### Gevonden en opgelost

De lade is gedeeld door beide zones. Trek je hem uit terwijl een zone niet
kookt, dan meldt ook die zone `pullOut`, met ingestelde tijd 0 en standaard
mode `AirFry`. Na terugduwen gaf de integratie voor die zone ten onrechte het
event `finished`, en de apparaatstatus stond op Gepauzeerd. Een zone telt nu
alleen als gepauzeerd kookproces als er een ingestelde tijd is en er eerder
een kookproces liep.
