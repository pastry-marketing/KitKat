import time
import random
from playwright.sync_api import sync_playwright

def run_nd_creation_flow(debug_url, email, password, full_name, logger_callback=print):
    """
    Connects to the running Incogniton profile via Playwright and automates Nextdoor Account Creation.
    """
    # Split the name as requested by the user
    name_parts = str(full_name).strip().split(" ")
    first_name = name_parts[0] if name_parts else "John"
    last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else "Smith"
    
    logger_callback(f"Starting automation for: {first_name} {last_name} ({email})")
    
    with sync_playwright() as p:
        try:
            logger_callback(f"Connecting to browser at {debug_url}")
            browser = None
            for attempt in range(5):
                try:
                    browser = p.chromium.connect_over_cdp(debug_url)
                    break
                except Exception as e:
                    if attempt < 4:
                        logger_callback(f"Browser not ready yet. Retrying in 3s ({attempt+1}/5)...")
                        time.sleep(3)
                    else:
                        raise e
            context = browser.contexts[0]
            
            # CRITICAL: Auto-grant geolocation permissions so Chrome doesn't show a popup
            context.grant_permissions(['geolocation'])
            logger_callback("Geolocation permissions granted to browser context.")
            
            # Use the first already-opened tab if it exists, otherwise create a new one
            if len(context.pages) > 0:
                page = context.pages[0]
                page.bring_to_front()
            else:
                page = context.new_page()
                
            # Close any extra tabs that might have opened
            for p in context.pages:
                if p != page:
                    try:
                        p.close()
                    except:
                        pass
                        
            # CRITICAL: Block Google Sign In completely so it never tries to open
            context.route("**/*", lambda route: route.abort() if "accounts.google.com" in route.request.url else route.continue_())
                
            try:
                page.goto("https://nextdoor.com/create-account/", wait_until="domcontentloaded", timeout=15000)
            except Exception:
                # If it times out but elements are present, we can just proceed
                pass
            logger_callback("Navigated to Nextdoor.")
            
            max_steps = 40
            step = 0
            location_failed_attempts = 0
            topics_selected = False
            recommendations_followed = False
            address_interacted = False
            
            def safe_click(locator, force=True, timeout=3000):
                """Scrolls element into view and performs click with multi-tier fallback."""
                if not locator:
                    return False
                try:
                    locator.scroll_into_view_if_needed(timeout=2000)
                except Exception:
                    pass
                try:
                    locator.click(timeout=timeout)
                    return True
                except Exception:
                    if force:
                        try:
                            locator.click(force=True, timeout=2000)
                            return True
                        except Exception:
                            pass
                return False

            while step < max_steps:
                page.wait_for_timeout(1000) # Fast debounce so loop doesn't lock CPU while React transitions happen
                
                url = page.url
                
                # 1. Login/Signup Page
                if page.locator("input[name='email']").is_visible():
                    email_input = page.locator("input[name='email']")
                    if email_input.input_value() != email:
                        logger_callback("Step: Entering Email and Password")
                        page.wait_for_timeout(random.randint(500, 1000))
                        email_input.fill("")
                        email_input.type(email, delay=random.randint(50, 150))
                        
                        pass_input = page.locator("input[name='password']")
                        page.wait_for_timeout(random.randint(500, 1000))
                        pass_input.fill("")
                        pass_input.type(password, delay=random.randint(50, 150))
                    
                    # We must NOT match "Continue with Google". Priority 1: Exact "Continue" button. Priority 2: submit button.
                    submit_btn = page.get_by_role("button", name="Continue", exact=True).first
                    if not submit_btn.is_visible():
                        submit_btn = page.locator("button[type='submit']").first
                    
                    if submit_btn.is_visible():
                        safe_click(submit_btn)
                        
                    page.wait_for_timeout(4000)
                    continue
                    
                # 2. Name Page
                if page.locator("input[name='first_name']").is_visible():
                    first_input = page.locator("input[name='first_name']")
                    if first_input.input_value() != first_name:
                        logger_callback("Step: Entering First and Last Name")
                        page.wait_for_timeout(random.randint(500, 1000))
                        first_input.fill("")
                        first_input.type(first_name, delay=random.randint(50, 150))
                        
                        last_input = page.locator("input[name='last_name']")
                        page.wait_for_timeout(random.randint(500, 1000))
                        last_input.fill("")
                        last_input.type(last_name, delay=random.randint(50, 150))
                    
                    submit_btn = page.get_by_role("button", name="Continue", exact=True).first
                    if not submit_btn.is_visible():
                        submit_btn = page.locator("button[type='submit']").first
                        
                    if submit_btn.is_visible():
                        safe_click(submit_btn)
                        
                    page.wait_for_timeout(4000)
                    continue
                    
                # 3. Location Ask (Primary button)
                if page.get_by_test_id("use-location-button").is_visible() or page.locator("button:has-text('Use my current location')").is_visible():
                    logger_callback("Step: Using Current Location")
                    btn = page.locator("button:has-text('Use my current location'), [data-testid='use-location-button']").first
                    safe_click(btn)
                    page.wait_for_timeout(5000)
                    continue
                        
                # 4. Fallback / Trouble verifying location
                if page.get_by_text("Having trouble verifying your location").is_visible() or page.get_by_text("Try another method").is_visible():
                    location_failed_attempts += 1
                    logger_callback(f"Step: Location verification failed (Attempt {location_failed_attempts})")
                    
                    if location_failed_attempts >= 3:
                        logger_callback("Location failed 3 times. Stopping flow as per user instructions.")
                        return False, "Not Created"
                        
                    # Click try another method to reset loop
                    try_btn = page.locator("button:has-text('Try another method')").first
                    if try_btn.is_visible():
                        safe_click(try_btn)
                    page.wait_for_timeout(3000)
                    continue
                    
                # 5. Birth Date
                if page.get_by_text("When is your birthday?").is_visible():
                    # Based on user's DOM
                    month_input = page.locator("input[aria-label='birth month']")
                    if month_input.is_visible():
                        if not month_input.input_value():
                            logger_callback("Step: Entering Random Birth Date")
                            month = str(random.randint(1, 12))
                            day = str(random.randint(1, 28))
                            year = str(random.randint(1990, 2000))
                            
                            page.wait_for_timeout(random.randint(500, 1000))
                            month_input.fill("")
                            month_input.type(month, delay=random.randint(50, 150))
                            
                            day_input = page.locator("input[aria-label='birth day']")
                            page.wait_for_timeout(random.randint(500, 1000))
                            day_input.fill("")
                            day_input.type(day, delay=random.randint(50, 150))
                            
                            year_input = page.locator("input[aria-label='birth year']")
                            page.wait_for_timeout(random.randint(500, 1000))
                            year_input.fill("")
                            year_input.type(year, delay=random.randint(50, 150))
                    else:
                        logger_callback("Could not find birth date inputs, attempting fallback...")
                    
                    continue_btn = page.locator("button:has-text('Continue'), button[type='submit']").first
                    safe_click(continue_btn)
                    page.wait_for_timeout(3000)
                    continue
                    
                # 6. Verified Page ("You're verified! Here's a peek...")
                if page.locator("text=You're verified").is_visible() or page.locator("h1:has-text(\"You're verified\")").is_visible():
                    logger_callback("Step: Passed Verification! Clicking Continue...")
                    continue_btn = page.locator("button:has-text('Continue'), button:has-text('Next')").first
                    safe_click(continue_btn)
                    page.wait_for_timeout(3000)
                    continue
                    
                # 7. Get the App Page ("Get the Nextdoor app for real-time...")
                if page.locator("text=Get the Nextdoor app").is_visible() or page.locator("h1:has-text('Get the Nextdoor app')").is_visible():
                    logger_callback("Step: Skipping App Download. Clicking Continue...")
                    continue_btn = page.locator("button:has-text('Continue'), button:has-text('Next'), button:has-text('Not now'), button:has-text('Skip')").first
                    safe_click(continue_btn)
                    page.wait_for_timeout(3000)
                    continue
                    
                # 8. Topics Page ("What topics do you want to see on Nextdoor?")
                if page.locator("text=What topics do you want to see").is_visible() or page.locator("h1:has-text('What topics do you want to see')").is_visible():
                    if not topics_selected:
                        logger_callback("Step: Selecting Topics")
                        topics_selected = True
                        
                        chips = page.get_by_test_id("interest-chip").all()
                        if chips:
                            selected = random.sample(chips, min(3, len(chips)))
                            for chip in selected:
                                safe_click(chip)
                                page.wait_for_timeout(300)
                        else:
                            checkboxes = page.locator("input[type='checkbox']").all()
                            if checkboxes:
                                selected = random.sample(checkboxes, min(3, len(checkboxes)))
                                for cb in selected:
                                    safe_click(cb)
                                    page.wait_for_timeout(300)
                                    
                    continue_btn = page.locator("button:has-text('Continue'), button:has-text('Next')").first
                    if continue_btn.is_visible():
                        safe_click(continue_btn)
                    page.wait_for_timeout(3000)
                    continue
                    
                # 9. Recommendations Page ("Here are recommendations for you to get started.")
                if page.locator("text=Here are recommendations for you").is_visible() or page.locator("h1:has-text('Here are recommendations for you')").is_visible():
                    if not recommendations_followed:
                        logger_callback("Step: Following Recommendations")
                        recommendations_followed = True
                        
                        follow_btns = page.locator("button:has-text('Follow')").all()
                        if follow_btns:
                            max_pick = min(3, len(follow_btns))
                            min_pick = min(2, len(follow_btns))
                            num_to_follow = random.randint(min_pick, max_pick)
                            selected = random.sample(follow_btns, num_to_follow)
                            for btn in selected:
                                try:
                                    safe_click(btn)
                                    page.wait_for_timeout(400)
                                except:
                                    pass
                                    
                    continue_btn = page.locator("button:has-text('Continue'), button:has-text('Next')").first
                    if continue_btn.is_visible():
                        safe_click(continue_btn)
                    page.wait_for_timeout(3000)
                    continue
                    
                # 10. Pledge Page ("One last thing! Let's all do our part...")
                pledge_btn = page.locator('[data-testid="member-pledge-accept-button"], button:has-text("I understand"), button:has-text("Agree")').first
                pledge_header = page.locator("text='One last thing!', h1:has-text('One last thing'), h1:has-text('keep Nextdoor safe')").first
                
                if pledge_btn.is_visible() or pledge_header.is_visible() or page.locator("text='I understand'").first.is_visible():
                    logger_callback("Step: Agreeing to Pledge")
                    
                    # 1. Scroll button into view
                    try:
                        pledge_btn.scroll_into_view_if_needed(timeout=3000)
                    except Exception:
                        page.mouse.wheel(0, 600)
                        page.wait_for_timeout(500)
                    
                    # 2. Click with standard Playwright actionability
                    clicked = safe_click(pledge_btn, force=False, timeout=3000)
                        
                    # 3. Fallback: Force click on button or tapArea
                    if not clicked:
                        btn_target = page.locator('[data-testid="member-pledge-accept-button"], button:has-text("I understand")').first
                        clicked = safe_click(btn_target, force=True, timeout=2000)
                            
                    # 4. Fallback: Direct DOM click via JavaScript
                    try:
                        page.evaluate("""() => {
                            const btn = document.querySelector('[data-testid="member-pledge-accept-button"]') || 
                                        Array.from(document.querySelectorAll('button')).find(el => el.textContent.includes('I understand'));
                            if (btn) {
                                btn.scrollIntoView({ behavior: 'smooth', block: 'center' });
                                btn.click();
                            }
                        }""")
                    except Exception:
                        pass
                        
                    page.wait_for_timeout(4000)
                    continue
                    
                # 11. End state: If we reach the newsfeed, we consider it a success.
                if "nextdoor.com/news_feed" in url or page.locator("div[role='feed']").is_visible() or page.locator("nav[aria-label='Main Navigation']").is_visible():
                    logger_callback("Step: Reached News Feed! Saving password to Chrome...")
                    
                    try:
                        pass_page = context.new_page()
                        pass_page.goto("chrome://password-manager/passwords")
                        pass_page.wait_for_timeout(2000)
                        
                        pass_page.locator("#addPasswordButton").click()
                        pass_page.wait_for_timeout(1000)
                        
                        pass_page.locator("#websiteInput input").type("nextdoor.com", delay=random.randint(50, 150))
                        pass_page.wait_for_timeout(500)
                        
                        pass_page.locator("#usernameInput input").type(email, delay=random.randint(50, 150))
                        pass_page.wait_for_timeout(500)
                        
                        pass_page.locator("#passwordInput input").type(password, delay=random.randint(50, 150))
                        pass_page.wait_for_timeout(500)
                        
                        pass_page.locator("#addButton").click()
                        pass_page.wait_for_timeout(2000)
                        pass_page.close()
                        logger_callback("Password saved to Chrome successfully.")
                    except Exception as e:
                        logger_callback(f"Failed to save password to Chrome: {e}")
                        
                    logger_callback("Step: Human-like scrolling for 15 seconds...")
                    for _ in range(15):
                        # Scroll down randomly
                        page.mouse.wheel(0, random.randint(300, 800))
                        page.wait_for_timeout(random.randint(800, 1200))
                        
                        # Occasionally scroll up slightly to look human
                        if random.random() > 0.7:
                            page.mouse.wheel(0, -random.randint(100, 300))
                            page.wait_for_timeout(random.randint(400, 800))
                        
                    logger_callback("Step: Closing all tabs as requested by user...")
                    try:
                        for p_to_close in context.pages:
                            try:
                                p_to_close.close()
                            except:
                                pass
                    except:
                        pass
                    return True, "Account Created"
                
                # 10.5 Handle Address Dropdown
                address_input = page.locator("input[data-testid='autocompleteAddress'], input[name='street_address'], input[id*='address']").first
                if address_input.is_visible():
                    if not address_interacted:
                        logger_callback("Step: Address Screen Detected")
                        address_interacted = True
                        
                        # 1. Force the dropdown to filter to the exact auto-filled address by adding two spaces at the end
                        logger_callback("Adding two spaces to address input to isolate the exact match in dropdown...")
                        address_input.click()
                        address_input.press("End")
                        address_input.press("Space")
                        address_input.press("Space")
                        page.wait_for_timeout(2000)
                        
                        # 2. Look for dropdown option (try multiple common Nextdoor DOM structures)
                        dropdown_option = None
                        selectors = [
                            "[aria-label='Address autocomplete list'] > div > div",  # Old custom Nextdoor
                            "div[role='listbox'] div[role='option']",               # Standard accessible
                            "ul[role='listbox'] li",                                # Standard accessible list
                            ".pac-container .pac-item",                             # Google Maps Autocomplete
                            "div[data-testid*='autocomplete'] div[role='button']",  # Another React pattern
                            "div[data-testid*='menu'] div[role='menuitem']"         # Menu pattern
                        ]
                        
                        for sel in selectors:
                            try:
                                if page.locator(sel).first.is_visible(timeout=500):
                                    dropdown_option = page.locator(sel).first
                                    break
                            except:
                                pass
                        
                        if dropdown_option:
                            logger_callback("Choosing address from dropdown menu...")
                            safe_click(dropdown_option)
                            page.wait_for_timeout(2000)
                        
                        continue_btn = page.locator("button:has-text('Continue'), button[type='submit']").first
                        if continue_btn.is_visible() and continue_btn.is_enabled():
                            logger_callback("Clicking Continue after address selection...")
                            safe_click(continue_btn)
                        page.wait_for_timeout(3000)
                        continue
                        
                    # Check if error is present due to premature Continue click
                    if page.locator("text='Please select a valid address from the dropdown'").is_visible():
                        logger_callback("Address error detected. Triggering dropdown...")
                        address_input.click()
                        address_input.press("Space")
                        address_input.press("Backspace")
                        page.wait_for_timeout(2000)
                        continue
                        
                    # If we are on the address screen, DO NOT fall through to the catch-all Continue.
                    # Wait for dropdown to appear or for user to interact.
                    logger_callback("Waiting for address dropdown or manual selection...")
                    page.wait_for_timeout(3000)
                    continue
                
                # Handle "Not now" / Dismiss prompts (e.g. Turn on Notifications, Find Contacts, App Download, Promos)
                dismiss_btn = page.locator("button:has-text('Not now'), button:has-text('Not Now'), a:has-text('Not now'), span:has-text('Not now'), div[role='button']:has-text('Not now'), button:has-text('Skip'), button:has-text('No thanks'), button:has-text('Maybe later')").first
                if dismiss_btn.is_visible():
                    logger_callback("Step: Dismiss/Skip button detected. Clicking it...")
                    safe_click(dismiss_btn)
                    page.wait_for_timeout(3000)
                    continue

                # Catch-all for random "Continue" / "Next" buttons that pop up on unexpected screens
                continue_btn = page.locator("button:has-text('Continue'), button:has-text('Next'), button:has-text('Submit'), button[type='submit']").first
                if continue_btn.is_visible():
                    logger_callback("Unknown screen detected. Checking Continue/Next button...")
                    if continue_btn.is_enabled():
                        logger_callback("Clicking Continue/Next...")
                        safe_click(continue_btn)
                    else:
                        logger_callback("Continue/Next button is visible but disabled. Waiting...")
                    page.wait_for_timeout(3000)
                    continue
                    
                # Handle "Verifying your information..." loading screen
                if page.locator("text='Verifying your information'").is_visible() or page.locator("h1:has-text('Verifying your information')").is_visible():
                    logger_callback("Waiting for Nextdoor to verify information... (This can take a minute)")
                    page.wait_for_timeout(3000)
                    continue

                    
                step += 1
                logger_callback(f"Waiting for recognizable screen... ({step}/{max_steps})")
                
            return False, "Timeout: Failed to reach news feed within step limit."
            
        except Exception as e:
            return False, f"Automation Error: {str(e)}"
