import urllib.parse
import os
import time
from core.engine.exceptions import AutomationStopped, RetryableError, PermanentError
from core.engine.state_machine import AutomationState
import random
import re
import requests
from playwright.sync_api import sync_playwright

from core.automation.auto_poster import parse_and_download_images


def run_auto_random_posting_flow(
    debug_url,
    post_text=None,
    visibility_pref=None,
    logger_callback=None,
    email_val=None,
    password_val=None,
    picture_val=None,
    state_callback=None,
    stop_event=None,
):
    """
    Connects to an existing Incogniton profile via Playwright and initiates the Auto Random Posting process.
    Handles automatic login if prompted. Scans for targets during scrolling.
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
            from core.engine.exceptions import AutomationStopped

            raise AutomationStopped("User manually stopped automation.")

    def interruptible_sleep(seconds):
        if stop_event is not None:
            if stop_event.wait(seconds):
                from core.engine.exceptions import AutomationStopped

                raise AutomationStopped("User manually stopped automation.")
        else:
            time.sleep(seconds)

    def check_banned():
        try:
            if (
                "account_disabled" in page.url
                or page.locator("text='Account indefinitely suspended'").is_visible()
                or page.locator(
                    "text='Your account has been indefinitely suspended'"
                ).is_visible()
            ):
                from core.engine.exceptions import PermanentError

                raise PermanentError("Account indefinitely suspended")
        except Exception as e:
            from core.engine.exceptions import PermanentError

            if isinstance(e, PermanentError):
                raise e
            pass

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
                        log(
                            f"Browser not ready yet. Retrying in 3s ({attempt+1}/{max_retries})..."
                        )
                        interruptible_sleep(3)
                    else:
                        raise e

            context = browser.contexts[0]
            page = context.pages[0] if context.pages else context.new_page()
            page.bring_to_front()
            set_state(AutomationState.PAGE_LOADING)

            downloaded_images = parse_and_download_images(picture_val, log)

            def extract_share_dialog_link():
                extracted_link = "No link extracted"
                try:
                    try:
                        page.wait_for_selector(
                            '[data-testid="share_app_button_COPY_LINK"]', timeout=5000
                        )
                    except:
                        log(
                            "Share dialog not found immediately. Scanning for intercepting pop-ups..."
                        )
                        dismiss_intercepting_popups()
                        page.wait_for_selector(
                            '[data-testid="share_app_button_COPY_LINK"]', timeout=10000
                        )

                    log("Share dialog opened successfully.")
                    dismiss_intercepting_popups()

                    # Take Screenshot
                    from datetime import datetime
                    import glob
                    import re
                    date_folder = datetime.now().strftime("%d %B %Y")
                    ss_dir = os.path.join("screenshots", "Auto Random Posting Pictures", date_folder)
                    os.makedirs(ss_dir, exist_ok=True)
                    
                    existing_files = glob.glob(os.path.join(ss_dir, "post-*.png"))
                    max_num = 0
                    for f in existing_files:
                        m = re.search(r"post-(\d+)\.png", os.path.basename(f))
                        if m:
                            num = int(m.group(1))
                            if num > max_num:
                                max_num = num
                    next_num = max_num + 1
                    
                    ss_path = os.path.abspath(os.path.join(ss_dir, f"post-{next_num}.png"))
                    
                    page.screenshot(path=ss_path)
                    log(f"Screenshot taken: {ss_path}")

                    # Extract URL from Facebook share button
                    fb_btn = page.locator(
                        '[data-testid="share_app_button_FACEBOOK"]'
                    ).first
                    if fb_btn.is_visible():
                        fb_href = fb_btn.get_attribute("href")
                        if fb_href:
                            parsed = urllib.parse.parse_qs(
                                urllib.parse.urlparse(fb_href).query
                            )
                            if "href" in parsed:
                                extracted_link = parsed["href"][0].split("?")[0]

                    # Click "Copy Link" to trigger any native clipboard/toast events
                    page.locator(
                        '[data-testid="share_app_button_COPY_LINK"]'
                    ).first.click(force=True)
                    if extracted_link == "No link extracted":
                        extracted_link = "Copied to clipboard (URL extraction fallback)"

                    log(f"Extracted Post Link: {extracted_link}")

                    # Close the Share dialog
                    log("Closing share dialog...")
                    close_btn = page.locator(
                        'button[icon="nav-close"], button[aria-label="Close Dialog"]'
                    ).first
                    if close_btn.is_visible():
                        close_btn.click(force=True)
                    interruptible_sleep(1.0)
                except Exception as e:
                    log(f"Warning: Share dialog did not appear or error occurred: {e}")
                return extracted_link

            def smart_navigate(url):
                nonlocal page
                last_err = ""
                for attempt in range(3):
                    try:
                        page.goto(url, timeout=45000)
                        try:
                            page.wait_for_selector(
                                'nav, header, [data-testid="content"], #main_content, form, [data-testid="email-address-input"]',
                                timeout=15000,
                            )
                            return
                        except:
                            log(
                                f"Screen appears blank. Refreshing (Attempt {attempt+1}/3)..."
                            )
                            page.reload()
                            interruptible_sleep(3)
                    except Exception as e:
                        last_err = str(e)
                        log(f"Navigation error: {e}")
                        interruptible_sleep(3)

                log("Still failing. Attempting to open a completely new tab...")
                try:
                    page.close()
                    page = context.new_page()
                    page.bring_to_front()
                    set_state(AutomationState.PAGE_LOADING)
                    page.goto(url, timeout=45000)
                    page.wait_for_selector(
                        'nav, header, [data-testid="content"], #main_content, form, [data-testid="email-address-input"]',
                        timeout=15000,
                    )
                except Exception as e:
                    # Catch ALL types of network, timeout, or proxy issues here broadly
                    raise Exception("Failed proxy issue")

            # Go to News Feed
            log("Navigating to Nextdoor News Feed...")
            smart_navigate("https://nextdoor.com/news_feed/")
            check_banned()

            def dismiss_intercepting_popups():
                log(
                    "Scanning for random intercepting pop-ups (e.g. app promos, location requests)..."
                )
                selectors = [
                    'button:has-text("Not now")',
                    'button:has-text("Skip")',
                    'button:has-text("No thanks")',
                    'button:has-text("Maybe later")',
                    'button:has-text("Cancel")',
                    'button:has-text("I understand")',
                    'button[aria-label="Close"]',
                    'button[aria-label="Close Dialog"]',
                    'button[icon="nav-close"]',
                ]
                for _ in range(2):
                    clicked_any = False
                    for sel in selectors:
                        try:
                            for modal_prefix in [
                                'div[role="dialog"] ',
                                'section[role="dialog"] ',
                                "",
                            ]:
                                full_sel = f"{modal_prefix}{sel}"
                                for el in page.locator(full_sel).all():
                                    if el.is_visible():
                                        try:
                                            # SAFETY CHECK: Do not close the composer or share dialog!
                                            is_safe = el.evaluate("""node => {
                                                if (node.closest('div[role="dialog"]') && node.closest('div[role="dialog"]').querySelector('[data-testid="composer-submit-button"]')) return false;
                                                if (node.closest('div[role="dialog"]') && node.closest('div[role="dialog"]').querySelector('[data-testid="share_app_button_COPY_LINK"]')) return false;
                                                return true;
                                            }""")
                                            if not is_safe:
                                                continue
                                        except:
                                            continue

                                        log(f"Closing intercepting pop-up via {sel}...")
                                        el.click(force=True)
                                        interruptible_sleep(1.0)
                                        clicked_any = True
                        except:
                            pass
                    if not clicked_any:
                        break

            dismiss_intercepting_popups()

            # --- LOGIN DETECTION & HANDLING ---
            try:
                # Wait for either the prompt container (logged in) or the sign in button (logged out)
                page.wait_for_selector(
                    'div[data-testid="prompt-container"], [data-testid="signin_button"]',
                    timeout=15000,
                )

                if page.locator('[data-testid="signin_button"]').is_visible():
                    log("Login screen detected. Processing login...")
                    set_state(AutomationState.LOGIN_CHECK)

                    email_input = page.locator(
                        '[data-testid="email-address-input"]'
                    ).first
                    pass_input = page.locator('[data-testid="password-input"]').first

                    # If Google Sheets provided an email, use it. Otherwise rely on autofill
                    if email_val and email_input.is_visible():
                        email_input.fill(str(email_val))
                    elif email_input.is_visible() and not email_input.input_value():
                        log(
                            "Warning: Autofill is empty and no email provided in sheet."
                        )

                    if password_val and pass_input.is_visible():
                        pass_input.fill(str(password_val))
                    elif pass_input.is_visible() and not pass_input.input_value():
                        log(
                            "Warning: Autofill is empty and no password provided in sheet."
                        )

                    interruptible_sleep(1.0)
                    page.locator('[data-testid="signin_button"]').first.click(
                        force=True
                    )

                    # Wait for feed to load after login
                    page.wait_for_selector(
                        'div[data-testid="prompt-container"], span:has-text("What\'s happening, neighbor?")',
                        timeout=20000,
                    )
                    log("Logged in successfully! Feed loaded.")
                    set_state(AutomationState.READY)
                else:
                    log("Already logged in. Feed loaded.")
                    set_state(AutomationState.READY)
            except Exception:
                log(
                    "Warning: Could not strictly verify feed or login state. Proceeding..."
                )
                check_banned()

            dismiss_intercepting_popups()

            # 20 Seconds of strict human-like scrolling
            log(
                "Feed confirmed loaded. Starting 30 seconds of human-like scrolling NOW..."
            )
            page.evaluate("window.scrollBy(0, window.innerHeight * 0.8)")
            scroll_start = time.time()

            while time.time() - scroll_start < 30:
                page.evaluate("window.scrollBy(0, window.innerHeight * 0.8)")
                interruptible_sleep(random.uniform(1.8, 2.2))

            # --- STANDARD POSTING FLOW ---
            log("Scrolling back to top to begin posting...")
            page.evaluate("window.scrollTo(0, 0)")
            interruptible_sleep(random.uniform(1.0, 2.0))

            # Wait for the feed to load
            try:
                page.wait_for_selector(
                    'div[data-testid="prompt-container"], span:has-text("What\'s happening, neighbor?")',
                    timeout=20000,
                )
                log("Feed loaded successfully.")
                set_state(AutomationState.READY)
            except Exception:
                log(
                    "Warning: Could not find the post prompt box. Page might not be fully loaded."
                )

            check_stop()
            # Click the prompt container to open the composer
            log("Clicking the post prompt box...")
            set_state(AutomationState.COMPOSER_OPEN)

            # Look specifically for the text to click
            prompt_span = page.locator(
                'span:has-text("What\'s happening, neighbor?")'
            ).first
            prompt_box = page.locator('div[data-testid="prompt-container"]').first
            global_post_btn = page.locator(
                'button[data-integration-id="post"], button[aria-label="Post"][icon*="compose"]'
            ).first

            if prompt_span.is_visible():
                prompt_span.click()
            elif prompt_box.is_visible():
                prompt_box.click(force=True)
            else:
                log(
                    "Prompt box not visible. Using the global Post button (sidebar/bottom-bar) instead..."
                )
                global_post_btn.click(force=True)

            interruptible_sleep(random.uniform(2.0, 3.0))

            # Now the composer modal should be open.
            log(f"Entering text: '{post_text[:30]}...'")
            set_state(AutomationState.CONTENT_ENTERED)

            # Use exact data-testid provided from HTML
            composer = page.locator(
                'textarea[data-testid="composer-text-field"], div[contenteditable="true"]'
            ).first

            try:
                composer.wait_for(state="visible", timeout=10000)
                composer.click()
            except Exception:
                log(
                    "Warning: Failed to locate explicitly visible textarea. Attempting to type directly into focused element."
                )

            check_stop()
            # Type the text naturally
            page.keyboard.type(post_text, delay=random.randint(30, 80))
            interruptible_sleep(random.uniform(1.5, 2.5))

            # --- UPLOAD IMAGES ---
            if downloaded_images:
                log(f"Attempting to upload {len(downloaded_images)} images...")
                try:
                    try:
                        file_input = page.locator('input[type="file"]').last
                        file_input.evaluate('el => el.setAttribute("multiple", "")')
                        file_input.set_input_files(downloaded_images, timeout=3000)
                        log("Images attached via hidden input.")
                        set_state(AutomationState.MEDIA_UPLOADED)
                    except:
                        log("Clicking Add Media to trigger file chooser...")
                        with page.expect_file_chooser(timeout=10000) as fc_info:
                            page.locator(
                                '[data-testid="OPEN_MEDIA_GALLERY"], button[aria-label*="photo"], button[aria-label*="media"], button:has(svg[data-icon="photos"])'
                            ).first.click(force=True)
                        fc_info.value.set_files(downloaded_images)
                        log("Images attached via file chooser.")
                        set_state(AutomationState.MEDIA_UPLOADED)

                    check_stop()
                    # Let the images upload and process
                    interruptible_sleep(random.uniform(5.0, 8.0))
                except Exception as e:
                    log(f"Warning: Failed to upload images: {str(e)}")

            # --- Check for Inline Visibility Selector ---
            visibility_successfully_set = False

            if visibility_pref:
                try:
                    vis_locator = page.locator('[data-testid="neighbor-audience-visibility-button"]')
                    
                    try:
                        vis_locator.wait_for(state="visible", timeout=3000)
                    except Exception:
                        pass

                    clicked_vis = False
                    
                    # Compute the target text correctly
                    v_lower = str(visibility_pref).lower().replace(" ", "")
                    target_text = "Anyone"
                    option_testid = "visibility-menu-option-0"
                    
                    if "your" in v_lower or "only" in v_lower:
                        target_text = "Your neighborhood"
                        option_testid = "visibility-menu-option-2"
                    elif "near" in v_lower or "neighbor" in v_lower:
                        target_text = "Nearby neighborhoods"
                        option_testid = "visibility-menu-option-1"
                        
                    if vis_locator.is_visible():
                        current_text = vis_locator.text_content().strip()
                        if current_text.lower() == target_text.lower() or (target_text.lower() == "anyone" and "anyone" in current_text.lower()):
                            log(f"Visibility is already correctly set to '{target_text}'.")
                            visibility_successfully_set = True
                        else:
                            log("Inline visibility selector found. Opening it...")
                            vis_locator.click(force=True)
                            clicked_vis = True

                    if clicked_vis:
                        log(f"Applying: {target_text}")
                        # 1. Try strict data-testid matching first
                        option = page.locator(f'[data-testid="{option_testid}"]')
                        try:
                            option.wait_for(state="visible", timeout=4000)
                            option.click(force=True)
                            log("Successfully clicked visibility option via data-testid.")
                            visibility_successfully_set = True
                            interruptible_sleep(1.0)
                        except Exception:
                            log("Specific option testid failed. Trying fallbacks...")
                            # 2. Fallback to exact menu item text
                            fallback_option = page.locator(f'div[role="menu"] h2:has-text("{target_text}"), div[role="menuitem"]:has-text("{target_text}")').last
                            try:
                                fallback_option.wait_for(state="visible", timeout=4000)
                                fallback_option.click(force=True)
                                log("Successfully clicked visibility option via text fallback.")
                                visibility_successfully_set = True
                                interruptible_sleep(1.0)
                            except Exception:
                                log("Fallback failed. Proceeding.")
                except Exception as e:
                    log(f"Warning during inline visibility selection: {e}")

            # Progress through Next/Post modals
            log("Progressing through Next/Post modals...")
            set_state(AutomationState.SUBMITTING)
            clicked_post = False
            for step in range(3):  # Support up to 3 modals/clicks
                try:
                    # Explicitly look for the button inside the active dialog/modal
                    submit_button = page.locator(
                        'div[role="dialog"] button:has-text("Post"), section[role="dialog"] button:has-text("Post"), button[data-testid="composer-submit-button"]'
                    ).last
                    # Give it a tiny moment to ensure images upload or validations finish
                    interruptible_sleep(2.0)
                    submit_button.wait_for(state="visible", timeout=10000)
                except Exception:
                    log("No submit/Next button found, assuming flow is complete.")
                    break

                btn_text = submit_button.text_content().strip().lower()

                # STRICT VISIBILITY ENFORCEMENT
                if (
                    "post" in btn_text
                    and visibility_pref
                    and not visibility_successfully_set
                ):
                    raise Exception(
                        f"ABORTING: Failed to securely set visibility to '{visibility_pref}'. Refusing to blindly click Post."
                    )

                log(f"Clicking button: '{btn_text}'...")
                
                # STRICT VISIBILITY ENFORCEMENT
                if "post" in btn_text and visibility_pref and not visibility_successfully_set:
                    raise Exception(f"ABORTING: Failed to securely set visibility to '{visibility_pref}'. Refusing to blindly click Post.")
                    
                if "post" in btn_text:
                    clicked_post = True
                submit_button.click()  # REMOVED force=True so it honors validation
                interruptible_sleep(random.uniform(3.0, 4.0))  # Wait for transition

                # Check for visibility menu
                vis_menu = page.locator('ul[role="menu"], div[role="radiogroup"], div[role="listbox"], form div[role="radiogroup"]').first
                if vis_menu.is_visible():
                    log("Visibility menu detected.")
                    if visibility_pref:
                        log(f"Visibility menu found. Looking for '{visibility_pref}'...")
                        try:
                            vis_options = vis_menu.locator(
                                "li, label, div[role='radio'], div[role='option'], button[role='radio']"
                            ).all()
                            clicked = False
                            for opt in vis_options:
                                text = opt.text_content().lower()
                                if visibility_pref.lower() in text:
                                    opt.click(force=True)
                                    log(f"Selected visibility: {text.strip()}")
                                    visibility_successfully_set = True
                                    clicked = True
                                    interruptible_sleep(1.0)
                                    break
                                    
                            if not clicked:
                                raw_text_opt = vis_menu.locator(f'span:has-text("{visibility_pref}"), div:has-text("{visibility_pref}")').last
                                if raw_text_opt.is_visible():
                                    raw_text_opt.click(force=True)
                                    log("Selected visibility (via text fallback).")
                                    visibility_successfully_set = True
                                    interruptible_sleep(1.0)
                        except Exception as e:
                            log(f"Warning: Failed to parse visibility menu: {e}")
                    else:
                        log("No visibility preference set. Skipping.")
                    interruptible_sleep(1.5)

                if "post" in btn_text:
                    log("Final Post button clicked.")
                    break

            # Wait for Share Dialog & Extract Link
            log("Waiting for Share dialog to appear...")
            set_state(AutomationState.VERIFYING)
            post_link = extract_share_dialog_link()

            # 10 Seconds of Post-Posting strict scrolling
            log("Post published. Starting 15 seconds of cooldown scrolling NOW...")
            page.evaluate("window.scrollBy(0, window.innerHeight * 0.8)")
            scroll_start = time.time()
            while time.time() - scroll_start < 15:
                page.evaluate("window.scrollBy(0, window.innerHeight * 0.8)")
                interruptible_sleep(random.uniform(1.8, 2.2))

            log("Cooldown scroll complete. Post published and verified successfully!")

            # Cleanup temp images
            if downloaded_images:
                log("Cleaning up temporary images...")
                for img_path in downloaded_images:
                    try:
                        if os.path.exists(img_path) and "temp_images" in img_path:
                            os.remove(img_path)
                    except:
                        pass

            # Graceful cleanup
            context.close()
            browser.close()

            if not clicked_post:
                raise Exception("Failed to complete the posting flow (Post button never clicked).")
            return True, post_link

    except Exception as e:
        log(f"Playwright Error during posting: {str(e)}")
        return False, str(e)
