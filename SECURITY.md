# Security and privacy

Please do not report a suspected vulnerability with real patient data. Remove
dates, serial numbers, symptoms, access URLs and exported reports from any
example before sending it.

For a private security report, contact the repository maintainer through the
hosting service's private security channel. If the project has no private
channel yet, open a minimal issue asking for a private contact method and do
not include exploit details.

Deployment operators should treat the following as sensitive:

- SD-card files and every generated report;
- `access-token`, patient context and log files;
- OAuth client credentials and allowlists;
- reverse-proxy upstream capability paths and private network addresses.

The default application is intended for loopback use. A public or shared
deployment must add TLS, authentication, access controls and a private data
store appropriate for its environment.
