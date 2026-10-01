import requests
import time
import urllib.parse
from core.automation.incogniton_manager import INCOGNITON_API


def parse_proxy(proxy_string):
    """Parses proxy in format: host:port:username:password"""
    if not proxy_string or str(proxy_string).strip() == "":
        return None

    parts = str(proxy_string).strip().split(":")
    if len(parts) >= 2:
        proxy_data = {
            "type": "SOCKS5",
            "host": parts[0],
            "port": parts[1],
            "username": parts[2] if len(parts) >= 3 else "",
            "password": parts[3] if len(parts) >= 4 else "",
        }
        return proxy_data
    return None


def get_val(data_dict, *keys):
    """Returns the first non-empty value found for the given case-insensitive keys."""
    lower_data = {str(k).lower().strip(): v for k, v in data_dict.items()}

    # 1. Exact match
    for k in keys:
        k_lower = k.lower().strip()
        if k_lower in lower_data and str(lower_data[k_lower]).strip():
            return str(lower_data[k_lower]).strip()

    # 2. Partial match (e.g., 'geo' in 'geo(lat/long)')
    for data_key, val in lower_data.items():
        if str(val).strip():
            for k in keys:
                k_lower = k.lower().strip()
                if k_lower in data_key:
                    return str(val).strip()
    return ""


def create_incogniton_profile(profile_data):
    """
    Sends a request to Incogniton local API to create a profile.
    Uses the flat CSV header mapping which Incogniton accepts as the payload structure.
    """
    url = f"{INCOGNITON_API}/profile/add"

    # Base payload
    group_name = get_val(profile_data, "group", "profile group", "group name")

    if group_name:
        import difflib

        valid_groups = [
            "Austin",
            "Bronx",
            "Brooklyn",
            "Chicago",
            "Downtown (LA Area)",
            "Houston",
            "Las Vegas",
            "Manhatten",
            "Georgia",
            "Miami",
            "New Jersey",
            "Orange County",
            "Queens, New York",
            "san diego",
            "san jose",
            "Santa Clarita",
            "Staten Island",
            "The Valley (LA Area)",
            "Push Hard Accounts",
            "Indianapolis, Indiana",
            "Palm Springs, CA",
            "Dallas",
            "San Francisco, California",
            "Florida",
            "California",
            "Texas",
            "Listings 2.0",
            "Dylan",
        ]

        # 1. Exact/case-insensitive match
        lower_map = {g.lower(): g for g in valid_groups}
        g_lower = str(group_name).strip().lower()

        if g_lower in lower_map:
            group_name = lower_map[g_lower]
        else:
            # 2. Substring match (handles "valley" matching "The Valley (LA Area)")
            matched = False
            for valid_lower, valid_original in lower_map.items():
                if g_lower in valid_lower:
                    group_name = valid_original
                    matched = True
                    break

            # 3. Fuzzy match for typos (handles 'Manhatan' -> 'Manhatten')
            if not matched:
                matches = difflib.get_close_matches(
                    g_lower, list(lower_map.keys()), n=1, cutoff=0.5
                )
                if matches:
                    group_name = lower_map[matches[0]]

    if not group_name:
        group_name = "Unassigned"

    profile_name = get_val(profile_data, "name", "profile name")
    if not profile_name:
        profile_name = f"Profile_{profile_data.get('rowNumber', 'New')}"

    payload = {
        "profileData": {
            "general_profile_information": {
                "profile_name": profile_name,
                "profile_group": group_name,
            },
            "profile_name": profile_name,
            "platform": "windows",
            "browser_version": "120",
        }
    }

    # Handle proxy
    proxy_str = get_val(profile_data, "proxy", "proxy string")
    proxy_info = parse_proxy(proxy_str)
    if proxy_info:
        payload["profileData"]["Proxy"] = {
            "connection_type": "SOCKS5",
            "proxy_url": f"{proxy_info['host']}:{proxy_info['port']}",
        }
        if proxy_info["username"]:
            payload["profileData"]["Proxy"]["proxy_username"] = proxy_info["username"]
        if proxy_info["password"]:
            payload["profileData"]["Proxy"]["proxy_password"] = proxy_info["password"]

    # Add geolocation if provided
    geo_str = get_val(profile_data, "geo", "geolocation", "lat/long", "latlong")
    acc = get_val(profile_data, "accuracy", "acc")

    if geo_str and "," in geo_str:
        try:
            lat_str, lon_str = geo_str.split(",", 1)
            payload["profileData"]["Geolocation"] = {
                "fill_geolocation_based_on_ip": "false",
                "location_information": {
                    "latitude": lat_str.strip(),
                    "longitude": lon_str.strip(),
                    "accuracy": str(acc).strip() if acc else "50",
                },
            }
        except ValueError:
            pass

    # Incogniton expects this to be json
    try:
        response = requests.post(url, json=payload, timeout=45)

        if response.status_code == 200:
            data = response.json()

            # Extract ID robustly
            profile_id = data.get("profile_id") or data.get("id")
            if not profile_id and "data" in data and isinstance(data["data"], dict):
                profile_id = data["data"].get("id", "")

            # If we still can't find it, just skip it as requested by user
            if not profile_id:
                profile_id = "N/A"

            if (
                data.get("status") == "ok"
                or data.get("success") == True
                or "profileData" in str(data)
            ):
                return True, "Created Successfully", profile_id
            else:
                return False, data.get("message", "Unknown error from API"), profile_id
        else:
            return False, f"API Error: {response.status_code}", ""

    except requests.exceptions.ConnectionError:
        return False, "Failed to connect to Incogniton. Is it running?", ""
    except Exception as e:
        return False, f"Error: {str(e)}", ""
