# KitKat

KitKat is a hosted control center for Incogniton browser profiles. Supabase stores users, roles, profile summaries, and commands. A small KitKat Bridge runs on each Windows PC and is the only component allowed to call Incogniton's unauthenticated local API.

## Architecture

`KitKat website → Supabase command queue → KitKat Bridge → Incogniton`

Google Sheets and the old ND Full Automated desktop UI are not part of this architecture.

## Run the PC bridge

Every user opens `bridge/Start KitKat Bridge.bat` on their own Incogniton PC and signs in once with their own KitKat account. See `bridge/README.md` for the full setup.

## Current capabilities

- Detect Incogniton connection state
- List and search profiles
- Read live profile status
- Create, launch, stop, clone, and delete profiles
- Responsive profile management UI
- Supabase authentication and cloud command queue
- User management for Super Admin, FB Admin, ND Admin, FB Operator, and ND Operator
- Database-enforced profile-group filtering for each user
- Lightweight bridge heartbeat and automatic profile sync
- Persistent light and dark themes

Do not expose Incogniton port `35000` directly to the internet.
