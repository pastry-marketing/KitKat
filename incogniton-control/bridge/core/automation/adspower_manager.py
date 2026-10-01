import threading
import subprocess
import psutil
import os
import time
import json
import requests

_launch_lock = threading.Lock()
_proxy_cache_lock = threading.Lock()
from core.config import get_setting, set_setting
from core.utils.path_finder import find_adspower_path

# AdsPower's local API always defaults to port 50325 (like Incogniton's fixed
# 35000), so the app uses that automatically and never asks for it. Users who
# changed the port in AdsPower -> Settings -> Local API can override it by
# adding "adspower_api_port" (or a full "adspower_api_base") to config.json;
# it is read each call so a change takes effect without a restart.
DEFAULT_ADSPOWER_PORT = "50325"

from core.engine.retry_manager import RetryManager
from core.engine.exceptions import RetryableError, PermanentError

_api_retry = RetryManager(max_attempts=3, backoff_seconds=2.0)

# AdsPower's local API is rate limited to roughly 1 request per second. When
# several profile workers run concurrently they would otherwise hammer it and
# get "Too many request per second" errors, so every request goes through this
# global throttle.
_rate_lock = threading.Lock()
_last_request_time = [0.0]
_MIN_REQUEST_INTERVAL = 1.2


def get_adspower_base():
    """Returns the base URL of the AdsPower local API from settings."""
    base = get_setting("adspower_api_base")
    if base:
        return str(base).rstrip("/")
    port = get_setting("adspower_api_port", DEFAULT_ADSPOWER_PORT) or DEFAULT_ADSPOWER_PORT
    return f"http://local.adspower.net:{port}"


# Kept for parity with incogniton_manager (which exposes INCOGNITON_API).
ADSPOWER_API = get_adspower_base()


def _throttle():
    """Blocks until at least _MIN_REQUEST_INTERVAL has passed since the last call."""
    with _rate_lock:
        elapsed = time.time() - _last_request_time[0]
        if elapsed < _MIN_REQUEST_INTERVAL:
            time.sleep(_MIN_REQUEST_INTERVAL - elapsed)
        _last_request_time[0] = time.time()


def get_adspower_api_key():
    """Returns the AdsPower Local API key from settings (empty string if unset)."""
    return str(get_setting("adspower_api_key", "") or "").strip()


def _api_request(method, endpoint, timeout=15, **kwargs):
    """Performs a rate-limited, retrying request against the AdsPower local API."""
    url = f"{get_adspower_base()}{endpoint}"

    # Newer AdsPower versions (and headless/CLI mode) require the Local API key
    # on every request, sent as an "Authorization: Bearer <key>" header.
    headers = dict(kwargs.pop("headers", {}) or {})
    api_key = get_adspower_api_key()
    if api_key:
        headers.setdefault("Authorization", f"Bearer {api_key}")

    def _do_req():
        _throttle()
        try:
            if method.lower() == "get":
                resp = requests.get(url, timeout=timeout, headers=headers, **kwargs)
            else:
                resp = requests.post(url, timeout=timeout, headers=headers, **kwargs)

            if resp.status_code in [429, 500, 502, 503, 504]:
                raise RetryableError(f"AdsPower API {resp.status_code}")

            # AdsPower returns HTTP 200 with a JSON body whose "code" is 0 on
            # success. A busy API returns a non-zero code with a message like
            # "Too many request per second." which we should retry.
            try:
                data = resp.json()
                msg = str(data.get("msg", "")).lower()
                if data.get("code") not in (0, None) and "too many request" in msg:
                    raise RetryableError(f"AdsPower busy: {data.get('msg')}")
            except ValueError:
                pass

            return resp
        except requests.exceptions.RequestException as e:
            raise RetryableError(f"AdsPower Connection Error: {str(e)}")

    return _api_retry.execute_with_retry(_do_req)


def is_adspower_running():
    """Checks if the AdsPower desktop app is already running."""
    for proc in psutil.process_iter(['name']):
        try:
            name = proc.info['name']
            if name and 'adspower' in name.lower():
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return False


def is_adspower_api_ready():
    """Checks if the AdsPower local REST API is responding."""
    try:
        resp = _api_request("get", "/status")
        if resp.status_code != 200:
            return False
        return resp.json().get("code") == 0
    except Exception:
        return False


def wait_for_adspower_ready(timeout=60, logger_callback=print):
    """
    Waits for the AdsPower process and its local API to become responsive.
    Polls every 2 seconds up to timeout (default 60 seconds).
    Returns (True, message) when ready, (False, message) if timed out.
    """
    start_time = time.time()
    logger_callback(f"Waiting for AdsPower API to initialize (up to {timeout}s)...")

    last_log_time = 0
    while time.time() - start_time < timeout:
        elapsed = int(time.time() - start_time)
        if is_adspower_api_ready():
            logger_callback(f"AdsPower is ready! (Initialized in {elapsed}s)")
            return True, "AdsPower is ready."

        time.sleep(2)
        if elapsed > 0 and elapsed - last_log_time >= 10:
            last_log_time = elapsed
            logger_callback(f"Still waiting for AdsPower to load... ({elapsed}s/{timeout}s)")

    return False, f"AdsPower did not become ready within {timeout} seconds."


def get_adspower_exe():
    """Gets the path to the AdsPower executable, trying config first, then auto-discovery."""
    saved_path = get_setting("adspower_path")
    if saved_path and os.path.exists(saved_path):
        return saved_path

    discovered_path = find_adspower_path()
    if discovered_path:
        set_setting("adspower_path", discovered_path)
        return discovered_path

    return None


def launch_adspower():
    """Launches the AdsPower desktop app if it's not already running."""
    if is_adspower_running():
        return True, "AdsPower is already running."

    exe_path = get_adspower_exe()
    if not exe_path:
        return False, "AdsPower executable not found. Please set it in Settings."

    try:
        subprocess.Popen([exe_path])
        return True, "AdsPower launched successfully."
    except Exception as e:
        return False, f"Failed to launch: {str(e)}"


def _iter_all_profiles():
    """Yields every profile dict from the (paginated) AdsPower user list."""
    page = 1
    page_size = 100
    while True:
        resp = _api_request(
            "get", "/api/v1/user/list",
            params={"page": page, "page_size": page_size},
            timeout=30,
        )
        if resp.status_code != 200:
            break
        payload = resp.json()
        if payload.get("code") != 0:
            break
        data = payload.get("data", {}) or {}
        rows = data.get("list", []) or []
        for row in rows:
            yield row
        if len(rows) < page_size:
            break
        page += 1


def resolve_profile_id(identifier, duplicate_resolver=None, master=None):
    """
    Resolves a profile name to its AdsPower user_id.
    Returns the original identifier if it already matches a known user_id.
    """
    profile_id = str(identifier).strip()
    if not profile_id:
        return None

    try:
        matches = []
        for p in _iter_all_profiles():
            user_id = str(p.get("user_id", "")).strip()
            name = str(p.get("name", "")).strip()
            group_name = p.get("group_name") or p.get("group_id") or "Unassigned"

            # Exact user_id match -> use it directly.
            if user_id and user_id == profile_id:
                return user_id

            if name and name == profile_id:
                matches.append({"browser_id": user_id, "group": group_name})

        if len(matches) == 1:
            return matches[0]["browser_id"]
        elif len(matches) > 1:
            if duplicate_resolver and master:
                print(f"[Warning] Multiple AdsPower profiles found for '{profile_id}'. Prompting user...")
                selected_id = duplicate_resolver(master, profile_id, matches)
                if selected_id:
                    return selected_id
                print(f"User canceled duplicate resolution for '{profile_id}'.")
                return None
            print(f"[Warning] Multiple AdsPower profiles found with name '{profile_id}'. Please use the specific Profile ID in Google Sheets instead.")
            return None

        return None
    except Exception:
        return None


def start_profile(identifier, duplicate_resolver=None, master=None, max_retries=3):
    """
    Starts an AdsPower profile for automation and returns the debugging WebSocket URL.
    Uses: /api/v1/browser/start?user_id={user_id}
    identifier can be an AdsPower user_id or the profile name.

    The returned data dict is normalised so it exposes a "url" (CDP puppeteer
    WebSocket) and "port" key, matching what the profile worker already expects
    from Incogniton.
    """
    profile_id = resolve_profile_id(identifier, duplicate_resolver, master)
    if not profile_id:
        return False, f"Could not find profile with name/id: {identifier}"

    with _launch_lock:
        for attempt in range(max_retries):
            try:
                response = _api_request(
                    "get", "/api/v1/browser/start",
                    params={"user_id": profile_id, "open_tabs": 1},
                    timeout=120,
                )
                if response.status_code == 200:
                    payload = response.json()
                    if payload.get("code") == 0:
                        data = payload.get("data", {}) or {}
                        ws = data.get("ws", {}) or {}
                        puppeteer_url = ws.get("puppeteer", "")
                        debug_port = data.get("debug_port", "")

                        normalized = {
                            "url": puppeteer_url,
                            "webSocketDebuggerUrl": puppeteer_url,
                            "port": debug_port,
                            "raw": data,
                        }
                        return True, normalized
                    else:
                        err_msg = str(payload.get("msg", ""))
                        if "too many request" in err_msg.lower():
                            if attempt < max_retries - 1:
                                print(f"[Warning] AdsPower busy. Retrying {attempt+1}/{max_retries}...")
                                time.sleep(2)
                                continue
                        return False, f"AdsPower returned error: {payload}"
                else:
                    return False, f"Failed to start profile. Status: {response.status_code}"
            except Exception as e:
                return False, str(e)

        return False, "Failed to start profile after retries."


def stop_profile(identifier):
    """
    Stops an AdsPower profile.
    Uses: /api/v1/browser/stop?user_id={user_id}
    """
    profile_id = resolve_profile_id(identifier)
    if not profile_id:
        return False

    try:
        response = _api_request(
            "get", "/api/v1/browser/stop",
            params={"user_id": profile_id},
            timeout=30,
        )
        if response.status_code != 200:
            return False
        return response.json().get("code") == 0
    except Exception:
        return False


def _build_proxy_config(proxy_str):
    """Builds an AdsPower user_proxy_config dict from a host:port:user:pass string."""
    if not proxy_str or str(proxy_str).strip() == "" or str(proxy_str).lower() == "n/a":
        return None

    from core.automation.profile_builder import parse_proxy
    proxy_info = parse_proxy(proxy_str)
    if not proxy_info:
        return None

    return {
        "proxy_soft": "other",
        "proxy_type": str(proxy_info.get("type", "socks5")).lower(),
        "proxy_host": proxy_info["host"],
        "proxy_port": str(proxy_info["port"]),
        "proxy_user": str(proxy_info.get("username") or ""),
        "proxy_password": str(proxy_info.get("password") or ""),
    }


# AdsPower's API does not expose a profile's stored proxy credentials (the
# user list only returns the exit IP), so we cannot live-compare the way
# Incogniton does. Instead we remember the last proxy we successfully set for
# each profile in a small local cache file and skip the update call when the
# incoming proxy is identical - the same "skip if unchanged" outcome.
_PROXY_CACHE_FILE = "adspower_proxy_cache.json"


def _proxy_signature(proxy_config):
    """A stable string identifying a proxy config, for change detection."""
    return "|".join([
        str(proxy_config.get("proxy_type", "")),
        str(proxy_config.get("proxy_host", "")),
        str(proxy_config.get("proxy_port", "")),
        str(proxy_config.get("proxy_user", "")),
        str(proxy_config.get("proxy_password", "")),
    ])


def _load_proxy_cache():
    try:
        with open(_PROXY_CACHE_FILE, "r") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _proxy_cache_get(user_id):
    with _proxy_cache_lock:
        return _load_proxy_cache().get(str(user_id))


def _proxy_cache_set(user_id, signature):
    with _proxy_cache_lock:
        cache = _load_proxy_cache()
        cache[str(user_id)] = signature
        try:
            with open(_PROXY_CACHE_FILE, "w") as f:
                json.dump(cache, f)
        except Exception:
            pass


def update_profile_proxy(profile_id, proxy_str):
    """
    Updates the proxy of an existing AdsPower profile before launching.
    Uses: POST /api/v1/user/update

    Skips the API call when the profile already has the same proxy we last set
    (tracked in a local cache), mirroring Incogniton's "already up to date" fast
    path.
    """
    proxy_config = _build_proxy_config(proxy_str)
    if not proxy_config:
        if not proxy_str or str(proxy_str).strip() == "" or str(proxy_str).lower() == "n/a":
            return False, "No valid proxy provided"
        return False, "Invalid proxy format (expected host:port:user:pass)"

    try:
        user_id = resolve_profile_id(profile_id)
        if not user_id:
            return False, f"Profile not found for update: {profile_id}"

        # Skip if this exact proxy was already applied to this profile.
        signature = _proxy_signature(proxy_config)
        if _proxy_cache_get(user_id) == signature:
            return True, "Proxy is already up to date"

        payload = {
            "user_id": user_id,
            "user_proxy_config": proxy_config,
        }
        resp = _api_request("post", "/api/v1/user/update", json=payload, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == 0:
                _proxy_cache_set(user_id, signature)
                return True, "Proxy updated successfully"
            return False, data.get("msg", "API returned non-ok status")
        return False, f"HTTP {resp.status_code}: {resp.text}"
    except Exception as e:
        return False, f"Error updating proxy: {str(e)}"


def _resolve_group_id(group_name):
    """Resolves an AdsPower group name to its group_id, creating it if missing. Defaults to '0'."""
    if not group_name:
        return "0"

    target = str(group_name).strip()
    if not target:
        return "0"

    try:
        page = 1
        page_size = 100
        while True:
            resp = _api_request(
                "get", "/api/v1/group/list",
                params={"page": page, "page_size": page_size},
                timeout=30,
            )
            if resp.status_code != 200:
                break
            payload = resp.json()
            if payload.get("code") != 0:
                break
            data = payload.get("data", {}) or {}
            rows = data.get("list", []) or []
            for row in rows:
                if str(row.get("group_name", "")).strip().lower() == target.lower():
                    return str(row.get("group_id", "0"))
            if len(rows) < page_size:
                break
            page += 1

        # Not found -> create it.
        create_resp = _api_request(
            "post", "/api/v1/group/create",
            json={"group_name": target},
            timeout=30,
        )
        if create_resp.status_code == 200:
            cdata = create_resp.json()
            if cdata.get("code") == 0:
                return str((cdata.get("data", {}) or {}).get("group_id", "0"))
    except Exception:
        pass

    return "0"


def get_adspower_os():
    """Returns the OS to create AdsPower profiles as: 'android' or 'windows'."""
    value = str(get_setting("adspower_os", "android") or "android").strip().lower()
    return "windows" if value == "windows" else "android"


def _build_ua_config():
    """
    Builds the random_ua + screen_resolution fingerprint fields for the OS
    chosen in Settings.

    random_ua fixes the profile's operating system (it overrides any custom UA
    and is only supported by the create endpoint, which is what we use):
      - "android" -> Android Chrome, mobile portrait resolution
      - "windows" -> Windows Chrome, desktop resolution
    """
    if get_adspower_os() == "windows":
        return {
            "random_ua": {
                "ua_browser": ["chrome"],
                "ua_system_version": ["Windows 10", "Windows 11"],
            },
            "screen_resolution": "random",
        }
    return {
        "random_ua": {
            "ua_browser": ["chrome"],
            "ua_system_version": [
                "Android 9", "Android 10", "Android 11", "Android 12", "Android 13",
            ],
        },
        "screen_resolution": "1080_1920",
    }


def _build_geolocation_config(profile_data):
    """
    Builds AdsPower geolocation fingerprint fields from the sheet's geo column.

    Uses the same 'lat,long' format Incogniton reads. Returns {} when no geo is
    provided so AdsPower keeps its default (IP-based) behaviour, mirroring how
    Incogniton only sets a Geolocation block when the sheet has coordinates.
    """
    from core.automation.profile_builder import get_val

    geo_str = get_val(profile_data, "geo", "geolocation", "lat/long", "latlong")
    if not geo_str or "," not in geo_str:
        return {}

    try:
        lat_str, lon_str = geo_str.split(",", 1)
        latitude = float(lat_str.strip())
        longitude = float(lon_str.strip())
    except (ValueError, TypeError):
        return {}

    # AdsPower requires latitude in [-90, 90] and longitude in [-180, 180],
    # each with at most 6 decimal places. Incogniton accepted long, high
    # precision values (e.g. 15 decimals); round to 6 dp so AdsPower accepts
    # the same coordinates instead of erroring with "longitude incorrect format".
    if not (-90.0 <= latitude <= 90.0) or not (-180.0 <= longitude <= 180.0):
        return {}
    latitude = f"{latitude:.6f}"
    longitude = f"{longitude:.6f}"

    # AdsPower requires accuracy to be an integer between 10 and 5000 metres.
    # Incogniton defaults to 50 when the sheet omits it, so match that.
    acc = get_val(profile_data, "accuracy", "acc")
    try:
        accuracy = int(float(str(acc).strip())) if acc else 50
    except (ValueError, TypeError):
        accuracy = 50
    accuracy = max(10, min(5000, accuracy))

    return {
        "location": "allow",       # let sites read the location without prompting
        "location_switch": "0",    # 0 = use the custom coordinates below, not IP
        "longitude": longitude,
        "latitude": latitude,
        "accuracy": str(accuracy),
    }


def create_adspower_profile(profile_data):
    """
    Creates a profile in AdsPower via the local API.
    Uses: POST /api/v1/user/create
    Returns (success: bool, message: str, profile_id: str) to match the
    Incogniton profile creator's signature.
    """
    from core.automation.profile_builder import get_val

    profile_name = get_val(profile_data, "name", "profile name")
    if not profile_name:
        profile_name = f"Profile_{profile_data.get('rowNumber', 'New')}"

    group_name = get_val(profile_data, "group", "profile group", "group name")
    group_id = _resolve_group_id(group_name)

    # A minimal fingerprint config; AdsPower randomises the rest. The OS
    # (random_ua + screen_resolution) is chosen from Settings, and custom
    # geolocation (from the sheet) is merged in when provided.
    fingerprint_config = {
        "automatic_timezone": "1",
        "language": ["en-US", "en"],
    }
    fingerprint_config.update(_build_ua_config())
    fingerprint_config.update(_build_geolocation_config(profile_data))

    payload = {
        "name": profile_name,
        "group_id": group_id,
        "fingerprint_config": fingerprint_config,
    }

    proxy_str = get_val(profile_data, "proxy", "proxy string")
    proxy_config = _build_proxy_config(proxy_str)
    if proxy_config:
        payload["user_proxy_config"] = proxy_config
    else:
        payload["user_proxy_config"] = {"proxy_soft": "no_proxy"}

    try:
        response = _api_request("post", "/api/v1/user/create", json=payload, timeout=45)
        if response.status_code == 200:
            data = response.json()
            if data.get("code") == 0:
                profile_id = str((data.get("data", {}) or {}).get("id", "")) or "N/A"
                return True, "Created Successfully", profile_id
            return False, data.get("msg", "Unknown error from API"), ""
        return False, f"API Error: {response.status_code}", ""
    except requests.exceptions.ConnectionError:
        return False, "Failed to connect to AdsPower. Is it running?", ""
    except Exception as e:
        return False, f"Error: {str(e)}", ""
