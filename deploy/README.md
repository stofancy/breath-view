# Reverse-proxy examples

These files are deployment templates, not a copy of any private installation.
They intentionally use `breath-view.example.org`, placeholder certificate
paths and a server-side upstream include. Replace the placeholders locally;
never commit the resulting credentials, capability URL or allowlist.

## Recommended boundary

1. Run Breath View on a private host with persistent storage mounted at
   `/data`.
2. Bind the application to the private interface only when a reverse proxy
   and an authentication layer are already in place.
3. Terminate TLS at the proxy and disable access logs for URLs that may carry
   the application's capability token.
4. Keep the upstream target and any OAuth client secret in a root-readable
   runtime-only file. Do not put them in this repository.
5. Restrict uploads, use a suitable request timeout, and do not share links
   containing health data.

`oauth2-proxy`-style configuration is shown in
[oauth2-breath-view.example.cfg](oauth2-breath-view.example.cfg). The Nginx
shape is in [nginx.example.conf](nginx.example.conf); its `include` paths are
deliberately left for the operator to create on the server.

## Rollback

Remove the site from the reverse proxy, validate the proxy configuration, and
reload it. Stop the Breath View container if the service should be withdrawn.
The application stores snapshots in its mounted data directory; remove those
separately only after confirming that they are no longer needed.

There is no supported reason to reset an unrelated VPN, tunnel, DNS zone or
reverse-proxy service as part of rolling back this application.
