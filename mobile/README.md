# AEGIS Scan — Flutter mobile purchaser app

A native Android companion to the AEGIS web UIs. A purchaser **scans a product
QR code** and instantly sees its cryptographic provenance: Canadian-content
percentage, "Buy Canadian" designation, chain validity, any integrity anomalies,
and the full supplier chain as a timeline.

This is **demo "extra"** — the scored deliverable is the backend `/verify`; the
web `frontend_react` is the judged purchaser UI. This app shows the same verdict
in a phone-native scanner for the live walkthrough.

## How it works

Mirrors the web purchaser flow exactly — the QR only carries a product id:

1. Scan QR → extract `pid` (from a `?pid=` deep link or a bare `att-…` id).
2. `GET /api/products/{pid}` → resolve the published attestation chain.
3. `POST /verify` with that chain → the scored verdict
   (`canadian_content_percentage`, `designation`, `chain_valid`, `anomalies`).
4. Render: trust banner, % gauge, designation badge, anomaly cards, and the
   provenance timeline (🇨🇦 = work performed in Canada, flagged nodes in red).

## Backend connection

The app talks to the **live AEGIS deployment on Render** by default — no LAN/USB
setup needed:

```
https://provenance-hackathon-jcim.onrender.com
```

It reads products, resolves chains, runs `/verify`, and loads QR codes straight
from that URL. The Render free tier spins the server down when idle, so the
**first request after a while takes ~30–50s** while it wakes up (request
timeouts are set to 60s to cover this); subsequent calls are instant.

- **Pick a published product** lists the live products and, via the ⟦qr⟧ button,
  **loads each product's QR code image directly from the backend**
  (`GET /api/qr/{product_id}`) — show it on one screen and scan it with another.
- Point the app at a LAN backend instead (e.g. `http://10.1.61.127:8000`, or
  `http://127.0.0.1:8000` with `adb reverse tcp:8000 tcp:8000`) via the in-app
  ⚙️ settings sheet for offline demos.

A bare-id / list fallback ("Pick a published product") is built in so the demo
never depends on a camera read.

## Build & run

```bash
flutter pub get
flutter build apk --release
adb install -r build/app/outputs/flutter-apk/app-release.apk
# launch
adb shell am start -n de.flemmings.aegis.aegis_scan/.MainActivity
```

Package id: `de.flemmings.aegis.aegis_scan`. Deps: `mobile_scanner`, `http`.
Cleartext HTTP is enabled in the manifest for the LAN/USB backend.
