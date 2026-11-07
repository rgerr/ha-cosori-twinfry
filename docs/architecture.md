# Architectuur – COSORI TwinFry-integratie

## Overzicht

```
VeSync-cloud ──HTTP── pyvesync 3.5 (VeSync, VeSyncDualAirFryer)
                           │
          ┌────────────────┼──────────────────────────────┐
          │ client.py      │ fryer_ext.py                 │
          │ login/discover │ recept bouwen + valideren,   │
          │                │ startMultiCook (readyStart)  │
          └────────┬───────┴──────────────┬───────────────┘
                   │                      │
            coordinator.py          controller.py ──── SwitchBot-entiteit
            (alleen bevestigde      (start/stop, lock,     (button.press /
             status, events)         bevestiging, store)    switch.turn_on)
                   │                      │
     sensor · binary_sensor · event   button · number · select · services
```

| Module | Verantwoordelijkheid |
| --- | --- |
| `client.py` | Enige plek waar de pyvesync-manager wordt gemaakt (HA-sessie, regio, `redact=True`); login + apparatenlijst met time-out. |
| `fryer_ext.py` | Dunne laag op pyvesync: programma's/limieten, recept valideren, start versturen. Native start via de publieke `set_mode_from_recipe()`; de `readyStart: true`-variant voor SwitchBot is de enige uitbreiding (zie onder). |
| `models.py` | Pure dataclasses en functies: poll-antwoord parsen, statussen normaliseren, gebeurtenissen classificeren, tijdconversie. Geen HA-afhankelijkheid → direct unit-testbaar. |
| `coordinator.py` | `DataUpdateCoordinator[FryerSnapshot]`. Elke snapshot komt uit één geslaagde poll. Dynamisch interval (actief/rust), events bij statusovergangen, foutvertaling (auth → reauth, netwerk/time-out → `UpdateFailed`). |
| `controller.py` | Klaargezette instellingen per zone (persistent via `Store`), start- en stopopdrachten met bevestiging, lock tegen dubbele starts, SwitchBot-aansturing. |
| platforms | Dun: lezen snapshot/controller, roepen controller aan. |

## Statusprincipe: alleen bevestigde waarden

1. pyvesync zet na een geslaagde opdracht zijn eigen kamerstatus lokaal op
   `COOKING`, en laat die bij een mislukte poll staan. **Die lokale status wordt
   nooit gelezen.** De coördinator parseert het ruwe `getAirfryerMultiStatus`-
   antwoord van de zojuist uitgevoerde poll (`models.parse_multi_status`).
2. Mislukt een poll (geen antwoord, foutcode, onleesbaar, time-out, netwerk),
   dan wordt `UpdateFailed` gegooid: alle zone-entiteiten worden
   **unavailable** in plaats van de vorige waarden te tonen.
3. Een zone in `standby` heeft geen temperatuur/tijd/programma (`unknown`),
   geen overgebleven waarden van een vorige sessie.
4. `sensor.<naam>_laatste_geslaagde_update` toont wanneer de laatste goede poll was,
   met `last_poll_successful` en `last_error` als attributen.
5. Restart van HA tijdens het koken: de eerste poll leest de echte status; er
   wordt geen "gestart"-event gevuurd voor een kookproces dat al liep.

## Entiteiten

Eén apparaat (identifier = VeSync-`cid`). Zone-entiteiten krijgen "Zone 1/2"
in de naam via `translation_placeholders`. Zone 1 = links, zone 2 = rechts.

| Platform | Per zone | Apparaat |
| --- | --- | --- |
| `sensor` | status (enum), programma (enum, attribuut recept), ingestelde temperatuur (°C), ingestelde tijd (duur), resterende tijd (duur), klaar om (timestamp) | status (enum incl. `offline`), sync-modus (diagnostisch), laatste geslaagde update (diagnostisch), laatste start (diagnostisch, met stappen) |
| `binary_sensor` | kookt (`running`) | online (`connectivity`, diagnostisch) |
| `button` | start, stop | start beide, match-start, stop beide |
| `number` | temperatuur, kooktijd (klaargezet) | – |
| `select` | programmakeuze (klaargezet) | – |
| `event` | gebeurtenis: started, ready, paused, resumed, finished, stopped | – |

Bewust **niet** aanwezig: actuele temperatuur (het apparaat rapporteert die
niet), pauze/hervat (geen API), voorverwarmen (geen API).

Klaargezette instellingen (number/select) zijn de waarden die bij de volgende
start worden verstuurd. Ze wijzigen nooit een lopend kookproces; daar heeft de
TF101S-API geen opdracht voor. Een programmakeuze laadt de standaardtemperatuur
en -tijd van de app; temperatuurgrenzen volgen het gekozen programma.

Zone-availability: zone 2 is unavailable tijdens een hele-mand-sessie
(`workChamber 3`), behalve de stopknop.

## Startstrategie

Elke start loopt onder één `asyncio.Lock`. Een tweede start terwijl er een
loopt wordt **geweigerd** (niet in de wachtrij gezet).

```
1. verse poll  ─ mislukt → not_reachable  /  offline → device_offline
2. instellingen valideren (programma, temperatuur per programma, 1..max min)
3. doelzone(s) moeten standby of ready zijn  ─ anders zone_busy
4. route:
   native ──► startMultiCook(readyStart=false)
              ├─ geweigerd ─► command_rejected (reden uit last_response)
              └─ polls tot time-out:
                   cooking ─► SUCCES (native)
                   ready   ─► auto+SwitchBot: druk (stap 6)  | anders waiting_for_button
                   niets   ─► auto+SwitchBot: SwitchBot-route | anders start_not_confirmed
   switchbot ► startMultiCook(readyStart=true)
              └─ polls tot ready-time-out:
                   ready   ─► 5. andere zone actief? → other_zone_active
                              6. wachttijd, SwitchBot indrukken (time-out 20 s)
                              7. polls tot cooking ─► SUCCES (switchbot)
                                                  └► not_confirmed_after_press
                   cooking ─► SUCCES (gestart zonder knop)
                   niets   ─► not_ready (SwitchBot NIET ingedrukt)
8. resultaat in sensor "Laatste start" (stappen als attribuut) + foutmelding
```

Doelen:

| Doel | Native | SwitchBot |
| --- | --- | --- |
| Zone 1 / Zone 2 | kamer 1 / 2 | kamer 1 / 2 + één druk |
| Beide zones | zone 1, daarna zone 2 (eigen instellingen) | alleen bij identieke instellingen: één `BOTH`-programma + één druk |
| Match-start | `BOTH` (`workChamber 4`, `syncType 2`), instellingen zone 1 | idem + één druk |
| Hele mand (service) | `WHOLE` (`workChamber 3`) | idem + één druk |

Waarom de SwitchBot niet drukt terwijl een andere zone actief is: de TwinFry
heeft één Start/Pauze-knop. Of een druk dan de klaargezette zone start of de
lopende zone pauzeert, is niet aangetoond. Daarom wordt in dat geval niet
gedrukt en volgt een duidelijke melding.

Stoppen gebruikt een eigen lock en wordt nooit door een lopende start
geblokkeerd. Alleen zones die niet `standby` zijn krijgen een `endCook`
(ook een klaargezet `ready`-programma wordt zo geannuleerd). Daarna wordt
gepolld tot `standby` bevestigd is (`stop_not_confirmed` bij time-out).

## De geïsoleerde pyvesync-uitbreiding

`fryer_ext.async_send_start(..., ready_start=True)` bouwt het
`startMultiCook`-request met pyvesync's eigen `_prepare_recipe`,
`_build_cook_configs`, `_get_sync_type` en `FryerDualStartCookData`; alleen
`readyStart` is `true`. Een test bewijst dat het request verder byte-gelijk is
aan dat van de publieke methode. Het pakket is vastgezet op
`pyvesync>=3.5.0,<3.6`; `check_compatible()` controleert bij het opstarten of
de helpers bestaan. Ontbreken ze na een update, dan werkt alles behalve de
SwitchBot-route (melding `ready_start_unavailable`).

Zodra pyvesync een publieke `ready_start`-parameter krijgt, kan deze
uitbreiding vervallen.

## Foutafhandeling

| Situatie | Gedrag |
| --- | --- |
| Geen internet / VeSync-serverfout | `UpdateFailed` → entiteiten unavailable; HA probeert volgend interval opnieuw |
| Time-out (30 s per aanroep) | idem, `poll_timeout` |
| Login geweigerd / token ongeldig | `ConfigEntryAuthFailed` → herauthenticatie-flow |
| Apparaat offline volgens VeSync | snapshot `online=false`: status `offline`, zones unavailable |
| Zone stopt onverwacht | event `stopped` (of `finished` als ≤ 90 s resterend was) |
| HA herstart tijdens koken | eerste poll leest echte status, geen spookevents |
| Gelijktijdige starts | geweigerd met `start_in_progress` |
| SwitchBot-fout / niet beschikbaar / switch mode | duidelijke fout, vóór versturen gecontroleerd waar mogelijk |
| Onbevestigde start | fout met time-out in de melding; sensor "Laatste start" = mislukt |

## Logging en privacy

pyvesync draait met `redact=True`. De integratie logt geen gebruikersnaam,
wachtwoord, token, account-ID of cid. Diagnostics redigeren dezelfde velden
(gecontroleerd in `test_diagnostics_have_no_secrets`).
