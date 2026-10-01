import time
from core.engine.exceptions import AutomationStopped, RetryableError, PermanentError
from core.engine.state_machine import AutomationState
import random
from playwright.sync_api import sync_playwright


def run_auto_warmup_flow(
    debug_url,
    logger_callback=None,
    email_val=None,
    password_val=None,
    state_callback=None,
    stop_event=None,
):
    """
    Connects to an existing Incogniton profile via Playwright and initiates the Auto Warmup process.
    Scrolls for 40 seconds and likes 2-3 random posts.
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

            # --- 40 SECOND SCROLL & LIKE LOGIC ---
            log(
                "Feed confirmed loaded. Starting 50 seconds of active warmup scrolling NOW..."
            )
            set_state(
                AutomationState.RUNNING
                if hasattr(AutomationState, "RUNNING")
                else AutomationState.READY
            )
            page.evaluate("window.scrollBy(0, window.innerHeight * 0.8)")
            scroll_start = time.time()
            scrolls = 0

            likes_to_do = random.randint(2, 3)
            likes_done = 0

            while time.time() - scroll_start < 50:
                page.evaluate("window.scrollBy(0, window.innerHeight * 0.8)")
                interruptible_sleep(random.uniform(1.8, 2.2))
                scrolls += 1

                # Attempt to like a post if we haven't hit our quota
                # 0.3 chance to try per scroll jump if we still need likes
                if likes_done < likes_to_do and random.random() < 0.3:
                    try:
                        # Broad selectors for Like buttons on Nextdoor
                        # We use .all() to grab all on screen, but we just want one that is visible
                        like_buttons = page.locator(
                            'button[aria-label="Like"], button[aria-label^="React"], [role="button"][aria-label="Like"]'
                        ).all()
                        for btn in like_buttons:
                            if btn.is_visible():
                                btn.scroll_into_view_if_needed()
                                interruptible_sleep(0.5)
                                btn.click(force=True)
                                likes_done += 1
                                log(f"Liked a post! ({likes_done}/{likes_to_do})")
                                interruptible_sleep(1.0)
                                break
                    except Exception:
                        pass

            log(
                f"Completed 50s of active warmup scrolling ({scrolls} jumps). Total likes: {likes_done}"
            )
            set_state(AutomationState.SUCCESS)

            # Graceful cleanup
            context.close()
            browser.close()

            return True, "Warmup done"

    except Exception as e:
        log(f"Error during Auto Warmup: {str(e)}")
        return False, str(e)
