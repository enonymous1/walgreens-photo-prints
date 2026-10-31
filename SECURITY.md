# Security

## Credentials

- Never commit a `.env` file, an API key, an affiliate ID, or a SAS
  upload URL. Configuration comes from the environment or a `.env`
  file that is gitignored; see `.env.example` for the shape.
- `creds` output redacts the SAS token, and submit previews redact
  the API key. Treat any printed upload URL as a live credential:
  do not paste it into issues, screenshots, or chat logs.
- This project is not affiliated with or endorsed by Walgreens.
  Do not use Walgreens branding in a way that implies endorsement.

## If a key leaks

1. Rotate or revoke the key in the Walgreens Developer Portal
   immediately. Do not reuse a key that was ever committed, even
   if the commit was later deleted: history, zips, and caches keep
   copies.
2. Remove the key from the repository, including history, and from
   any published artifact. A new commit on top does not clean
   history; a leaked key needs a fresh, scrubbed export.
3. Re-issue credentials through the environment only, and re-run
   the sandbox smoke test with the fresh key before any release.

## Reporting a vulnerability

Open an issue describing the problem without including any live
credential, customer data, or real order detail. Replace secrets
with `***` and use fictional values (for example `example.test`)
in any reproduction.
