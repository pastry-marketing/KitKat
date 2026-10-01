import requests
import time
from core.config import get_setting


def _requests_retry(method, url, retries=3, backoff=2, **kwargs):
    import requests
    import time
    for i in range(retries):
        try:
            if method.lower() == "get":
                resp = requests.get(url, **kwargs)
            else:
                resp = requests.post(url, **kwargs)
                
            # Check for retryable HTTP statuses
            if resp.status_code in [429, 500, 502, 503, 504]:
                if i < retries - 1:
                    time.sleep(backoff)
                    continue
                else:
                    return resp # Return it anyway after all retries fail
                    
            return resp
        except requests.exceptions.RequestException as e:
            if i < retries - 1:
                time.sleep(backoff)
            else:
                raise e

def get_script_url():
    return get_setting("apps_script_url", "")

def fetch_pending_profiles():
    """Fetches profiles that have an empty status from Google Sheets."""
    url = get_script_url()
    if not url:
        return False, "Google Apps Script URL is not set in Settings."
        
    try:
        response = _requests_retry("get", f"{url}?action=getPendingProfiles", timeout=10)
        data = response.json()
        
        if data.get("success"):
            return True, data.get("data", [])
        else:
            return False, data.get("error", "Unknown error from Google Apps Script.")
    except Exception as e:
        return False, f"Failed to connect to Google Sheets: {str(e)}"

def update_profile_status(row_number, status, notes="", sheet_name="Incog Profile Creation"):
    """Updates the status and notes of a specific row in Google Sheets."""
    url = get_script_url()
    if not url:
        return False, "Google Apps Script URL is not set in Settings."
        
    payload = {
        "action": "updateStatus",
        "sheetName": sheet_name,
        "rowNumber": row_number,
        "status": status,
        "notes": notes
    }
    
    try:
        response = _requests_retry("post", url, json=payload, timeout=10)
        data = response.json()
        
        if data.get("success"):
            return True, "Success"
        else:
            return False, data.get("error", "Unknown error from Google Apps Script.")
    except Exception as e:
        return False, f"Failed to update Google Sheets: {str(e)}"

def fetch_pending_nd_accounts():
    url = get_script_url()
    if not url:
        return False, "Google Apps Script URL is not set."
        
    try:
        response = _requests_retry("get", url, params={"action": "getPendingNDAccounts"}, timeout=15)
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                return True, data.get("data", [])
            else:
                return False, data.get("error", "Unknown error")
        else:
            return False, f"HTTP Error: {response.status_code}"
    except Exception as e:
        return False, str(e)

def update_nd_account_status(row_number, status, notes=""):
    url = get_script_url()
    if not url:
        return False, "Google Apps Script URL is not set."
        
    if notes:
        status = f"{status} | {notes}"
        
    payload = {
        "action": "updateNDStatus",
        "rowNumber": row_number,
        "status": status
    }
    
    try:
        response = _requests_retry("post", url, json=payload, timeout=15)
        if response.status_code == 200:
            return True, "Status updated"
        else:
            return False, f"Failed with status: {response.status_code}"
    except Exception as e:
        return False, str(e)

def fetch_pending_rows(sheet_name):
    url = get_script_url()
    if not url:
        return False, "Google Apps Script URL is not set."
        
    try:
        response = _requests_retry("get", url, params={"action": "getPendingRows", "sheetName": sheet_name}, timeout=15)
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                return True, data.get("data", [])
            else:
                return False, data.get("error", "Unknown error")
        else:
            return False, f"HTTP Error: {response.status_code}"
    except Exception as e:
        return False, str(e)

def update_row_status(sheet_name, row_number, status, notes=""):
    url = get_script_url()
    if not url:
        return False, "Google Apps Script URL is not set."
        
    if notes:
        status = f"{status} | {notes}"
        
    payload = {
        "action": "updateRowStatus",
        "sheetName": sheet_name,
        "rowNumber": row_number,
        "status": status
    }
    
    try:
        response = _requests_retry("post", url, json=payload, timeout=15)
        if response.status_code == 200:
            return True, "Status updated"
        else:
            return False, f"Failed with status: {response.status_code}"
    except Exception as e:
        return False, str(e)

def update_column_value(sheet_name, row_number, column_name, value):
    url = get_script_url()
    if not url:
        return False, "Google Apps Script URL is not set."
        
    payload = {
        "action": "updateColumnValue",
        "sheetName": sheet_name,
        "rowNumber": row_number,
        "columnName": column_name,
        "value": value
    }
    
    try:
        response = _requests_retry("post", url, json=payload, timeout=15)
        if response.status_code == 200:
            return True, "Column updated"
        else:
            return False, f"Failed with status: {response.status_code}"
    except Exception as e:
        return False, str(e)

def claim_row(sheet_name, row_number):
    """
    Atomically claims a row for processing to prevent duplicates.
    Returns (True, "Claimed") if successful.
    Returns (False, "Already claimed") if someone else got it first.
    """
    url = get_script_url()
    if not url:
        return False, "Google Apps Script URL is not set."
        
    payload = {
        "action": "claimRow",
        "sheetName": sheet_name,
        "rowNumber": row_number
    }
    
    try:
        response = _requests_retry("post", url, json=payload, timeout=15)
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                # Handle both {"success": true, "claimed": true} and just {"success": true}
                if data.get("claimed") is True or "claimed" not in data:
                    return True, "Claimed"
                else:
                    return False, f"Already claimed (Status: {data.get('currentStatus')})"
            else:
                return False, data.get("error", "Unknown error from Google Apps Script.")
        else:
            return False, f"HTTP Error: {response.status_code}"
    except Exception as e:
        return False, f"Failed to connect to Google Sheets: {str(e)}"
