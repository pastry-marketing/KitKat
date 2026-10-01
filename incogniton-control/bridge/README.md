# KitKat Bridge

The bridge is the only local KitKat component. It connects the KitKat website to the Incogniton API on the same Windows PC.

It does **not** use Google Sheets and does **not** run the old ND Full Automated desktop application.

## First run

1. Install Python 3 if it is not already installed.
2. Open Incogniton and enable its local API on port `35000`.
3. Double-click `Start KitKat Bridge.bat`.
4. Sign in once with the KitKat Super Admin account.

The password is never saved. Supabase returns a refresh session which is protected with Windows Data Protection API and stored at:

`%APPDATA%\KitKat Bridge\session.json`

The saved session only works for the same Windows user on the same PC. Delete that file to disconnect the PC and require a new sign-in.

## Current bridge commands

- Sync Incogniton profiles
- Create a profile
- Launch a profile
- Stop a profile
- Clone a profile
- Delete a profile

Browser posting and other automations will be added separately when their exact KitKat controls are defined.

## Optional settings

- `INCOGNITON_URL` — defaults to `http://127.0.0.1:35000`
- `KITKAT_POLL_SECONDS` — defaults to `2`
