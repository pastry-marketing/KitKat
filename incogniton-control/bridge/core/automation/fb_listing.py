import time
import random
import os
import re
import uuid
import tempfile
import requests
from core.engine.state_machine import AutomationState
from core.engine.exceptions import AutomationStopped, RetryableError, PermanentError
from playwright.sync_api import sync_playwright

FB_HOME = "https://www.facebook.com/"
FB_MARKETPLACE_CREATE = "https://www.facebook.com/marketplace/create/item"


def run_fb_listing_flow(
    debug_url,
    post=None,
    logger_callback=None,
    state_callback=None,
    stop_event=None,
):
    """
    Connects to a running browser profile (Incogniton/AdsPower) via Playwright and:
      1. Opens facebook.com (reuses an existing Facebook tab if one is open,
         otherwise opens it in a new tab).
      2. Verifies the profile is logged into Facebook.
      3. Scrolls the feed for ~15 seconds (warmup).
      4. Opens the Marketplace "Create item" page.

    The actual listing form fill happens after this (added in a later step).
    """

    def log(msg):
        if logger_callback:
            logger_callback(msg)
        else:
            print(msg)

    def set_state(state, msg=""):
        if state_callback:
            state_callback(state, msg)

    def check_stop():
        if stop_event and stop_event.is_set():
            raise AutomationStopped("User manually stopped automation.")

    def interruptible_sleep(seconds):
        if stop_event is not None:
            if stop_event.wait(seconds):
                raise AutomationStopped("User manually stopped automation.")
        else:
            time.sleep(seconds)

    def is_logged_out(page):
        """Detects the Facebook login screen."""
        try:
            login_selectors = [
                'input[name="email"]',
                '#email',
                '[data-testid="royal_email"]',
                'button[name="login"]',
                '[data-testid="royal_login_button"]',
            ]
            for sel in login_selectors:
                loc = page.locator(sel)
                if loc.count() > 0 and loc.first.is_visible():
                    return True
            url = (page.url or "").lower()
            if "login" in url or "/checkpoint" in url or "recover" in url:
                return True
        except Exception:
            pass
        return False

    def is_logged_in(page):
        """Detects a logged-in Facebook session (feed/navigation present)."""
        selectors = [
            '[aria-label="Create a post"]',
            '[aria-label="Your profile"]',
            '[aria-label="Search Facebook"]',
            'div[role="feed"]',
            '[aria-label="Facebook"][role="navigation"]',
        ]
        for sel in selectors:
            try:
                loc = page.locator(sel)
                if loc.count() > 0 and loc.first.is_visible():
                    return True
            except Exception:
                pass
        return False

    try:
        with sync_playwright() as p:
            log("Connecting to browser...")
            set_state(AutomationState.CDP_CONNECTING)

            max_retries = 5
            browser = None
            for attempt in range(max_retries):
                try:
                    browser = p.chromium.connect_over_cdp(debug_url)
                    break
                except Exception as e:
                    if attempt < max_retries - 1:
                        log(f"Browser not ready yet. Retrying in 3s ({attempt+1}/{max_retries})...")
                        interruptible_sleep(3)
                    else:
                        raise e

            context = browser.contexts[0] if browser.contexts else browser.new_context()

            # 1. Reuse an existing Facebook tab if one is already open, else open a new tab.
            check_stop()
            set_state(AutomationState.PAGE_LOADING)
            page = None
            for pg in context.pages:
                try:
                    if "facebook.com" in (pg.url or "").lower():
                        page = pg
                        log("Found an existing Facebook tab. Reusing it.")
                        break
                except Exception:
                    pass

            if page is None:
                log("No Facebook tab open. Opening facebook.com in a new tab...")
                page = context.new_page()
                page.goto(FB_HOME, timeout=60000)

            page.bring_to_front()

            # Make sure we are actually on Facebook home before checking login state.
            try:
                if "facebook.com" not in (page.url or "").lower():
                    page.goto(FB_HOME, timeout=60000)
            except Exception:
                pass

            try:
                page.wait_for_load_state("domcontentloaded", timeout=30000)
            except Exception:
                pass
            interruptible_sleep(2)

            # 2. Verify the profile is logged in.
            check_stop()
            set_state(AutomationState.LOGIN_CHECK if hasattr(AutomationState, "LOGIN_CHECK") else AutomationState.PAGE_LOADING)
            if is_logged_out(page) and not is_logged_in(page):
                raise PermanentError("Facebook profile is not logged in. Please log in to this profile first.")
            log("Facebook session is logged in.")
            set_state(AutomationState.READY)

            # 3. Scroll the feed for ~15 seconds.
            check_stop()
            log("Scrolling the Facebook feed for 15 seconds...")
            scroll_start = time.time()
            while time.time() - scroll_start < 15:
                check_stop()
                try:
                    page.evaluate("window.scrollBy(0, window.innerHeight * 0.8)")
                except Exception:
                    pass
                interruptible_sleep(random.uniform(1.5, 2.2))
            log("Finished 15s feed scroll.")

            # 4. Open the Marketplace "Create item" page.
            check_stop()
            log("Opening Marketplace create item page...")
            page.goto(FB_MARKETPLACE_CREATE, timeout=60000)
            try:
                page.wait_for_load_state("domcontentloaded", timeout=30000)
            except Exception:
                pass

            # Best-effort wait for the create-listing form to appear.
            form_ready = False
            for sel in [
                'input[type="file"]',
                'label:has-text("Title")',
                'span:has-text("Photos")',
                'span:has-text("Item for sale")',
            ]:
                try:
                    page.wait_for_selector(sel, timeout=15000)
                    form_ready = True
                    break
                except Exception:
                    continue

            if form_ready:
                log("Marketplace create item page is open and ready.")
            else:
                log("Opened Marketplace create item URL (form controls not confirmed yet).")

            # ---------------------------------------------------------------
            # Fill the "Item for sale" form.
            # ---------------------------------------------------------------
            from core.automation.profile_builder import get_val
            # Reuse the exact same image handler as Auto Posting: it supports
            # Google Drive links, direct image URLs, and local files (in the app
            # folder or the "pictures"/"images" subfolders).
            from core.automation.auto_poster import parse_and_download_images

            def fill_field(label, value):
                """Fills a text input / textarea identified by its FB label."""
                if value is None or str(value).strip() == "":
                    return False
                value = str(value)
                try:
                    loc = page.get_by_label(label, exact=True).first
                    loc.click()
                    loc.fill(value)
                    return True
                except Exception:
                    try:
                        inp = page.locator(
                            f'label:has(span:text-is("{label}")) input, '
                            f'label:has(span:text-is("{label}")) textarea'
                        ).first
                        inp.click()
                        inp.fill(value)
                        return True
                    except Exception as e:
                        log(f"Could not fill '{label}': {e}")
                        return False

            def select_dropdown(label, value):
                """Opens a combobox by its label and clicks the option matching value."""
                if value is None or str(value).strip() == "":
                    return False
                value = str(value)
                try:
                    combo = page.locator(f'label[role="combobox"]:has-text("{label}")').first
                    combo.click()
                    interruptible_sleep(1.0)
                except Exception as e:
                    log(f"Could not open '{label}' dropdown: {e}")
                    return False

                # Options may render as role=option/menuitem (Condition listbox)
                # or as role=button rows (Category picker). The visible label is
                # inside a nested <span>, so an exact span match is most reliable.
                esc = value.replace('"', '\\"')
                # Case-insensitive exact match (tolerates minor casing/spacing in the sheet).
                ci_exact = re.compile(rf"^\s*{re.escape(value)}\s*$", re.IGNORECASE)
                option_getters = [
                    lambda: page.locator(f'div[role="option"]:has(span:text-is("{esc}"))'),
                    lambda: page.locator(f'div[role="button"]:has(span:text-is("{esc}"))'),
                    lambda: page.locator(f'div[role="menuitemradio"]:has(span:text-is("{esc}"))'),
                    lambda: page.get_by_role("option", name=ci_exact),
                    lambda: page.get_by_role("menuitem", name=ci_exact),
                    lambda: page.get_by_role("option", name=value, exact=True),
                    lambda: page.get_by_role("menuitem", name=value, exact=True),
                    lambda: page.get_by_role("option", name=value),
                    lambda: page.get_by_role("menuitem", name=value),
                    lambda: page.get_by_role("button", name=value),
                    lambda: page.locator(
                        f'div[role="option"]:has-text("{esc}"), '
                        f'div[role="menuitem"]:has-text("{esc}"), '
                        f'div[role="button"]:has-text("{esc}")'
                    ),
                ]
                for getter in option_getters:
                    try:
                        cand = getter().first
                        cand.wait_for(state="visible", timeout=3000)
                        cand.scroll_into_view_if_needed(timeout=2000)
                        cand.click()
                        return True
                    except Exception:
                        continue
                log(f"Could not find option '{value}' for '{label}'.")
                try:
                    page.keyboard.press("Escape")
                except Exception:
                    pass
                return False

            # 1. Photos
            check_stop()
            photos_val = get_val(post or {}, "pictures", "picture", "photos", "photo", "images", "image", "picture link")
            photo_paths = parse_and_download_images(photos_val, log)
            if photo_paths:
                try:
                    file_input = page.locator('input[type="file"][accept*="image"]').first
                    file_input.set_input_files(photo_paths)
                    log(f"Uploaded {len(photo_paths)} photo(s).")
                    interruptible_sleep(3)
                except Exception as e:
                    log(f"Could not upload photos: {e}")
            else:
                log("No photos provided/resolved; skipping photo upload.")

            # 2. Title
            check_stop()
            title_val = get_val(post or {}, "title", "listing title", "item title", "item name")
            if fill_field("Title", title_val):
                log(f"Title set: {title_val}")

            # 3. Price
            check_stop()
            price_val = get_val(post or {}, "price", "amount")
            if fill_field("Price", price_val):
                log(f"Price set: {price_val}")

            # 4. Category
            check_stop()
            category_val = get_val(post or {}, "category")
            if category_val:
                if select_dropdown("Category", category_val):
                    log(f"Category set: {category_val}")

            # 5. Condition
            check_stop()
            condition_val = get_val(post or {}, "condition")
            if condition_val:
                if select_dropdown("Condition", condition_val):
                    log(f"Condition set: {condition_val}")

            # 6. Description
            check_stop()
            description_val = get_val(post or {}, "description", "desc", "details")
            if fill_field("Description", description_val):
                log("Description set.")

            # ---------------------------------------------------------------
            # Step 1 -> Step 2 (Delivery method): click Next.
            # ---------------------------------------------------------------
            def click_next():
                """Clicks an enabled 'Next' button; returns True on success."""
                for sel in [
                    'div[role="button"][aria-label="Next"]:not([aria-disabled="true"])',
                    'div[aria-label="Next"][role="button"]:not([aria-disabled="true"])',
                ]:
                    try:
                        btn = page.locator(sel).first
                        btn.wait_for(state="visible", timeout=8000)
                        btn.click()
                        return True
                    except Exception:
                        continue
                try:
                    page.locator('div[aria-label="Next"]').first.click()
                    return True
                except Exception as e:
                    log(f"Could not click Next: {e}")
                    return False

            check_stop()
            log("Clicking Next -> Delivery method step...")
            if not click_next():
                return False, "Could not advance to the Delivery method step"

            try:
                page.wait_for_selector(
                    'input[aria-label="Location"], h1:has-text("Delivery method")',
                    timeout=20000,
                )
            except Exception:
                pass
            interruptible_sleep(2)

            # ---------------------------------------------------------------
            # Step 2: Location (type-to-search, then pick a suggestion).
            # Delivery method defaults to "Local pickup only" and is left as-is.
            # ---------------------------------------------------------------
            check_stop()
            location_val = get_val(post or {}, "location", "city", "area", "place")
            if location_val:
                try:
                    loc = page.locator('input[aria-label="Location"]').first
                    loc.click()
                    try:
                        loc.fill("")
                    except Exception:
                        pass
                    loc.press_sequentially(str(location_val), delay=60)
                    interruptible_sleep(2.5)

                    options = page.locator('ul[role="listbox"] li[role="option"]')
                    options.first.wait_for(state="visible", timeout=8000)

                    chosen = None
                    val_l = str(location_val).strip().lower()
                    for i in range(min(options.count(), 10)):
                        li = options.nth(i)
                        try:
                            txt = (li.inner_text() or "").lower()
                        except Exception:
                            txt = ""
                        if val_l and val_l in txt:
                            chosen = li
                            break
                    if chosen is None:
                        chosen = options.first
                    chosen.click()
                    log(f"Location set: {location_val}")
                    interruptible_sleep(1.5)
                except Exception as e:
                    log(f"Could not set location: {e}")
            else:
                log("No location provided; FB requires one to continue past this step.")

            # Confirm the location was accepted (green tick / "valid" helper text).
            try:
                page.wait_for_selector("text=Input Location is valid.", timeout=8000)
                log("Location confirmed valid.")
            except Exception:
                log("Warning: could not confirm location validity; continuing.")

            # ---------------------------------------------------------------
            # Meetup preferences: tick all options.
            # ---------------------------------------------------------------
            check_stop()
            for pref in ["Public meetup", "Door pickup", "Door dropoff"]:
                try:
                    cb = page.locator(f'div[role="checkbox"]:has-text("{pref}")').first
                    if cb.count() == 0:
                        continue
                    if (cb.get_attribute("aria-checked") or "").lower() != "true":
                        cb.click()
                        log(f"Enabled meetup preference: {pref}")
                        interruptible_sleep(0.5)
                except Exception as e:
                    log(f"Could not toggle '{pref}': {e}")

            # ---------------------------------------------------------------
            # Step 2 -> Step 3: click Next.
            # ---------------------------------------------------------------
            check_stop()
            log("Clicking Next -> final step...")
            if not click_next():
                return False, "Could not advance to the final step"
            try:
                page.wait_for_selector(
                    'div[role="button"][aria-label="Publish"], h1:has-text("List in more places")',
                    timeout=20000,
                )
            except Exception:
                pass
            interruptible_sleep(2)

            # ---------------------------------------------------------------
            # Step 3 ("List in more places"): Publish.
            # Leaves the default public Marketplace listing (no extra groups).
            # ---------------------------------------------------------------
            check_stop()

            def click_publish():
                for sel in [
                    'div[role="button"][aria-label="Publish"]:not([aria-disabled="true"])',
                    'div[aria-label="Publish"][role="button"]',
                ]:
                    try:
                        btn = page.locator(sel).first
                        btn.wait_for(state="visible", timeout=10000)
                        btn.click()
                        return True
                    except Exception:
                        continue
                return False

            log("Publishing listing...")
            if not click_publish():
                return False, "Could not click Publish"

            # Give FB time to submit; on success it navigates away from the form.
            interruptible_sleep(6)
            log("Listing published.")
            set_state(AutomationState.SUCCESS)
            return True, "Published Marketplace listing"

    except AutomationStopped as e:
        log(f"Stopped: {e}")
        raise
    except PermanentError as e:
        log(f"FB Listing failed: {e}")
        return False, str(e)
    except Exception as e:
        log(f"Error during FB Listing: {str(e)}")
        return False, str(e)
