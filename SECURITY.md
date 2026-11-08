# Security

This project is a static dashboard. It never sends your spreadsheet data
anywhere except your own browser.

## Reporting a vulnerability

Please open a private security advisory, or email the maintainers via the
repository's security tab.

## Good practices

- Never commit `google_credentials.json`, `.env`, or any service account key.
- Give the service account only the access it needs (Editor on the sheet,
  or Viewer if you only export).
- Rotate keys you suspect may have leaked.
- Do not publish private data.json files that contain real transactions.
