"""Generate strings.json, translations/en.json and translations/nl.json with identical keys."""

import json
from pathlib import Path
import sys

ROOT = Path(sys.argv[1])

ZONE_STATUS = {
    "en": {
        "standby": "Idle",
        "ready": "Ready (waiting for start button)",
        "cooking": "Cooking",
        "paused": "Paused",
        "basket_out": "Basket out",
        "hold": "Waiting (sync)",
        "unknown": "Unknown",
    },
    "nl": {
        "standby": "Inactief",
        "ready": "Klaar (wacht op startknop)",
        "cooking": "Bezig",
        "paused": "Gepauzeerd",
        "basket_out": "Mand eruit",
        "hold": "Wacht (sync)",
        "unknown": "Onbekend",
    },
}
PROGRAM = {
    "en": {
        "airfry": "Air fry",
        "roast": "Roast",
        "bake": "Bake",
        "grill": "Grill",
        "reheat": "Reheat",
        "dry": "Dry",
    },
    "nl": {
        "airfry": "Airfry",
        "roast": "Braden",
        "bake": "Bakken",
        "grill": "Grillen",
        "reheat": "Opwarmen",
        "dry": "Drogen",
    },
}
DEVICE_STATUS = {
    "en": {
        "offline": "Offline",
        "idle": "Idle",
        "ready": "Ready",
        "cooking": "Cooking",
        "paused": "Paused",
    },
    "nl": {
        "offline": "Offline",
        "idle": "Inactief",
        "ready": "Klaar",
        "cooking": "Bezig",
        "paused": "Gepauzeerd",
    },
}
SYNC = {
    "en": {"off": "Off", "match": "Match", "sync": "Sync"},
    "nl": {"off": "Uit", "match": "Match", "sync": "Sync"},
}
OUTCOME = {
    "en": {
        "none": "None",
        "in_progress": "In progress",
        "success": "Confirmed",
        "failed": "Failed",
    },
    "nl": {"none": "Geen", "in_progress": "Bezig", "success": "Bevestigd", "failed": "Mislukt"},
}
EVENTS = {
    "en": {
        "started": "Started",
        "ready": "Ready",
        "paused": "Paused",
        "resumed": "Resumed",
        "finished": "Finished",
        "stopped": "Stopped",
    },
    "nl": {
        "started": "Gestart",
        "ready": "Klaar om te starten",
        "paused": "Gepauzeerd",
        "resumed": "Hervat",
        "finished": "Klaar",
        "stopped": "Gestopt",
    },
}
METHOD = {
    "en": {
        "native": "Native (VeSync)",
        "switchbot": "SwitchBot Button Pusher",
        "auto": "Automatic (native, then SwitchBot)",
    },
    "nl": {
        "native": "Native (VeSync)",
        "switchbot": "SwitchBot Button Pusher",
        "auto": "Automatisch (eerst native, dan SwitchBot)",
    },
}
ZONE_SEL = {
    "en": {
        "zone_1": "Zone 1 (left)",
        "zone_2": "Zone 2 (right)",
        "both": "Both zones (each its own settings)",
        "match": "Match: zone 1 settings in both zones",
        "whole": "Whole basket (divider removed)",
    },
    "nl": {
        "zone_1": "Zone 1 (links)",
        "zone_2": "Zone 2 (rechts)",
        "both": "Beide zones (eigen instellingen)",
        "match": "Match: instellingen zone 1 in beide zones",
        "whole": "Hele mand (scheidingswand eruit)",
    },
}

T = {
    "en": {
        "user_title": "VeSync account",
        "user_desc": "Log in with the account you use in the VeSync app. The password is stored in Home Assistant and never logged.",
        "username": "E-mail address",
        "password": "Password",
        "country": "Account country (ISO code, e.g. NL)",
        "device_title": "Choose the air fryer",
        "device": "Air fryer",
        "reauth_title": "Log in again",
        "reauth_desc": "VeSync rejected the stored login for {username}. Enter the password again.",
        "invalid_auth": "Login rejected by VeSync.",
        "cannot_connect": "Could not reach VeSync.",
        "unknown": "Unexpected error, see the log.",
        "no_devices": "No COSORI dual-chamber air fryer found in this account.",
        "device_missing": "The configured air fryer is no longer in this account.",
        "already_configured": "This air fryer is already configured.",
        "reauth_successful": "Login updated.",
        "options_title": "Start method and timing",
        "options_desc": "Native sends the start through VeSync. SwitchBot loads the program, waits until the fryer reports it is ready and then lets the Bot press the physical start button. Automatic tries native first and uses the SwitchBot only when the fryer waits for its button. A start only counts once VeSync reports the zone cooking. The Bot's press duration is set in the SwitchBot app; Home Assistant cannot change it.",
        "start_method": "Start method",
        "switchbot_entity": "SwitchBot Bot (button or switch in press mode)",
        "press_delay": "Wait before pressing",
        "ready_timeout": "Time-out waiting for 'ready'",
        "confirm_timeout": "Time-out confirming the start",
        "scan_active": "Poll interval while cooking",
        "scan_idle": "Poll interval while idle",
        "switchbot_required": "Choose the SwitchBot entity for this start method.",
        "switchbot_wrong_domain": "Choose a button or switch entity.",
        "switchbot_not_found": "Entity not found.",
        "switchbot_switch_mode": "This Bot is in switch mode; set it to press mode in the SwitchBot app.",
        "zone_status": "Zone {zone} status",
        "zone_program": "Zone {zone} program",
        "zone_set_temperature": "Zone {zone} set temperature",
        "zone_set_time": "Zone {zone} set time",
        "zone_remaining_time": "Zone {zone} remaining time",
        "zone_ends_at": "Zone {zone} ready at",
        "device_status": "Status",
        "sync_mode": "Sync mode",
        "last_poll": "Last successful update",
        "last_start": "Last start",
        "zone_cooking": "Zone {zone} cooking",
        "online": "Online",
        "zone_start": "Start zone {zone}",
        "zone_stop": "Stop zone {zone}",
        "start_both": "Start both zones",
        "match_start": "Match start (zone 1 settings in both)",
        "stop_both": "Stop both zones",
        "zone_temperature": "Zone {zone} temperature",
        "zone_time": "Zone {zone} cook time",
        "zone_program_setting": "Zone {zone} program choice",
        "zone_event": "Zone {zone} event",
        "ex": {
            "auth_failed": "VeSync rejected the login; reconfigure the account.",
            "cannot_connect": "Could not reach VeSync ({error}).",
            "device_not_found": "The air fryer was not found in the VeSync account.",
            "poll_failed": "Updating the air fryer failed: {error}",
            "poll_timeout": "VeSync did not answer in time.",
            "start_in_progress": "A start is already in progress; wait for it to finish.",
            "zone_busy": "Zone {zone} is busy ({status}); stop it first.",
            "other_zone_active": "Zone {zone} is active. The SwitchBot is not pressed while another zone runs, because the start/pause button could pause it.",
            "both_needs_equal_settings": "With the SwitchBot both zones can only start together with identical settings (one press). Use Match start or start the zones one at a time.",
            "command_rejected": "The air fryer or VeSync refused the command: {error}",
            "command_timeout": "The command to VeSync timed out.",
            "waiting_for_button": "The air fryer accepted the program but waits for its start button. Press start on the fryer, or configure a SwitchBot.",
            "start_not_confirmed": "The start was accepted by the API but VeSync did not report the zone cooking within {timeout} s.",
            "not_ready": "The air fryer did not report 'ready' within {timeout} s; the SwitchBot was not pressed.",
            "not_confirmed_after_press": "The SwitchBot pressed the button, but VeSync did not report cooking within {timeout} s.",
            "ready_start_unavailable": "The installed pyvesync version does not support the ready-start request needed for the SwitchBot route.",
            "not_reachable": "The air fryer could not be read ({error}).",
            "device_offline": "VeSync reports the air fryer as offline.",
            "switchbot_not_configured": "No SwitchBot entity configured.",
            "switchbot_wrong_domain": "{entity_id} is not a button or switch.",
            "switchbot_unavailable": "SwitchBot {entity_id} is unavailable.",
            "switchbot_switch_mode": "SwitchBot {entity_id} is in switch mode; set it to press mode.",
            "switchbot_failed": "Pressing SwitchBot {entity_id} failed ({error}).",
            "stop_rejected": "Stopping zone {zone} was refused: {error}",
            "stop_not_confirmed": "VeSync did not confirm the stop within {timeout} s.",
            "program_not_supported": "This air fryer has no program {program}.",
            "temperature_out_of_range": "{temperature} is outside {min}-{max} for {program}.",
            "time_out_of_range": "{minutes} min is outside 1-{max} min for {program}.",
            "unknown_device": "Choose a COSORI TwinFry device.",
            "entry_not_loaded": "The air fryer is not loaded.",
        },
        "svc_start": "Start cook",
        "svc_start_desc": "Start a cook after an explicit request. Optional values replace the staged settings of the zone first. Returns only after VeSync confirms the zone is cooking.",
        "svc_stop": "Stop cook",
        "svc_stop_desc": "End the cook (or a loaded program) and wait until VeSync reports idle.",
        "f_device": "Air fryer",
        "f_zone": "Zone",
        "f_program": "Program",
        "f_temperature": "Temperature",
        "f_duration": "Cook time",
        "f_method": "Start method",
        "f_device_d": "The COSORI TwinFry device.",
        "f_zone_d": "Which zone(s).",
        "f_program_d": "Program to stage first (loads its defaults).",
        "f_temperature_d": "Temperature to stage.",
        "f_duration_d": "Minutes to stage.",
        "f_method_d": "Overrides the configured start method once.",
    },
    "nl": {
        "user_title": "VeSync-account",
        "user_desc": "Log in met het account van de VeSync-app. Het wachtwoord wordt in Home Assistant opgeslagen en nooit gelogd.",
        "username": "E-mailadres",
        "password": "Wachtwoord",
        "country": "Land van het account (ISO-code, bijv. NL)",
        "device_title": "Kies de airfryer",
        "device": "Airfryer",
        "reauth_title": "Opnieuw inloggen",
        "reauth_desc": "VeSync weigert de opgeslagen login voor {username}. Vul het wachtwoord opnieuw in.",
        "invalid_auth": "Login geweigerd door VeSync.",
        "cannot_connect": "VeSync is niet bereikbaar.",
        "unknown": "Onverwachte fout, zie het logboek.",
        "no_devices": "Geen COSORI-airfryer met twee zones gevonden in dit account.",
        "device_missing": "De ingestelde airfryer staat niet meer in dit account.",
        "already_configured": "Deze airfryer is al ingesteld.",
        "reauth_successful": "Login bijgewerkt.",
        "options_title": "Startmethode en tijden",
        "options_desc": "Native start via VeSync. SwitchBot laadt het programma, wacht tot de airfryer meldt dat hij klaarstaat en laat dan de Bot de fysieke startknop indrukken. Automatisch probeert eerst native en gebruikt de SwitchBot alleen als de airfryer op zijn knop wacht. Een start telt pas als VeSync meldt dat de zone kookt. De drukduur van de Bot stel je in de SwitchBot-app in; Home Assistant kan die niet wijzigen.",
        "start_method": "Startmethode",
        "switchbot_entity": "SwitchBot Bot (knop of schakelaar in press mode)",
        "press_delay": "Wachttijd vóór het indrukken",
        "ready_timeout": "Time-out wachten op 'klaar'",
        "confirm_timeout": "Time-out bevestiging start",
        "scan_active": "Poll-interval tijdens koken",
        "scan_idle": "Poll-interval in rust",
        "switchbot_required": "Kies de SwitchBot-entiteit voor deze startmethode.",
        "switchbot_wrong_domain": "Kies een knop- of schakelaarentiteit.",
        "switchbot_not_found": "Entiteit niet gevonden.",
        "switchbot_switch_mode": "Deze Bot staat in switch mode; zet hem in de SwitchBot-app op press mode.",
        "zone_status": "Zone {zone} status",
        "zone_program": "Zone {zone} programma",
        "zone_set_temperature": "Zone {zone} ingestelde temperatuur",
        "zone_set_time": "Zone {zone} ingestelde tijd",
        "zone_remaining_time": "Zone {zone} resterende tijd",
        "zone_ends_at": "Zone {zone} klaar om",
        "device_status": "Status",
        "sync_mode": "Sync-modus",
        "last_poll": "Laatste geslaagde update",
        "last_start": "Laatste start",
        "zone_cooking": "Zone {zone} kookt",
        "online": "Online",
        "zone_start": "Start zone {zone}",
        "zone_stop": "Stop zone {zone}",
        "start_both": "Start beide zones",
        "match_start": "Match-start (zone 1 in beide)",
        "stop_both": "Stop beide zones",
        "zone_temperature": "Zone {zone} temperatuur",
        "zone_time": "Zone {zone} kooktijd",
        "zone_program_setting": "Zone {zone} programmakeuze",
        "zone_event": "Zone {zone} gebeurtenis",
        "ex": {
            "auth_failed": "VeSync weigert de login; stel het account opnieuw in.",
            "cannot_connect": "VeSync is niet bereikbaar ({error}).",
            "device_not_found": "De airfryer staat niet in het VeSync-account.",
            "poll_failed": "Bijwerken van de airfryer mislukt: {error}",
            "poll_timeout": "VeSync antwoordde niet op tijd.",
            "start_in_progress": "Er loopt al een start; wacht tot die klaar is.",
            "zone_busy": "Zone {zone} is bezig ({status}); stop die eerst.",
            "other_zone_active": "Zone {zone} is actief. De SwitchBot drukt niet terwijl een andere zone loopt, omdat de start/pauzeknop die zone kan pauzeren.",
            "both_needs_equal_settings": "Met de SwitchBot kunnen beide zones alleen samen starten met identieke instellingen (één druk). Gebruik Match-start of start de zones na elkaar.",
            "command_rejected": "De airfryer of VeSync weigerde de opdracht: {error}",
            "command_timeout": "De opdracht aan VeSync duurde te lang.",
            "waiting_for_button": "De airfryer heeft het programma aangenomen maar wacht op zijn startknop. Druk op start op de airfryer of stel een SwitchBot in.",
            "start_not_confirmed": "De API accepteerde de start, maar VeSync meldde binnen {timeout} s niet dat de zone kookt.",
            "not_ready": "De airfryer meldde binnen {timeout} s geen 'klaar'; de SwitchBot is niet ingedrukt.",
            "not_confirmed_after_press": "De SwitchBot heeft gedrukt, maar VeSync meldde binnen {timeout} s niet dat de zone kookt.",
            "ready_start_unavailable": "De geïnstalleerde pyvesync-versie ondersteunt het klaarzet-verzoek voor de SwitchBot-route niet.",
            "not_reachable": "De airfryer kon niet worden uitgelezen ({error}).",
            "device_offline": "VeSync meldt de airfryer als offline.",
            "switchbot_not_configured": "Geen SwitchBot-entiteit ingesteld.",
            "switchbot_wrong_domain": "{entity_id} is geen knop of schakelaar.",
            "switchbot_unavailable": "SwitchBot {entity_id} is niet beschikbaar.",
            "switchbot_switch_mode": "SwitchBot {entity_id} staat in switch mode; zet hem op press mode.",
            "switchbot_failed": "Indrukken met SwitchBot {entity_id} mislukt ({error}).",
            "stop_rejected": "Stoppen van zone {zone} geweigerd: {error}",
            "stop_not_confirmed": "VeSync bevestigde het stoppen niet binnen {timeout} s.",
            "program_not_supported": "Deze airfryer heeft geen programma {program}.",
            "temperature_out_of_range": "{temperature} valt buiten {min}-{max} voor {program}.",
            "time_out_of_range": "{minutes} min valt buiten 1-{max} min voor {program}.",
            "unknown_device": "Kies een COSORI TwinFry-apparaat.",
            "entry_not_loaded": "De airfryer is niet geladen.",
        },
        "svc_start": "Kookproces starten",
        "svc_start_desc": "Start een kookproces na een expliciete opdracht. Opgegeven waarden vervangen eerst de klaargezette instellingen van de zone. Rondt pas af als VeSync bevestigt dat de zone kookt.",
        "svc_stop": "Kookproces stoppen",
        "svc_stop_desc": "Beëindig het kookproces (of een klaargezet programma) en wacht tot VeSync 'inactief' meldt.",
        "f_device": "Airfryer",
        "f_zone": "Zone",
        "f_program": "Programma",
        "f_temperature": "Temperatuur",
        "f_duration": "Kooktijd",
        "f_method": "Startmethode",
        "f_device_d": "Het COSORI TwinFry-apparaat.",
        "f_zone_d": "Welke zone(s).",
        "f_program_d": "Eerst klaar te zetten programma (laadt de standaardwaarden).",
        "f_temperature_d": "Klaar te zetten temperatuur.",
        "f_duration_d": "Klaar te zetten minuten.",
        "f_method_d": "Overschrijft eenmalig de ingestelde startmethode.",
    },
}


def build(lang: str) -> dict:
    t = T[lang]
    errors = {
        k: t[k]
        for k in ("invalid_auth", "cannot_connect", "unknown", "no_devices", "device_missing")
    }
    opt_errors = {
        k: t[k]
        for k in (
            "switchbot_required",
            "switchbot_wrong_domain",
            "switchbot_not_found",
            "switchbot_switch_mode",
        )
    }

    def zone_names(key: str, extra: dict | None = None) -> dict:
        return {"name": t[key], **(extra or {})}

    return {
        "config": {
            "step": {
                "user": {
                    "title": t["user_title"],
                    "description": t["user_desc"],
                    "data": {
                        "username": t["username"],
                        "password": t["password"],
                        "country_code": t["country"],
                    },
                },
                "device": {"title": t["device_title"], "data": {"device_cid": t["device"]}},
                "reauth_confirm": {
                    "title": t["reauth_title"],
                    "description": t["reauth_desc"],
                    "data": {"password": t["password"]},
                },
            },
            "error": errors,
            "abort": {
                "already_configured": t["already_configured"],
                "reauth_successful": t["reauth_successful"],
            },
        },
        "options": {
            "step": {
                "init": {
                    "title": t["options_title"],
                    "description": t["options_desc"],
                    "data": {
                        "start_method": t["start_method"],
                        "switchbot_entity": t["switchbot_entity"],
                        "press_delay": t["press_delay"],
                        "ready_timeout": t["ready_timeout"],
                        "confirm_timeout": t["confirm_timeout"],
                        "scan_interval_active": t["scan_active"],
                        "scan_interval_idle": t["scan_idle"],
                    },
                }
            },
            "error": opt_errors,
        },
        "selector": {
            "start_method": {"options": METHOD[lang]},
            "zone": {"options": ZONE_SEL[lang]},
            "program": {"options": PROGRAM[lang]},
        },
        "entity": {
            "sensor": {
                "zone_status": zone_names("zone_status", {"state": ZONE_STATUS[lang]}),
                "zone_program": zone_names("zone_program", {"state": PROGRAM[lang]}),
                "zone_set_temperature": zone_names("zone_set_temperature"),
                "zone_set_time": zone_names("zone_set_time"),
                "zone_remaining_time": zone_names("zone_remaining_time"),
                "zone_ends_at": zone_names("zone_ends_at"),
                "device_status": zone_names("device_status", {"state": DEVICE_STATUS[lang]}),
                "sync_mode": zone_names("sync_mode", {"state": SYNC[lang]}),
                "last_poll": zone_names("last_poll"),
                "last_start": zone_names("last_start", {"state": OUTCOME[lang]}),
            },
            "binary_sensor": {
                "zone_cooking": zone_names("zone_cooking"),
                "online": zone_names("online"),
            },
            "button": {
                k: zone_names(k)
                for k in ("zone_start", "zone_stop", "start_both", "match_start", "stop_both")
            },
            "number": {
                "zone_temperature": zone_names("zone_temperature"),
                "zone_time": zone_names("zone_time"),
            },
            "select": {
                "zone_program_setting": zone_names("zone_program_setting", {"state": PROGRAM[lang]})
            },
            "event": {
                "zone_event": zone_names(
                    "zone_event", {"state_attributes": {"event_type": {"state": EVENTS[lang]}}}
                )
            },
        },
        "exceptions": {k: {"message": v} for k, v in t["ex"].items()},
        "services": {
            "start_cook": {
                "name": t["svc_start"],
                "description": t["svc_start_desc"],
                "fields": {
                    "device_id": {"name": t["f_device"], "description": t["f_device_d"]},
                    "zone": {"name": t["f_zone"], "description": t["f_zone_d"]},
                    "program": {"name": t["f_program"], "description": t["f_program_d"]},
                    "temperature": {
                        "name": t["f_temperature"],
                        "description": t["f_temperature_d"],
                    },
                    "duration": {"name": t["f_duration"], "description": t["f_duration_d"]},
                    "method": {"name": t["f_method"], "description": t["f_method_d"]},
                },
            },
            "stop_cook": {
                "name": t["svc_stop"],
                "description": t["svc_stop_desc"],
                "fields": {
                    "device_id": {"name": t["f_device"], "description": t["f_device_d"]},
                    "zone": {"name": t["f_zone"], "description": t["f_zone_d"]},
                },
            },
        },
    }


def dump(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


en = build("en")
dump(ROOT / "strings.json", en)
dump(ROOT / "translations" / "en.json", en)
dump(ROOT / "translations" / "nl.json", build("nl"))
print("written")
