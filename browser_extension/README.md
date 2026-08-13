# Fourth Down ESPN Connector scaffold

This Manifest V3 package is **not an operational connector**. It does not read,
display, store, or transfer ESPN cookies. The popup says that the connector is
unavailable.

Why: Streamlit Community Cloud does not expose a suitable authenticated REST
endpoint for a browser-extension handshake. Enabling connection requires a
separately deployed HTTPS service with a cryptographically random state/code,
five-minute-or-shorter expiry, single-use redemption, rate limiting, encrypted
secret storage, revocation, redacted logs, and an audited allowlist for both the
extension ID and the Fourth Down origin.

The disabled scaffold requests no permissions and no host access. A reviewed
operational release would add only ESPN cookie/host access and the deployed
Fourth Down handshake origin. No browsing-history, tabs-read, clipboard,
Disney+, Hulu, payments, or unrelated website permission is appropriate.
`tabs.create` is allowed by the user-initiated action and only opens Fourth Down.

Do not publish this package as a working connector until the handshake service,
token lifecycle, consent screen, disconnect/revocation flow, and automated abuse
tests are deployed and reviewed.
