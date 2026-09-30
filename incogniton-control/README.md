# KitKat

KitKat is a local web control center for Incogniton browser profiles. It keeps browser-facing code separate from Incogniton's unauthenticated local API, avoiding direct browser-to-port-35000 requests.

## Requirements

- Node.js 22 or newer
- Incogniton desktop app running and signed in
- Incogniton automation API enabled on port `35000`

## Start

```powershell
cd incogniton-control
npm install
npm start
```

Then open `http://127.0.0.1:4173`.

The first install adds `puppeteer-core`, which connects to Incogniton's browser without downloading another copy of Chrome.

## Current capabilities

- Detect Incogniton connection state
- List and search profiles
- Read live profile status
- Create, launch, stop, clone, and delete profiles
- Responsive profile management UI
- Local session activity history
- Saved automation workflows
- Puppeteer connection through Incogniton's local automation endpoint
- Live run progress and local run history
- Local user and role management for Super Admin, FB Admin, ND Admin, FB Operator, and ND Operator
- Server-side profile-group filtering for each user
- Persistent light and dark themes

## Local role preview

Authentication is not enabled yet. KitKat seeds a `Local Super Admin` and provides a role-preview selector in Settings so permissions can be tested locally. This selector is for development only and is not a security boundary. When sign-in is added, the authenticated user identity should replace the preview header; the role hierarchy and group checks can remain unchanged.

## Configuration

The server binds to `127.0.0.1` by default, so it is only accessible on the same computer.

Optional environment variables:

- `PORT` — KitKat port, default `4173`
- `HOST` — bind address, default `127.0.0.1`
- `INCOGNITON_URL` — Incogniton API URL, default `http://127.0.0.1:35000`

Do not expose Incogniton port `35000` directly to the internet.
