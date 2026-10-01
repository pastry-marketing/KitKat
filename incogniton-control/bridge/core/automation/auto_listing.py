import time
from core.engine.exceptions import AutomationStopped, RetryableError, PermanentError
from core.engine.state_machine import AutomationState
import random
import os
from playwright.sync_api import sync_playwright

from core.automation.auto_poster import parse_and_download_images


def run_auto_listing_flow(
    debug_url,
    list_title=None,
    picture_val=None,
    price_val=None,
    description_val=None,
    category_val=None,
    logger_callback=None,
    email_val=None,
    password_val=None,
    state_callback=None,
    stop_event=None,
):
    """
    Connects to an existing Incogniton profile via Playwright and initiates the Auto Listing process on Nextdoor.
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

            # Pre-download images if any
            downloaded_images = parse_and_download_images(picture_val, log)

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
                    'button[aria-label="Close"]',
                    'button[aria-label="Close Dialog"]',
                    'button[icon="nav-close"]',
                    'button:has-text("Not now")',
                    'button:has-text("Skip")',
                    'button:has-text("No thanks")',
                    'button:has-text("Maybe later")',
                    'button:has-text("Cancel")',
                    'button:has-text("I understand")',
                ]
                for _ in range(2):
                    clicked_any = False
                    for sel in selectors:
                        try:
                            # Prioritize clicking buttons inside dialogs to avoid closing actual sidebars
                            for modal_prefix in [
                                'div[role="dialog"] ',
                                'section[role="dialog"] ',
                                "",
                            ]:
                                full_sel = f"{modal_prefix}{sel}"
                                for el in page.locator(full_sel).all():
                                    if el.is_visible():
                                        try:
                                            # SAFETY CHECK: Do not close the composer, listing form, or share dialog!
                                            is_safe = el.evaluate("""node => {
                                                if (node.closest('div[role="dialog"]') && node.closest('div[role="dialog"]').querySelector('[data-testid="composer-submit-button"]')) return false;
                                                if (node.closest('div[role="dialog"]') && node.closest('div[role="dialog"]').querySelector('[data-testid="share_app_button_COPY_LINK"]')) return false;
                                                if (node.closest('div[role="dialog"]') && node.closest('div[role="dialog"]').querySelector('[data-testid="composer-finds-title"]')) return false;
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
            scroll_start = time.time()
            scrolls = 0
            while time.time() - scroll_start < 30:
                page.evaluate("window.scrollBy(0, window.innerHeight * 0.8)")
                interruptible_sleep(random.uniform(1.8, 2.2))
                scrolls += 1
            log(f"Completed 30s of active scrolling ({scrolls} jumps).")

            # --- START ACTUAL LISTING FLOW HERE ---
            log("Navigating to For Sale and Free section...")
            smart_navigate("https://nextdoor.com/for_sale_and_free/")
            check_banned()
            dismiss_intercepting_popups()
            interruptible_sleep(random.uniform(2.0, 3.0))

            log("Clicking on 'My listings' tab...")
            try:
                my_listings_tab = page.locator(
                    '[data-testid="tab-yourItems"], a[href="/for_sale_and_free/your_items/"]'
                ).first
                my_listings_tab.wait_for(state="visible", timeout=15000)
                my_listings_tab.click(force=True)
                interruptible_sleep(random.uniform(2.0, 3.0))
            except Exception as e:
                log(f"Error: Could not find or click 'My listings' tab: {e}")
                raise Exception(f"Could not find or click 'My listings' tab: {e}")

            log("Waiting for My Listings page to load...")
            interruptible_sleep(random.uniform(2.0, 3.0))

            try:
                # Wait for either the empty state button or the first listing item
                page.wait_for_selector(
                    'button:has-text("Create a listing"), [data-testid="classified-your-listing-item"]',
                    timeout=15000,
                )
            except Exception:
                log(
                    "Warning: Could not strictly determine if page is empty or has listings."
                )

            listings = page.locator('[data-testid="classified-your-listing-item"]')
            count = listings.count()
            log(f"Found {count} existing listings.")

            # Delete older listings if we have 5 or more, to keep the max at 5 AFTER we post the new one
            while count >= 5:
                log(
                    f"Listing limit reached ({count} >= 5). Deleting the oldest listing at the bottom..."
                )
                try:
                    last_item = listings.last
                    options_btn = last_item.locator(
                        'button[aria-label="Options"], button:has(svg[data-icon="more"])'
                    ).first
                    options_btn.scroll_into_view_if_needed()
                    interruptible_sleep(1.0)
                    options_btn.click(force=True)

                    log("Clicked Options (3 dots).")
                    delete_opt = page.locator(
                        '[data-testid="classified-dropdown-option-delete"]'
                    ).first
                    delete_opt.wait_for(state="visible", timeout=5000)
                    delete_opt.click(force=True)

                    log("Clicked Delete in dropdown. Waiting for confirmation popup...")
                    confirm_delete = page.locator(
                        '[data-testid="mark-delete-button"]'
                    ).first
                    confirm_delete.wait_for(state="visible", timeout=5000)
                    confirm_delete.click(force=True)

                    log("Confirmed deletion. Waiting for UI to refresh...")
                    interruptible_sleep(random.uniform(3.5, 5.0))
                    count = listings.count()
                    log(f"Listings remaining: {count}")
                except Exception as e:
                    log(f"Error during deletion process: {str(e)}")
                    break

            if count == 0:
                log(
                    "Zero listings remain. Clicking empty-state 'Create a listing' button..."
                )
                try:
                    create_btn = page.locator(
                        'button:has-text("Create a listing")'
                    ).first
                    create_btn.click(force=True)
                    interruptible_sleep(random.uniform(2.0, 3.0))
                    log("Create listing form opened successfully.")
                    set_state(AutomationState.COMPOSER_OPEN)
                except Exception as e:
                    log(
                        f"Warning: Could not find 'Create a listing' button. Exception: {e}"
                    )
            else:
                log(
                    f"{count} listings remain. Clicking sidebar 'Post' button to create a new listing..."
                )
                try:
                    sidebar_post_btn = page.locator(
                        'button[data-integration-id="post"], button[aria-label="Post"][icon*="compose"]'
                    ).first
                    sidebar_post_btn.wait_for(state="visible", timeout=10000)
                    sidebar_post_btn.click(force=True)
                    interruptible_sleep(random.uniform(2.0, 3.0))
                    log("Sidebar Post button clicked. Listing form should now be open.")
                    set_state(AutomationState.COMPOSER_OPEN)
                except Exception as e:
                    log(
                        f"Warning: Could not find sidebar 'Post' button. Exception: {e}"
                    )

            # --- POPUP / FORM FILLING ---
            # 1. Skip modal check
            log("Waiting for potential 'Skip' popup...")
            try:
                skip_btn = page.locator('button:has-text("Skip")').first
                skip_btn.wait_for(state="visible", timeout=5000)
                skip_btn.click(force=True)
                log("Clicked 'Skip' on the popup.")
                interruptible_sleep(random.uniform(1.0, 2.0))
            except Exception:
                log("No 'Skip' popup appeared (or timed out). Proceeding...")

            check_stop()
            # 2. Main Composer
            log("Waiting for New Listing composer...")
            extracted_link = "No link extracted"
            chat_count = "0"
            try:
                # Wait for title input to appear
                title_input = page.locator('[data-testid="composer-finds-title"]').first
                title_input.wait_for(state="visible", timeout=15000)

                # Upload Images
                if downloaded_images:
                    log(f"Uploading {len(downloaded_images)} images...")
                    try:
                        try:
                            # 1. Target the file input inside the active modal (using .last)
                            file_input = page.locator(
                                '[data-testid="uploader-fileinput"], input[type="file"]'
                            ).last
                            file_input.set_input_files(downloaded_images, timeout=3000)
                            log("Images attached via hidden input.")
                            set_state(AutomationState.MEDIA_UPLOADED)
                        except Exception as fallback_e:
                            log("Direct input failed. Trying file chooser fallback...")
                            with page.expect_file_chooser(timeout=10000) as fc_info:
                                page.locator(
                                    'label:has(input[type="file"]), [data-testid="uploader"]'
                                ).last.click(force=True)
                            fc_info.value.set_files(downloaded_images)
                            log("Images attached via file chooser.")
                            set_state(AutomationState.MEDIA_UPLOADED)
                        interruptible_sleep(random.uniform(4.0, 6.0))  # Let them upload
                    except Exception as e:
                        log(f"Warning: Failed to attach images: {e}")

                # Fill Title
                if list_title:
                    log(f"Entering Title: {str(list_title)[:30]}...")
                    title_input.fill(str(list_title))
                    interruptible_sleep(random.uniform(0.5, 1.0))

                # Fill Price or mark as Free
                if price_val:
                    if str(price_val).strip().lower() == "free":
                        log("Marking item as Free...")
                        free_switch = page.locator('button[role="switch"]').first
                        free_switch.click(force=True)
                    else:
                        log(f"Entering Price: {price_val}")
                        price_input = page.locator(
                            '[data-testid="fsf-price-field"]'
                        ).first
                        price_input.fill(str(price_val))
                    interruptible_sleep(random.uniform(0.5, 1.0))

                # Fill Description
                if description_val:
                    log("Entering Description...")
                    set_state(AutomationState.CONTENT_ENTERED)
                    desc_input = page.locator(
                        'textarea[id="finds-flow-textarea"]'
                    ).first
                    desc_input.fill(str(description_val))
                    interruptible_sleep(random.uniform(0.5, 1.0))

                # Category Handling
                target_category = (
                    str(category_val).strip() if category_val else "Neighbor services"
                )
                log(f"Selecting Category: '{target_category}'...")
                try:
                    # Click the category input/button to open dropdown
                    cat_input = page.locator(
                        'input[aria-label="Category"], button:has(input[aria-label="Category"])'
                    ).first
                    cat_input.click(force=True)
                    interruptible_sleep(1.0)

                    # Try to select the specific category, fallback to Neighbor services if not found
                    cat_item = page.locator(
                        f'[role="menuitem"]:has-text("{target_category}"), [role="option"]:has-text("{target_category}"), div:has-text("{target_category}")'
                    ).last
                    if cat_item.is_visible():
                        cat_item.scroll_into_view_if_needed()
                        cat_item.click(force=True)
                    else:
                        log(
                            f"Warning: '{target_category}' not visible. Falling back to 'Neighbor services'..."
                        )
                        fallback = page.locator(
                            '[role="menuitem"]:has-text("Neighbor services"), [role="option"]:has-text("Neighbor services"), div:has-text("Neighbor services")'
                        ).last
                        fallback.scroll_into_view_if_needed()
                        fallback.click(force=True)

                    interruptible_sleep(random.uniform(1.0, 1.5))
                except Exception as e:
                    log(f"Error: Failed to select category: {e}")
                    raise Exception(f"Failed to select category: {e}")

                check_stop()
                # Click Next
                log("Clicking 'Next' button...")
                set_state(AutomationState.SUBMITTING)
                try:
                    # Give it a second to validate category/images so the button becomes enabled
                    interruptible_sleep(2.0)
                    next_btn = page.locator('button:has-text("Next")').last
                    next_btn.wait_for(state="visible", timeout=10000)
                    next_btn.click()  # REMOVED force=True so it waits for it to be clickable
                    interruptible_sleep(random.uniform(2.0, 3.0))
                    log("Moved to the next step.")
                except Exception as e:
                    log(f"Error: Failed to click Next: {e}")
                    raise Exception(f"Failed to click Next: {e}")

                # Final Post button confirmation
                log("Waiting for the final confirmation popup...")
                try:
                    # Explicitly look for the Post button INSIDE a dialog/modal to avoid clicking the top nav Post button
                    final_post_btn = page.locator(
                        'section[role="dialog"] button:has-text("Post"), div[role="dialog"] button:has-text("Post")'
                    ).last
                    final_post_btn.wait_for(state="visible", timeout=15000)
                    log("Clicking final 'Post' button...")
                    final_post_btn.click()  # REMOVED force=True
                    log("Listing submitted! Waiting a few seconds for processing...")
                    interruptible_sleep(random.uniform(4.0, 6.0))
                except Exception as e:
                    log(f"Warning: Failed to click final Post button: {e}")

                check_stop()
                # Wait for Share Dialog & Extract Link
                log("Waiting for 'Share this listing' dialog to appear...")
                set_state(AutomationState.VERIFYING)
                extracted_link = "No link extracted"
                try:
                    page.wait_for_selector(
                        '[data-testid="share_app_button_COPY_LINK"]', timeout=15000
                    )
                    log("Share dialog opened successfully.")
                    dismiss_intercepting_popups()

                    # Take Screenshot
                    from datetime import datetime
                    import glob
                    import re
                    date_folder = datetime.now().strftime("%d %B %Y")
                    ss_dir = os.path.join("screenshots", "Auto Listing Pictures", date_folder)
                    os.makedirs(ss_dir, exist_ok=True)
                    
                    existing_files = glob.glob(os.path.join(ss_dir, "listing-*.png"))
                    max_num = 0
                    for f in existing_files:
                        m = re.search(r"listing-(\d+)\.png", os.path.basename(f))
                        if m:
                            num = int(m.group(1))
                            if num > max_num:
                                max_num = num
                    next_num = max_num + 1
                    
                    ss_path = os.path.abspath(os.path.join(ss_dir, f"listing-{next_num}.png"))
                    
                    page.screenshot(path=ss_path)
                    log(f"Screenshot taken: {ss_path}")

                    # Extract URL from Facebook share button
                    import urllib.parse

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

                    log(f"Extracted Listing Link: {extracted_link}")

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

                # 10 Seconds of Post-Listing strict scrolling
                log("Navigating back to News Feed for 10s cooldown scroll...")
                try:
                    smart_navigate("https://nextdoor.com/news_feed/")
                    check_banned()
                    dismiss_intercepting_popups()
                    log(
                        "Feed re-loaded. Starting 15s of active cooldown scrolling NOW..."
                    )
                    page.evaluate("window.scrollBy(0, window.innerHeight * 0.8)")
                    scroll_start = time.time()
                    while time.time() - scroll_start < 15:
                        page.evaluate("window.scrollBy(0, window.innerHeight * 0.8)")
                        interruptible_sleep(random.uniform(1.8, 2.2))
                    log("Cooldown scroll complete.")
                except Exception as e:
                    log(f"Warning during cooldown scroll: {e}")

                # Extract Chat Count
                chat_count = "0"
                try:
                    chat_badge = page.locator(
                        '[data-testid="floating-chat-bar-touchable-area"] span[class*="Badge_variant_number"]:visible'
                    ).first
                    chat_badge.wait_for(state="visible", timeout=5000)
                    chat_count = chat_badge.text_content().strip()
                    log(f"Found Chat Count: {chat_count}")
                except Exception:
                    log("No active chat notifications found.")

                log("Auto Listing flow completed successfully!")

            except Exception as e:
                log(f"Error: Issue filling the composer: {e}")
                raise Exception(f"Issue filling the composer: {e}")

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

            return True, extracted_link, chat_count

    except Exception as e:
        log(f"Error during Auto Listing: {str(e)}")
        return False, str(e), "0"
