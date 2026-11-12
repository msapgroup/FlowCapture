# Hosting FlowCapture and accessing it from Teams

## Current status

FlowCapture is a single-company **early pilot**. Its current database is SQLite, and original files are stored on a local filesystem. It is not production-ready or suitable for direct exposure to the public internet. Gmail, QuickBooks, AI extraction, production hosting, Teams embedding and Microsoft single sign-on are not implemented.

## Customer-owned hosting design

For each customer, plan a separate hosting account, application instance, database, and private document store. The customer can own the billing account and grant their IT provider access. A future production architecture should include:

- A securely configured HTTPS application endpoint accessible to approved users.
- A managed PostgreSQL database for ticket details, users, messages, and templates.
- Private object storage for original photos and PDFs.
- Separate, tested backups and restores for database and document storage.
- Secure staff device enrollment, office authentication, access logs, rate limiting and monitoring.
- Optional customer-configured email, AI extraction and QuickBooks integrations.

Those components are **not implemented by the current pilot**. The current pilot must have a persistent local disk; do not put its SQLite database or document folder on an ephemeral container filesystem. Do not run SQLite on a network share without validating its locking guarantees; Microsoft specifically advises against using Azure storage mounts for local databases such as SQLite. See [Microsoft's storage-mount guidance](https://learn.microsoft.com/en-us/azure/app-service/configure-connect-to-azure-storage?pivots=container-linux&tabs=portal).

## Teams access

The simplest future option is to share a link to the customer's FlowCapture HTTPS URL in a Teams chat or channel; it opens in a browser and still requires FlowCapture authentication. A **custom Teams app/tab** could be considered later. Teams is an access surface, not the host or database for FlowCapture.

The current pilot sends `frame-ancestors 'none'` and uses `SameSite=Strict` session cookies, so embedding it inside a Teams tab is not currently supported. A production Teams integration needs a deliberately scoped content security policy, compatible authentication and session behavior, proper Microsoft Teams app configuration, and testing in Teams desktop, browser, iPhone/iPad and Android. Do not simply remove browser security headers or expose the pilot to make it appear in Teams.

Microsoft requires Teams tab pages to use HTTPS, and mobile behavior varies by tab type. See [Teams tab requirements](https://learn.microsoft.com/en-us/microsoftteams/platform/tabs/how-to/tab-requirements) and [Teams mobile tabs](https://learn.microsoft.com/en-us/microsoftteams/platform/tabs/design/tabs-mobile).
