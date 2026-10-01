import threading
import subprocess
import psutil
import os
import time
import requests

_launch_lock = threading.Lock()
from core.config import get_setting, set_setting
from core.utils.path_finder import find_incogniton_path

INCOGNITON_API = "http://127.0.0.1:35000"

from core.engine.retry_manager import RetryManager
from core.engine.exceptions import RetryableError, PermanentError

_api_retry = RetryManager(max_attempts=3, backoff_seconds=2.0)

def _api_request(method, endpoint, timeout=15, **kwargs):
    import requests
    url = f"{INCOGNITON_API}{endpoint}"
    
    def _do_req():
        try:
            if method.lower() == "get":
                resp = requests.get(url, timeout=timeout, **kwargs)
            else:
                resp = requests.post(url, timeout=timeout, **kwargs)
                
            if resp.status_code in [429, 500, 502, 503, 504]:
                raise RetryableError(f"Incogniton API {resp.status_code}")
                
            return resp
        except requests.exceptions.RequestException as e:
            raise RetryableError(f"Incogniton Connection Error: {str(e)}")
            
    return _api_retry.execute_with_retry(_do_req)


def is_incogniton_running():
    """Checks if Incogniton is already running."""
    for proc in psutil.process_iter(['name']):
        try:
            if proc.info['name'] and 'incogniton' in proc.info['name'].lower():
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return False

def is_incogniton_api_ready():
    """Checks if the Incogniton local REST API is responding."""
    try:
        resp = _api_request("get", "/profile/all")
        return resp.status_code == 200
    except Exception:
        return False

def wait_for_incogniton_ready(timeout=60, logger_callback=print):
    """
    Waits for Incogniton process and its API to become responsive.
    Polls every 2-3 seconds up to timeout (default 60 seconds).
    Returns (True, message) when ready, (False, message) if timed out.
    """
    start_time = time.time()
    logger_callback(f"Waiting for Incogniton API to initialize (up to {timeout}s)...")
    
    last_log_time = 0
    while time.time() - start_time < timeout:
        elapsed = int(time.time() - start_time)
        if is_incogniton_api_ready():
            logger_callback(f"Incogniton is ready! (Initialized in {elapsed}s)")
            return True, "Incogniton is ready."
            
        time.sleep(2)
        if elapsed > 0 and elapsed - last_log_time >= 10:
            last_log_time = elapsed
            logger_callback(f"Still waiting for Incogniton to load... ({elapsed}s/{timeout}s)")
            
    return False, f"Incogniton did not become ready within {timeout} seconds."

def get_incogniton_exe():
    """Gets the path to the Incogniton executable, trying config first, then auto-discovery."""
    saved_path = get_setting("incogniton_path")
    if saved_path and os.path.exists(saved_path):
        return saved_path
    
    discovered_path = find_incogniton_path()
    if discovered_path:
        set_setting("incogniton_path", discovered_path)
        return discovered_path
        
    return None

def launch_incogniton():
    """Launches Incogniton if it's not already running."""
    if is_incogniton_running():
        return True, "Incogniton is already running."
        
    exe_path = get_incogniton_exe()
    if not exe_path:
        return False, "Incogniton executable not found. Please set it in Settings."
        
    try:
        # Use Popen to start it detached from our script
        subprocess.Popen([exe_path])
        return True, "Incogniton launched successfully."
    except Exception as e:
        return False, f"Failed to launch: {str(e)}"

def resolve_profile_id(identifier, duplicate_resolver=None, master=None):
    """Resolves a profile name to its browser_id (UUID). Returns the original identifier if already a UUID."""
    profile_id = str(identifier).strip()
    # If it looks like a UUID (has dashes and length 32-36), use it directly
    if len(profile_id) >= 32 and "-" in profile_id:
        return profile_id
        
    try:
        resp = _api_request("get", "/profile/all")
        if resp.status_code == 200:
            profiles = resp.json().get("profileData", [])
            matches = []
            for p in profiles:
                info = p.get("general_profile_information", {})
                if info.get("profile_name") == profile_id:
                    # Also grab the group name for the UI
                    group_name = p.get("group", "Unassigned")
                    matches.append({"browser_id": info.get("browser_id"), "group": group_name})
            
            if len(matches) == 1:
                return matches[0]["browser_id"]
            elif len(matches) > 1:
                if duplicate_resolver and master:
                    print(f"[Warning] Multiple profiles found for '{profile_id}'. Prompting user...")
                    selected_id = duplicate_resolver(master, profile_id, matches)
                    if selected_id:
                        return selected_id
                    else:
                        print(f"User canceled duplicate resolution for '{profile_id}'.")
                        return None
                else:
                    print(f"[Warning] Multiple Incogniton profiles found with name '{profile_id}'. Please use the specific Profile ID in Google Sheets instead.")
                    return None
                
        return None
    except Exception:
        return None

def start_profile(identifier, duplicate_resolver=None, master=None, max_retries=3):
    """
    Starts an Incogniton profile for automation and returns the debugging WebSocket URL.
    Uses: /automation/launch/puppeteer/{profile_id}
    identifier can be a UUID or the profile name.
    """
    profile_id = resolve_profile_id(identifier, duplicate_resolver, master)
    if not profile_id:
        return False, f"Could not find profile with name/id: {identifier}"

    with _launch_lock:
        for attempt in range(max_retries):
            try:
                url = f"{INCOGNITON_API}/automation/launch/puppeteer/{profile_id}"
                response = _api_request("get", f"/automation/launch/puppeteer/{profile_id}", timeout=120)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("status") == "ok":
                        return True, data
                    else:
                        err_msg = data.get("message", "")
                        if "out of sync" in err_msg.lower():
                            if attempt < max_retries - 1:
                                print(f"[Warning] Profile is out of sync. Waiting 5s before retry {attempt+1}/{max_retries}...")
                                time.sleep(5)
                                continue
                        return False, f"Incogniton returned error: {data}"
                else:
                    return False, f"Failed to start profile. Status: {response.status_code}"
            except Exception as e:
                return False, str(e)
                
        return False, "Failed to start profile after retries (Profile is out of sync or locked)."

def stop_profile(identifier):
    """
    Stops an Incogniton profile.
    Uses: /profile/stop/{profile_id}
    """
    profile_id = resolve_profile_id(identifier)
    if not profile_id:
        return False
        
    try:
        url = f"{INCOGNITON_API}/profile/stop/{profile_id}"
        response = _api_request("get", f"/profile/stop/{profile_id}", timeout=30)
        return response.status_code == 200
    except:
        return False

def update_profile_proxy(profile_id, proxy_str):
    """
    Updates the proxy of an existing Incogniton profile before launching.
    """
    if not proxy_str or str(proxy_str).strip() == "" or str(proxy_str).lower() == "n/a":
        return False, "No valid proxy provided"
        
    # We must import parse_proxy here to avoid circular imports if any
    from core.automation.profile_builder import parse_proxy
    proxy_info = parse_proxy(proxy_str)
    if not proxy_info:
        return False, "Invalid proxy format (expected host:port:user:pass)"
        
    try:
        # Fetch current profile configurations
        resp = _api_request("get", "/profile/all")
        if resp.status_code != 200:
            return False, f"Failed to fetch profiles for update: HTTP {resp.status_code}"
            
        profiles = resp.json().get("profileData", [])
        profile_data = None
        actual_browser_id = profile_id
        
        for p in profiles:
            info = p.get("general_profile_information", {})
            if str(info.get("browser_id")) == str(profile_id) or str(info.get("profile_name")).strip().lower() == str(profile_id).strip().lower():
                profile_data = p
                actual_browser_id = info.get("browser_id", profile_id)
                break
                
        if not profile_data:
            return False, f"Profile not found for update: {profile_id}"
            
        # Check if existing proxy already matches
        existing_proxy = profile_data.get("Proxy", {})
        if isinstance(existing_proxy, dict):
            existing_url = str(existing_proxy.get("proxy_url", "")).strip()
            existing_user = str(existing_proxy.get("proxy_username", "")).strip()
            existing_pass = str(existing_proxy.get("proxy_password", "")).strip()
            
            target_url = f"{proxy_info['host']}:{proxy_info['port']}".strip()
            target_user = str(proxy_info.get("username") or "").strip()
            target_pass = str(proxy_info.get("password") or "").strip()
            
            if (existing_url == target_url and 
                existing_user == target_user and 
                existing_pass == target_pass and 
                str(existing_proxy.get("connection_type", "")).upper() in ["SOCKS5", "HTTP"]):
                return True, "Proxy is already up to date"

        # Build a 100% CLEAN proxy dictionary containing ONLY primitive strings
        # This completely prevents Java LinkedHashMap casting errors on Incogniton's backend
        clean_proxy = {
            "connection_type": str(proxy_info.get("type", "SOCKS5")),
            "proxy_url": f"{proxy_info['host']}:{proxy_info['port']}",
            "proxy_username": str(proxy_info.get("username") or ""),
            "proxy_password": str(proxy_info.get("password") or "")
        }
        
        profile_name = profile_data.get("general_profile_information", {}).get("profile_name", "")
        
        # Try payload formats in order
        payloads_to_try = [
            {
                "profileData": {
                    "profile_browser_id": str(actual_browser_id),
                    "Proxy": clean_proxy
                }
            },
            {
                "profile_id": str(actual_browser_id),
                "profileData": {
                    "profile_browser_id": str(actual_browser_id),
                    "general_profile_information": {
                        "profile_name": profile_name,
                        "browser_id": str(actual_browser_id)
                    },
                    "Proxy": clean_proxy
                }
            }
        ]
        
        last_err = "Unknown error"
        for payload in payloads_to_try:
            try:
                update_resp = _api_request("post", "/profile/update", json=payload, timeout=30)
                if update_resp.status_code == 200:
                    resp_json = update_resp.json()
                    if resp_json.get("status") == "ok" or resp_json.get("success") is True:
                        return True, "Proxy updated successfully"
                    else:
                        last_err = resp_json.get("message", "API returned non-ok status")
                else:
                    last_err = f"HTTP {update_resp.status_code}: {update_resp.text}"
            except Exception as ex:
                last_err = str(ex)
                
        return False, f"API Error: {last_err}"
            
    except Exception as e:
        return False, f"Error updating proxy: {str(e)}"


