# Hardwarevalidatie – protocol en resultaten

## Huidige stand (7 november 2026)

| Test | Mock / simulator | Fysieke CAF-TF101S-AEUR |
| --- | --- | --- |
| Detectie van het apparaat | ✅ getest | ⬜ niet getest |
| Uitlezen van beide zones | ✅ getest | ⬜ niet getest |
| Temperatuur en tijd instellen | ✅ getest (request-inhoud gecontroleerd) | ⬜ niet getest |
| Starten zone 1 (native) | ✅ getest | ⬜ niet getest |
| Starten zone 2 (native) | ✅ getest | ⬜ niet getest |
| Starten beide zones | ✅ getest | ⬜ niet getest |
| Match-start | ✅ getest | ⬜ niet getest |
| Stoppen per zone | ✅ getest | ⬜ niet getest |
| Stoppen beide zones | ✅ getest | ⬜ niet getest |
| Starten via SwitchBot | ✅ getest (nep-Bot) | ⬜ niet getest |
| Verificatie werkelijke kookstatus | ✅ getest | ⬜ niet getest |

**Niets is op fysieke hardware getest.** Er waren geen VeSync-inloggegevens
beschikbaar en de gekoppelde Home Assistant-instantie toonde geen VeSync- of
SwitchBot-entiteiten. De simulator gebruikt de echte pyvesync-code; alleen het
netwerk is nagebootst. Het gedrag van de airfryer zelf (vooral wat
`readyStart` doet en wat de fysieke startknop doet) is in de simulator een
**aanname** en precies wat hieronder op hardware moet worden vastgesteld.

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

Vul deze tabel in na de tests (en werk de bovenste tabel bij).

| # | Datum | Firmware | Uitkomst | Opmerking |
| --- | --- | --- | --- | --- |
| H1 | | | | |
| H5 | | | | |
| S1 | | | | |
