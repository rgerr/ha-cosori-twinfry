"""A simulated VeSync cloud + CAF-TF101S used by the tests.

Only the network layer is fake: pyvesync's real ``VeSync`` manager, device
classes, request builders and response parsing run unchanged. That makes the
tests check the actual request bodies pyvesync (and ``fryer_ext``) send.

The fryer's start behaviour is configurable because it is exactly what has
not been verified on hardware:

``native_behaviour``
    ``"starts"``  readyStart false starts cooking at once (pyvesync's assumption)
    ``"ready"``   readyStart false only loads the program (waits for the button)
    ``"ignore"``  the API accepts the command but nothing happens
``ready_behaviour``
    ``"ready"``   readyStart true loads the program and waits for the button
    ``"ignore"``  accepted but nothing happens
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from pyvesync import VeSync
from pyvesync.utils.errors import VeSyncLoginError

CID = "tf101s-cid-0001"
ACCOUNT_ID = "acct-0001"
DEVICE_TYPE = "CAF-TF101S-AEU"


@dataclass
class Chamber:
    """Simulated chamber."""

    status: str = "standby"
    mode: str = ""
    recipe_name: str = ""
    recipe_id: int = 0
    set_time: int = 0
    temp: int = 0
    remaining: int = 0

    def item(self, number: int) -> dict[str, Any]:
        active = self.status != "standby"
        return {
            "cookStatus": self.status,
            "startTime": 1768667721 if active else 0,
            "recipeType": 3,
            "recipeId": self.recipe_id if active else 0,
            "recipeName": self.recipe_name if active else "",
            "upc": "",
            "holdTime": 0,
            "cookSetTime": self.set_time if active else 0,
            "cookTemp": self.temp if active else 0,
            "mode": self.mode or "AirFry",
            "currentRemainingTime": self.remaining if active else 0,
            "totalTimeRemaining": self.remaining if active else 0,
            "chamber": number,
        }


@dataclass
class FakeCloud:
    """Simulated VeSync cloud with one TwinFry."""

    native_behaviour: str = "starts"
    ready_behaviour: str = "ready"
    online: bool = True
    reject_login: bool = False
    reject_start_code: int | None = None
    fail_polls: int = 0
    poll_exception: Exception | None = None
    chambers: dict[int, Chamber] = field(
        default_factory=lambda: {1: Chamber(), 2: Chamber(), 3: Chamber()}
    )
    work_chamber: int = 0
    sync_type: int = 0
    requests: list[dict[str, Any]] = field(default_factory=list)
    devices: list[dict[str, Any]] | None = None

    # ------------------------------------------------------------ helpers

    def device_item(self, cid: str = CID, name: str = "TwinFry") -> dict[str, Any]:
        return {
            "deviceRegion": "EU",
            "isOwner": True,
            "deviceName": name,
            "deviceImg": "",
            "cid": cid,
            "uuid": f"{cid}-uuid",
            "macID": "00:11:22:33:44:55",
            "connectionType": "wifi",
            "deviceType": DEVICE_TYPE,
            "type": "airFryer",
            "configModule": "WiFiBTOnboardingNotify_AirFryer_CAF-TF101S_EU",
            "currentFirmVersion": "1.0.10",
            "deviceStatus": "on",
            "connectionStatus": "online" if self.online else "offline",
            "subDeviceNo": 0,
        }

    def sent(self, method: str) -> list[dict[str, Any]]:
        """Return the payload data of every request with this payload method."""
        return [
            r["payload"]["data"]
            for r in self.requests
            if r.get("payload", {}).get("method") == method
        ]

    def press_start_button(self) -> None:
        """What a physical press of the start button does (assumed)."""
        for chamber in self.chambers.values():
            if chamber.status == "ready":
                chamber.status = "cooking"

    def finish(self, number: int) -> None:
        self.chambers[number] = Chamber()
        if self.work_chamber in (3, 4) or not any(
            c.status != "standby" for c in self.chambers.values()
        ):
            self.work_chamber = 0

    # ----------------------------------------------------------- responses

    @staticmethod
    def _ok(inner: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "traceId": "trace",
            "code": 0,
            "msg": "request success",
            "result": {"traceId": "trace", "code": 0, "result": inner or {}},
        }

    def _status(self) -> dict[str, Any]:
        if self.work_chamber == 3:
            items = [self.chambers[3].item(3)]
        else:
            items = [self.chambers[1].item(1), self.chambers[2].item(2)]
        return self._ok(
            {
                "statusList": items,
                "tempUnit": "c",
                "syncType": self.sync_type,
                "workChamber": self.work_chamber,
            }
        )

    def _start(self, data: dict[str, Any]) -> dict[str, Any]:
        if self.reject_start_code is not None:
            return {"traceId": "t", "code": self.reject_start_code, "msg": "refused"}
        behaviour = self.ready_behaviour if data["readyStart"] else self.native_behaviour
        if behaviour == "ignore":
            return self._ok()
        status = "ready" if (data["readyStart"] or behaviour == "ready") else "cooking"
        self.work_chamber = data["workChamber"]
        self.sync_type = data["syncType"]
        for config in data["cookConfigs"]:
            number = 3 if data["workChamber"] == 3 else config["chamber"]
            self.chambers[number] = Chamber(
                status=status,
                mode=config["mode"],
                recipe_name=config["recipeName"],
                recipe_id=config["recipeId"],
                set_time=config["cookSetTime"],
                temp=config["cookTemp"],
                remaining=config["cookSetTime"],
            )
        return self._ok()

    def _end(self, data: dict[str, Any]) -> dict[str, Any]:
        chamber = data["chamber"]
        targets = (1, 2) if chamber == 4 else (chamber,)
        for number in targets:
            self.chambers[number] = Chamber()
        if chamber in (3, 4) or not any(c.status != "standby" for c in self.chambers.values()):
            self.work_chamber = 0
            self.sync_type = 0
        return self._ok()

    async def call(self, api: str, method: str, json_object: Any = None, **_: Any):
        body = (
            json_object.to_dict() if hasattr(json_object, "to_dict") else copy.deepcopy(json_object)
        )
        self.requests.append(body or {})
        if api.endswith("/cloud/v1/deviceManaged/devices"):
            devices = self.devices if self.devices is not None else [self.device_item()]
            return {
                "traceId": "trace",
                "code": 0,
                "msg": None,
                "result": {"total": len(devices), "pageSize": 100, "pageNo": 1, "list": devices},
            }, 200
        payload = body["payload"]
        name = payload["method"]
        if not self.online:
            return {"traceId": "t", "code": 4041004, "msg": "device offline"}, 200
        if name == "getAirfryerMultiStatus":
            if self.poll_exception is not None:
                raise self.poll_exception
            if self.fail_polls > 0:
                self.fail_polls -= 1
                return None, 200
            return self._status(), 200
        if name == "startMultiCook":
            return self._start(payload["data"]), 200
        if name == "endCook":
            return self._end(payload["data"]), 200
        return {"traceId": "t", "code": -1, "msg": "unknown method"}, 200


class FakeVeSync(VeSync):
    """Real pyvesync manager with the network replaced by ``FakeCloud``."""

    cloud: FakeCloud

    async def login(self) -> bool:
        if self.cloud.reject_login:
            raise VeSyncLoginError("Invalid password")
        self.auth.set_credentials("token-secret", ACCOUNT_ID, "NL", "EU")
        self.enabled = True
        return True

    async def async_call_api(self, api, method, json_object=None, headers=None, device=None):
        return await self.cloud.call(api, method, json_object)
