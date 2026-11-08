# Extra CA certificates

PEM files (`.crt` or `.pem`) placed here are trusted by every Docker image built from `docker/Dockerfile`, both during the build and at runtime. A file may hold several certificates.

Use this when building behind a TLS-inspecting proxy, or when PR-Agent talks to servers signed by a private CA. Leave the directory empty otherwise. The files are git-ignored.
