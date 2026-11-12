# FlowCapture

FlowCapture is an early, customer-hosted pilot for capturing load tickets and delivering them to an office inbox. It is a mobile-friendly website for iPhone, iPad, Android, and desktop browsers.

Try the separate [interactive phone mockup](https://flowcapture-test-drive.mediaplusmsap.chatgpt.site). It uses sample data and simulated actions.

## Current pilot

- Sign in as Front Line Staff, Office Manager, or Admin.
- Capture a JPEG, PNG, or PDF and manually enter ticket details.
- Store the original privately and send the ticket to a shared office inbox.
- Show the submitting user only their own tickets; allow office users to review all tickets and correct ticket details, then approve a quantity and rate to **Ready**.
- Detect duplicate ticket number, vendor, and date; show client-side weight and US-ton checks.
- Search ticket history, preview a selected image before submission, download the original or a delivery-summary PDF, choose light or dark theme, and create users as an Admin.
- Admins create and share industry templates with additional text, number, and date fields; users can export and privately import template files.
- Admins generate single-use, 24-hour invitation links for staff devices and can disconnect all of a staff member’s sessions.
- Office users can reject a ticket with a reason; the submitting staff member receives an in-app notice and can provide a correction and resend it. A separate rejection history is retained after resubmission. Approval also creates an in-app notice.
- Admins can configure an office email address and use Gmail SMTP with an app password supplied in hosting secrets. A new submission can email its original attachment and a PDF summary; email status is separate from the office inbox. QuickBooks Online can be connected using customer-hosted Intuit app credentials.
- Office users send in-app messages to staff, who can acknowledge and mark them completed. Messages appear when the app is open or refreshed; the home screen checks for updates about every 30 seconds while visible. No push alerts are sent yet.

**This is an early pilot, not production-ready.** It does not yet include forgotten-password recovery, push notifications, offline upload queues, audit logs, account lockout/rate limiting, encrypted file storage, or automated backups. Gmail delivery is optional; push notifications are not implemented. A ticket is delivered when the server confirms its receipt; the visible home screen checks for new records about every 30 seconds; users can also reopen the inbox. Office staff can create a single-line invoice in a connected QuickBooks company after matching an existing customer and item.

## How to use the pilot

1. **Admin setup:** Sign in and open **Team access**. Create a Front Line Staff account and an Office Manager account. Use a unique temporary password for each user and share it through a secure channel.
2. **Capture a ticket:** Sign in as Front Line Staff, tap **Capture**, choose a JPEG, PNG, or PDF, and enter the ticket number, vendor, date, customer, and quantity. Complete the remaining fields as needed, then tap **Send to Office**. The success message appears after the server saves the record.
3. **Review in the office:** Sign in as an Office Manager or Admin. Open **Office inbox**, select a record, and download its original attachment if needed. Use **Edit ticket details** to correct a record, then enter quantity and rate and choose **Approve for QuickBooks**. Saving edits returns the ticket to Needs Review; conflicting changes are rejected so a newer edit is not silently overwritten. The app shows a calculated subtotal; after approval, office staff can select an existing QuickBooks customer and item and create an invoice. Office users can reject a ticket with a reason; it leaves the inbox, and the staff member can add a correction and resend it. Rejection history remains available in File history.
4. **Find a ticket:** Open **File history** and search by ticket number, customer, vendor, truck, PO, material, or date. Front Line Staff can see their own submissions; Office Managers and Admins can see the shared inbox. Open a ticket and select **Download delivery summary (PDF)** to save a summary; attach the original file separately if needed. The PDF is for review or manual entry, not a QuickBooks import file. Staff summaries do not include rates.
5. **Templates:** Open **Manage templates**. An Admin can create a shared template and add text, number, or date fields. Staff can import a JSON file for their own account. Select a template on the capture form; its additional fields will appear on each ticket. The standard hauling fields remain required in this pilot.
6. **Invite a staff phone:** In **Team access**, create a Front Line Staff user, choose **Create invite link**, and send it privately to that person. The link is valid once for 24 hours. To invalidate outstanding invitations and sessions, choose **Disconnect all devices**. Invitation links contain a credential: share them privately and never post them publicly.
7. **Messages:** Open **Messages & tasks**. An Office Manager or Admin can send a message to a staff user; staff can acknowledge or complete it after opening the app. This pilot does not provide phone push notifications or email notifications.
8. **Account and access:** Use **Account** to change your password. Admins can disable and re-enable users from Team access; disabling a user invalidates sessions and invitations.
9. **Change appearance:** Tap **Theme** to switch between light and dark on that browser.

## Run locally

Python 3.12 or newer is required. Install dependencies with `python -m pip install -r requirements.txt`.

1. Set `FLOWCAPTURE_ADMIN_USER` and `FLOWCAPTURE_ADMIN_PASSWORD` to create the initial Admin (password minimum 12 characters).
2. Run `python app.py`.
3. Open `http://127.0.0.1:8000` and sign in. Use **Team access** to create office and staff accounts.

The initial Admin environment settings are used only when the database is empty. Data is saved in `data/` by default; set `FLOWCAPTURE_DATA` to choose another persistent directory. Stop the server before backing up, and include **both** the SQLite database and the `files/` folder. Test restores before relying on backups.

## Optional AI extraction

AI extraction is disabled by default. A customer who chooses to enable it sets `OPENAI_API_KEY` and `FLOWCAPTURE_AI_MODEL` in the host's secret settings, restarts the service, and enables AI under **Accounting & email setup**. Select a photo or PDF and choose **Extract details with AI**. The document is sent to OpenAI and may incur charges; suggested values fill only empty fields and must be checked before submitting. Manual entry remains available. No real provider account has been tested in this pilot; PDF/image extraction, model availability, provider billing, and data-handling requirements should be verified by the customer before use.

## Optional Gmail delivery

An Admin saves the destination address under **Accounting & email setup**. Configure `FLOWCAPTURE_GMAIL_ADDRESS` and `FLOWCAPTURE_GMAIL_APP_PASSWORD` as secrets on the customer’s host, then restart the app. Do not commit the app password to GitHub. Use an app password created for the sending Google account, not the normal account password. Google requires 2-Step Verification and some account policies prevent app passwords: see [Google’s setup instructions](https://support.google.com/accounts/answer/185833).

For each new submission, the app saves the office inbox record first, then attempts to email the original file and delivery summary over Gmail SMTP. It reports `Sent`, `Failed`, or `Not configured` separately. `Sent` means Gmail accepted the message, not that the recipient read it. This pilot does not automatically retry failures, send an email on resubmission, process incoming mail, or verify Gmail connectivity before a submission. The office inbox remains the source of truth.

## QuickBooks Online setup

The customer creates an Intuit developer app with the QuickBooks Online Accounting scope, then configures these values as hosting secrets before starting FlowCapture:

- `FLOWCAPTURE_QBO_CLIENT_ID` and `FLOWCAPTURE_QBO_CLIENT_SECRET`: the Intuit app credentials.
- `FLOWCAPTURE_QBO_REDIRECT_URI`: the registered callback, for example `https://your-company.example/api/qbo/callback`. The URL must be HTTPS except on localhost.
- `FLOWCAPTURE_QBO_ENCRYPTION_KEY`: a persistent Fernet key, generated with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Store it securely and back it up separately; changing or losing it prevents decrypting the connection.
- `FLOWCAPTURE_QBO_ENV`: `sandbox` (the default) or `production`. Use the matching Intuit credentials and company for that environment.

An Admin opens **Accounting & email setup → Connect QuickBooks Online** and authorizes the company. An Office Manager or Admin approves a ticket, opens **Match and send to QuickBooks**, chooses an existing customer and item, and creates the invoice. Unknown customers and items are never created. This pilot supports one invoice line per ticket and loads up to 1,000 active customers and items. The QuickBooks invoice ID is shown in the record.

Creating the invoice is a financial transaction, not a guaranteed draft. The app requests no automatic payment or email, but company settings can affect delivery; verify them in a sandbox. If a send result is uncertain, FlowCapture blocks another send and displays **Send result uncertain**; check QuickBooks manually before taking action. The pilot has no automated reconciliation or retry. Disconnect removes the local connection; revoke access in Intuit as well. Credentials, callback, and invoice creation have only been tested with simulated responses, not with a live Intuit sandbox. Do not use this integration for live accounting until the customer has verified it.


## Container pilot

Build with `docker build -t flowcapture .`. Run with a writable persistent volume mounted at `/data`, and supply the two Admin environment variables using your hosting provider's secret settings. The process runs as UID 10001; ensure it can write to the mounted directory. `FLOWCAPTURE_SECURE_COOKIES=1` requires HTTPS, so use TLS at a trusted reverse proxy. The application listens on port 8000.

The pilot uses SQLite and local file storage. **Do not deploy it to a platform with ephemeral disk storage**, including a default stateless App Platform container: records and documents would be lost on redeploy. This pilot has not been hardened or validated for internet-facing production, and requires a protected network. Managed PostgreSQL/object storage, encrypted backups, authentication hardening, production deployment, and recovery testing are future work.

For the planned customer-hosted setup and Microsoft Teams access, see [Hosting and Teams](docs/hosting-and-teams.md).

## Tests

Run `python -m unittest discover -s tests -v` and `node --check static/app.js`.

## License

GPL-3.0; see [LICENSE](LICENSE).
