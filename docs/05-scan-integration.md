# Scan integration progress

October 2, 2026. Camera behavior approved: a Scan button opens preview; Cancel or a matched entity stops capture. Badge-only identification approved; whether people use native Homebox accounts or borrower records is awaiting user choice.

Implemented locally: JPEG/PNG decoding with zxing-cpp; native Homebox asset and item/location QR parsing; retail GTIN checksum validation; native inventory resolution; unknown/malformed code messages; same-origin checks and request/image limits. Scanned URLs are interpreted as identifiers and never opened.

Verified in Windows Chromium at 800 by 480 with touch enabled: search and item navigation, scan-to-detail routing, camera track termination on Cancel, Desktop confirmation cancellation and no JavaScript errors. Browser used simulated camera and Homebox API.

Verified real Python server and real QR decoder locally: generated native asset QR decoded and resolved through a simulated Homebox API; unknown asset, unsafe scheme, wrong origin, oversized request and malformed JSON handled. Native /item/ and /location/ UUID routes recognized.

Pi deployment completed over Ethernet at 192.168.1.62 after reboot. Existing Homebox data restarted intact. Pinned Playwright 1.63.0 dependencies captured locally; live decoder and native asset resolution passed. Pi Chromium passed touch search, camera start/cancel using a synthetic device, scan routing and Desktop cancellation with no JavaScript errors. Physical camera acceptance remains pending. See scan-integration-results.json.

Next: physical camera scan acceptance; resolve badge identity model with user before badge enrollment. Startup helper restarts the existing baseline without creating data. Camera permission is scoped to local kiosk origin.

