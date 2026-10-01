"""
Browser provider dispatcher.

This is a thin facade that routes every browser operation to the provider the
user selected in Settings ("browser_provider": "incogniton" | "adspower").

It exposes the exact same function names the rest of the app already imported
from ``incogniton_manager`` (plus generic aliases), so switching a consumer to
this module is a one-line import change - none of the automation, engine,
sheets, retry or Playwright flow logic changes. Each provider module keeps an
identical interface, so the profile worker and the views behave the same way
regardless of which browser is active.
"""

from core.config import get_setting

from core.automation import incogniton_manager as _incogniton
from core.automation import adspower_manager as _adspower

INCOGNITON = "incogniton"
ADSPOWER = "adspower"


def get_provider():
    """Returns the active provider key ('incogniton' or 'adspower')."""
    value = str(get_setting("browser_provider", INCOGNITON) or INCOGNITON).strip().lower()
    return ADSPOWER if value == ADSPOWER else INCOGNITON


def provider_label():
    """Human-readable name of the active provider, for logs and the UI."""
    return "AdsPower" if get_provider() == ADSPOWER else "Incogniton"


def _mgr():
    """Returns the manager module for the active provider."""
    return _adspower if get_provider() == ADSPOWER else _incogniton


# --- Generic, provider-agnostic API ---------------------------------------

def is_running():
    return _mgr().is_adspower_running() if get_provider() == ADSPOWER else _incogniton.is_incogniton_running()


def launch():
    return _mgr().launch_adspower() if get_provider() == ADSPOWER else _incogniton.launch_incogniton()


def wait_for_ready(timeout=60, logger_callback=print):
    if get_provider() == ADSPOWER:
        return _adspower.wait_for_adspower_ready(timeout=timeout, logger_callback=logger_callback)
    return _incogniton.wait_for_incogniton_ready(timeout=timeout, logger_callback=logger_callback)


def start_profile(identifier, duplicate_resolver=None, master=None, max_retries=3):
    return _mgr().start_profile(identifier, duplicate_resolver=duplicate_resolver, master=master, max_retries=max_retries)


def stop_profile(identifier):
    return _mgr().stop_profile(identifier)


def update_profile_proxy(profile_id, proxy_str):
    return _mgr().update_profile_proxy(profile_id, proxy_str)


def resolve_profile_id(identifier, duplicate_resolver=None, master=None):
    return _mgr().resolve_profile_id(identifier, duplicate_resolver=duplicate_resolver, master=master)


def create_profile(profile_data):
    """Creates a profile with the active provider. Returns (ok, message, profile_id)."""
    if get_provider() == ADSPOWER:
        return _adspower.create_adspower_profile(profile_data)
    from core.automation.profile_builder import create_incogniton_profile
    return create_incogniton_profile(profile_data)


# --- Drop-in aliases matching the legacy incogniton_manager names ----------
# These let existing consumers switch to this module by changing only the
# import path; the call sites and their logic stay exactly as they were.

def is_incogniton_running():
    return is_running()


def launch_incogniton():
    return launch()


def wait_for_incogniton_ready(timeout=60, logger_callback=print):
    return wait_for_ready(timeout=timeout, logger_callback=logger_callback)


def create_incogniton_profile(profile_data):
    return create_profile(profile_data)
