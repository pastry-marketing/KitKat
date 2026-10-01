import os

def find_incogniton_path():
    """Attempts to find the Incogniton executable on Windows."""
    
    # Common installation paths for Incogniton
    appdata_local = os.environ.get('LOCALAPPDATA', '')
    
    possible_paths = [
        os.path.join(appdata_local, 'Programs', 'Incogniton', 'Incogniton.exe'),
        os.path.join(appdata_local, 'Incogniton', 'Incogniton.exe'),
        r"C:\Program Files\Incogniton\Incogniton.exe",
        r"C:\Program Files (x86)\Incogniton\Incogniton.exe"
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            return path

    # If not found in standard paths, return None
    return None


def find_adspower_path():
    """Attempts to find the AdsPower executable on Windows."""

    appdata_local = os.environ.get('LOCALAPPDATA', '')
    appdata_roaming = os.environ.get('APPDATA', '')

    possible_paths = [
        os.path.join(appdata_local, 'Programs', 'adspower_global', 'AdsPower Global.exe'),
        os.path.join(appdata_local, 'Programs', 'AdsPower Global', 'AdsPower Global.exe'),
        os.path.join(appdata_local, 'Programs', 'adspower', 'AdsPower.exe'),
        os.path.join(appdata_roaming, 'AdsPower Global', 'AdsPower Global.exe'),
        r"C:\Program Files\AdsPower Global\AdsPower Global.exe",
        r"C:\Program Files (x86)\AdsPower Global\AdsPower Global.exe",
        r"C:\Program Files\AdsPower\AdsPower.exe",
        r"C:\Program Files (x86)\AdsPower\AdsPower.exe",
    ]

    for path in possible_paths:
        if os.path.exists(path):
            return path

    # If not found in standard paths, return None
    return None
