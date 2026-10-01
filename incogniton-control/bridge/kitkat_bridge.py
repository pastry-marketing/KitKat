"""KitKat's lightweight Windows bridge for the Incogniton local API.

The bridge deliberately contains no Google Sheets or legacy desktop UI code.
It signs in as the KitKat user on that PC, polls that user's agent queue, executes
profile commands against Incogniton on this PC, and syncs safe profile fields
back to KitKat.
"""

from __future__ import annotations

import getpass
import base64
import ctypes
import json
import os
import platform
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SUPABASE_URL = "https://mqxpsagrjbwryqgiyzfr.supabase.co"
SUPABASE_KEY = "sb_publishable_mMEnrqnXRumi1rlNaxXaXw_Wd7bB4t8"
INCOGNITON_URL = os.environ.get("INCOGNITON_URL", "http://127.0.0.1:35000").rstrip("/")
POLL_SECONDS = max(1.0, float(os.environ.get("KITKAT_POLL_SECONDS", "2")))
HEARTBEAT_SECONDS = 20.0
PROFILE_SYNC_SECONDS = 60.0

STATE_DIR = Path(os.environ.get("APPDATA") or Path.home()) / "KitKat Bridge"
STATE_FILE = STATE_DIR / "session.json"


class BridgeError(RuntimeError):
    pass


class HttpError(BridgeError):
    def __init__(self, status: int, message: str, data: Any = None):
        super().__init__(message)
        self.status = status
        self.data = data


class DataBlob(ctypes.Structure):
    _fields_ = [("size", ctypes.c_ulong), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log(message: str) -> None:
    stamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{stamp}] {message}", flush=True)


def _windows_protect(value: str) -> str:
    if os.name != "nt":
        return value
    raw = value.encode("utf-8")
    buffer = ctypes.create_string_buffer(raw)
    source = DataBlob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    destination = DataBlob()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(source), "KitKat Bridge", None, None, None, 0x01, ctypes.byref(destination)
    ):
        raise ctypes.WinError()
    try:
        encrypted = ctypes.string_at(destination.data, destination.size)
        return base64.b64encode(encrypted).decode("ascii")
    finally:
        ctypes.windll.kernel32.LocalFree(destination.data)


def _windows_unprotect(value: str) -> str:
    if os.name != "nt":
        return value
    raw = base64.b64decode(value.encode("ascii"), validate=True)
    buffer = ctypes.create_string_buffer(raw)
    source = DataBlob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    destination = DataBlob()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(source), None, None, None, None, 0x01, ctypes.byref(destination)
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(destination.data, destination.size).decode("utf-8")
    finally:
        ctypes.windll.kernel32.LocalFree(destination.data)


def _decode_response(response: Any) -> Any:
    raw = response.read()
    if not raw:
        return None
    text = raw.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"message": text}


def request_json(
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: Any = None,
    timeout: float = 30,
) -> Any:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request_headers = {"Accept": "application/json", **(headers or {})}
    if data is not None:
        request_headers.setdefault("Content-Type", "application/json")
    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return _decode_response(response)
    except urllib.error.HTTPError as error:
        payload = _decode_response(error)
        message = "Request failed"
        if isinstance(payload, dict):
            message = str(payload.get("message") or payload.get("msg") or payload.get("error_description") or payload.get("error") or message)
        raise HttpError(error.code, message, payload) from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise BridgeError(str(getattr(error, "reason", error))) from error


def load_state() -> dict[str, Any]:
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def save_state(state: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    temporary = STATE_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
    temporary.replace(STATE_FILE)


class SupabaseSession:
    def __init__(self) -> None:
        state = load_state()
        self.access_token = ""
        self.refresh_token = ""
        protected = str(state.get("refresh_token_protected") or "")
        if protected:
            try:
                self.refresh_token = _windows_unprotect(protected)
            except Exception:
                self.refresh_token = ""
        elif state.get("refresh_token"):
            self.refresh_token = str(state["refresh_token"])
        self.expires_at = 0.0
        self.user: dict[str, Any] = {}

    def _auth_request(self, grant_type: str, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{SUPABASE_URL}/auth/v1/token?grant_type={grant_type}"
        result = request_json(url, "POST", {"apikey": SUPABASE_KEY}, body)
        if not isinstance(result, dict) or not result.get("access_token"):
            raise BridgeError("Supabase did not return a valid session")
        return result

    def _apply(self, result: dict[str, Any]) -> None:
        self.access_token = str(result["access_token"])
        self.refresh_token = str(result.get("refresh_token") or self.refresh_token)
        self.expires_at = time.time() + max(30, int(result.get("expires_in") or 3600) - 60)
        self.user = result.get("user") or self.user
        save_state({
            "refresh_token_protected": _windows_protect(self.refresh_token),
            "email": self.user.get("email"),
            "updated_at": utc_now(),
        })

    def sign_in(self) -> None:
        print()
        print("Connect this PC to KitKat")
        print("Use your own account from the KitKat website.")
        email = input("Email: ").strip()
        password = getpass.getpass("Password: ")
        if not email or not password:
            raise BridgeError("Email and password are required")
        self._apply(self._auth_request("password", {"email": email, "password": password}))

    def refresh(self) -> None:
        if not self.refresh_token:
            self.sign_in()
            return
        try:
            self._apply(self._auth_request("refresh_token", {"refresh_token": self.refresh_token}))
        except HttpError as error:
            if error.status not in (400, 401):
                raise
            log("The saved KitKat session expired. Please sign in again.")
            self.refresh_token = ""
            self.sign_in()

    def ensure(self, force: bool = False) -> str:
        if force or not self.access_token or time.time() >= self.expires_at:
            self.refresh()
        return self.access_token


class SupabaseRest:
    def __init__(self, session: SupabaseSession) -> None:
        self.session = session

    def request(
        self,
        table: str,
        method: str = "GET",
        query: list[tuple[str, str]] | None = None,
        body: Any = None,
        prefer: str | None = None,
        retry_auth: bool = True,
    ) -> Any:
        suffix = urllib.parse.urlencode(query or [], doseq=True)
        url = f"{SUPABASE_URL}/rest/v1/{table}" + (f"?{suffix}" if suffix else "")
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {self.session.ensure()}",
        }
        if prefer:
            headers["Prefer"] = prefer
        try:
            return request_json(url, method, headers, body)
        except HttpError as error:
            if retry_auth and error.status == 401:
                self.session.ensure(force=True)
                return self.request(table, method, query, body, prefer, retry_auth=False)
            raise


class IncognitonClient:
    RETRYABLE_STATUSES = {429, 500, 502, 503, 504}

    def request(self, endpoint: str, method: str = "GET", body: Any = None, timeout: float = 30) -> Any:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                result = request_json(f"{INCOGNITON_URL}{endpoint}", method, body=body, timeout=timeout)
                if isinstance(result, dict) and result.get("status") == "error":
                    raise BridgeError(str(result.get("message") or "Incogniton returned an error"))
                return result
            except HttpError as error:
                last_error = error
                if error.status not in self.RETRYABLE_STATUSES:
                    raise
            except BridgeError as error:
                last_error = error
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
        raise BridgeError(f"Incogniton is unavailable at {INCOGNITON_URL}: {last_error}")

    def profiles(self) -> list[dict[str, Any]]:
        result = self.request("/profile/all")
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            profiles = result.get("profileData") or result.get("profiles") or []
            if isinstance(profiles, list):
                return profiles
        raise BridgeError("Incogniton returned an unexpected profile list")


class KitKatBridge:
    SUPPORTED_ACTIONS = {
        "sync_profiles",
        "create_profile",
        "launch_profile",
        "stop_profile",
        "clone_profile",
        "delete_profile",
    }

    def __init__(self) -> None:
        self.session = SupabaseSession()
        self.db = SupabaseRest(self.session)
        self.incogniton = IncognitonClient()
        self.workspace_id = ""
        self.user_id = ""
        self.role = ""
        self.allowed_groups: set[str] | None = set()
        self.agent: dict[str, Any] = {}
        self.last_heartbeat = 0.0
        self.last_sync = 0.0

    def setup(self) -> None:
        self.session.ensure()
        self.user_id = str(self.session.user.get("id") or "")
        if not self.user_id:
            raise BridgeError("The KitKat session does not contain a user ID")

        memberships = self.db.request("workspace_members", query=[
            ("select", "workspace_id,role,active"),
            ("user_id", f"eq.{self.user_id}"),
            ("active", "eq.true"),
            ("limit", "1"),
        ]) or []
        if not memberships:
            raise BridgeError("Open KitKat in the browser and finish creating the workspace first")
        membership = memberships[0]
        self.workspace_id = str(membership["workspace_id"])
        self.role = str(membership.get("role") or "")
        if self.role == "super_admin":
            self.allowed_groups = None
        else:
            access_rows = self.db.request("member_group_access", query=[
                ("select", "group_name"),
                ("workspace_id", f"eq.{self.workspace_id}"),
                ("user_id", f"eq.{self.user_id}"),
            ]) or []
            self.allowed_groups = {
                str(row.get("group_name") or "").strip()
                for row in access_rows
                if str(row.get("group_name") or "").strip()
            }
        self.agent = self._find_or_create_agent()
        self.heartbeat()

    def _find_or_create_agent(self) -> dict[str, Any]:
        machine = (platform.node() or os.environ.get("COMPUTERNAME") or "Windows PC")[:80]
        agents = self.db.request("agents", query=[
            ("select", "*"),
            ("workspace_id", f"eq.{self.workspace_id}"),
            ("created_by", f"eq.{self.user_id}"),
            ("machine_label", f"eq.{machine}"),
            ("limit", "1"),
        ]) or []
        if agents:
            agent = agents[0]
            updated = self.db.request("agents", "PATCH", [("id", f"eq.{agent['id']}")], {
                "active": True,
                "last_seen_at": utc_now(),
            }, "return=representation")
            return (updated or [agent])[0]

        created = self.db.request("agents", "POST", body={
            "workspace_id": self.workspace_id,
            "name": f"{machine} Bridge"[:80],
            "machine_label": machine,
            "active": True,
            "last_seen_at": utc_now(),
            "created_by": self.user_id,
        }, prefer="return=representation")
        if not created:
            raise BridgeError("KitKat could not register this PC")
        return created[0]

    def heartbeat(self) -> None:
        self.db.request("agents", "PATCH", [("id", f"eq.{self.agent['id']}")], {
            "active": True,
            "last_seen_at": utc_now(),
        }, "return=minimal")
        self.last_heartbeat = time.monotonic()

    @staticmethod
    def _profile_row(profile: dict[str, Any], workspace_id: str, agent_id: str) -> dict[str, Any] | None:
        info = (
            profile.get("general_profile_information")
            or profile.get("General_profile_information")
            or profile.get("generalProfileInformation")
            or {}
        )
        profile_id = info.get("browser_id") or profile.get("profile_browser_id") or profile.get("browser_id")
        if not profile_id:
            return None
        name = info.get("profile_name") or profile.get("profile_name") or str(profile_id)
        group_name = info.get("profile_group") or profile.get("profile_group") or profile.get("group") or "Unassigned"
        platform_name = info.get("simulated_operating_system") or profile.get("platform")
        status = profile.get("profile_status") or profile.get("status") or "unknown"
        return {
            "workspace_id": workspace_id,
            "profile_id": str(profile_id),
            "agent_id": agent_id,
            "name": str(name)[:200],
            "group_name": str(group_name)[:200],
            "platform": str(platform_name)[:80] if platform_name else None,
            "status": str(status)[:40],
            "last_synced_at": utc_now(),
            "metadata": {"source": "incogniton"},
        }

    def sync_profiles(self) -> int:
        profiles = self.incogniton.profiles()
        rows = []
        for profile in profiles:
            row = self._profile_row(profile, self.workspace_id, str(self.agent["id"]))
            if row is None:
                continue
            if self.allowed_groups is not None and row["group_name"] not in self.allowed_groups:
                continue
            rows.append(row)
        if rows:
            self.db.request("browser_profiles", "POST", [("on_conflict", "workspace_id,profile_id")], rows,
                            "resolution=merge-duplicates,return=minimal")

        current_ids = {row["profile_id"] for row in rows}
        existing = self.db.request("browser_profiles", query=[
            ("select", "profile_id"),
            ("workspace_id", f"eq.{self.workspace_id}"),
            ("agent_id", f"eq.{self.agent['id']}"),
        ]) or []
        for item in existing:
            profile_id = str(item.get("profile_id") or "")
            if profile_id and profile_id not in current_ids:
                self.db.request("browser_profiles", "DELETE", [
                    ("workspace_id", f"eq.{self.workspace_id}"),
                    ("agent_id", f"eq.{self.agent['id']}"),
                    ("profile_id", f"eq.{profile_id}"),
                ], prefer="return=minimal")
        self.last_sync = time.monotonic()
        return len(rows)

    def _claim(self, command_id: str) -> dict[str, Any] | None:
        rows = self.db.request("commands", "PATCH", [
            ("id", f"eq.{command_id}"),
            ("status", "eq.queued"),
        ], {"status": "claimed", "claimed_at": utc_now()}, "return=representation") or []
        return rows[0] if rows else None

    def _finish(self, command_id: str, result: Any = None, error: str | None = None) -> None:
        body = {
            "status": "failed" if error else "completed",
            "completed_at": utc_now(),
            "result": None if error else (result if isinstance(result, dict) else {"value": result}),
            "error_message": str(error)[:1000] if error else None,
        }
        self.db.request("commands", "PATCH", [("id", f"eq.{command_id}")], body, "return=minimal")

    def _execute(self, command: dict[str, Any]) -> Any:
        action = str(command.get("action") or "")
        profile_id = str(command.get("profile_id") or "")
        payload = command.get("payload") if isinstance(command.get("payload"), dict) else {}
        if action not in self.SUPPORTED_ACTIONS:
            raise BridgeError(f"'{action}' is not installed in the lightweight bridge yet")
        if action == "sync_profiles":
            return {"profiles_synced": self.sync_profiles()}
        if action == "create_profile":
            name = str(payload.get("profile_name") or "").strip()
            if not name:
                raise BridgeError("Profile name is required")
            group_name = str(payload.get("profile_group") or "Unassigned").strip()
            if self.allowed_groups is not None and group_name not in self.allowed_groups:
                raise BridgeError(f"Your KitKat account does not have access to group '{group_name}'")
            request_body = {
                "profile_name": name,
                "platform": payload.get("platform") or "windows",
                "profile_group": group_name,
            }
            if str(payload.get("userAgent") or "").strip():
                request_body["userAgent"] = str(payload["userAgent"]).strip()
            result = self.incogniton.request("/profile/add", "POST", request_body, 60)
            self.sync_profiles()
            return result
        if not profile_id:
            raise BridgeError("The command is missing an Incogniton profile ID")
        encoded = urllib.parse.quote(profile_id, safe="")
        if action == "launch_profile":
            result = self.incogniton.request(f"/profile/launch/{encoded}", timeout=120)
            self.sync_profiles()
            return result
        if action == "stop_profile":
            result = self.incogniton.request(f"/profile/stop/{encoded}", timeout=45)
            self.sync_profiles()
            return result
        if action == "clone_profile":
            request_body = {
                "profile_browser_id": profile_id,
                "clone_cookies": payload.get("clone_cookies") is not False,
                "clone_advanced_other_settings": True,
                "clone_useragent": True,
                "clone_other_browser_data": True,
            }
            if str(payload.get("profile_name") or "").strip():
                request_body["profile_name"] = str(payload["profile_name"]).strip()
            if str(payload.get("target_group") or "").strip():
                request_body["target_group"] = str(payload["target_group"]).strip()
            result = self.incogniton.request("/profile/clone", "POST", request_body, 120)
            self.sync_profiles()
            return result
        result = self.incogniton.request(f"/profile/delete/{encoded}", timeout=60)
        self.sync_profiles()
        return result

    def process_commands(self) -> int:
        commands = self.db.request("commands", query=[
            ("select", "*"),
            ("agent_id", f"eq.{self.agent['id']}"),
            ("status", "eq.queued"),
            ("order", "created_at.asc"),
            ("limit", "10"),
        ]) or []
        handled = 0
        for queued in commands:
            command = self._claim(str(queued["id"]))
            if not command:
                continue
            handled += 1
            action = str(command.get("action") or "command")
            log(f"Running {action.replace('_', ' ')}")
            try:
                result = self._execute(command)
                self._finish(str(command["id"]), result=result)
                log(f"Completed {action.replace('_', ' ')}")
            except Exception as error:
                self._finish(str(command["id"]), error=str(error))
                log(f"Failed {action.replace('_', ' ')}: {error}")
        return handled

    def shutdown(self) -> None:
        if not self.agent:
            return
        try:
            self.db.request("agents", "PATCH", [("id", f"eq.{self.agent['id']}")], {
                "active": False,
                "last_seen_at": utc_now(),
            }, "return=minimal")
        except Exception:
            pass

    def run(self) -> None:
        self.setup()
        log(f"Connected as {self.session.user.get('email') or 'KitKat user'}")
        log(f"PC registered as {self.agent.get('name')}")
        if self.allowed_groups is not None:
            group_summary = ", ".join(sorted(self.allowed_groups)) or "none assigned"
            log(f"Allowed profile groups: {group_summary}")
        try:
            count = self.sync_profiles()
            log(f"Incogniton connected — {count} profiles synced")
        except Exception as error:
            log(f"Incogniton is not ready: {error}")
            log("Open Incogniton and enable its local API; the bridge will keep retrying.")

        last_error = ""
        while True:
            try:
                now = time.monotonic()
                if now - self.last_heartbeat >= HEARTBEAT_SECONDS:
                    self.heartbeat()
                if now - self.last_sync >= PROFILE_SYNC_SECONDS:
                    count = self.sync_profiles()
                    log(f"Profile sync complete — {count} profiles")
                self.process_commands()
                last_error = ""
            except KeyboardInterrupt:
                raise
            except Exception as error:
                message = str(error)
                if message != last_error:
                    log(f"Bridge waiting: {message}")
                    last_error = message
            time.sleep(POLL_SECONDS)


def main() -> int:
    print("KitKat Bridge")
    print("KitKat cloud ↔ this PC ↔ Incogniton")
    print()
    bridge = KitKatBridge()
    try:
        bridge.run()
    except KeyboardInterrupt:
        log("Stopping KitKat Bridge")
        bridge.shutdown()
        return 0
    except Exception as error:
        log(f"Bridge could not start: {error}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
