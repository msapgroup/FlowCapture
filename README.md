# FlowCapture

FlowCapture is an early, customer-hosted pilot for capturing load tickets and delivering them to an office inbox. It is a mobile-friendly website for iPhone, iPad, Android, and desktop browsers.

## Current pilot

- Sign in as Front Line Staff, Office Manager, or Admin.
- Capture a JPEG, PNG, or PDF and manually enter ticket details.
- Store the original privately and send the ticket to a shared office inbox.
- Show the submitting user only their own tickets; allow office users to review all tickets and approve a quantity and rate to **Ready**.
- Detect duplicate ticket number, vendor, and date; show client-side weight and US-ton checks.
- Search ticket history, download the original, choose light or dark theme, and create users as an Admin.

**This is an early pilot, not production-ready.** It does not yet include AI/OCR, Gmail, QuickBooks, password reset, staff invitation links, push notifications, template management, offline upload queues, audit logs, account lockout/rate limiting, encrypted file storage, or automated backups. The office does not receive an email or push notification. A ticket is delivered when the server confirms its receipt; users must reopen or refresh their inbox to see new records. Accounting transactions are not created.

## How to use the pilot

1. **Admin setup:** Sign in and open **Team access**. Create a Front Line Staff account and an Office Manager account. Use a unique temporary password for each user and share it through a secure channel.
2. **Capture a ticket:** Sign in as Front Line Staff, tap **Capture**, choose a JPEG, PNG, or PDF, and enter the ticket number, vendor, date, customer, and quantity. Complete the remaining fields as needed, then tap **Send to Office**. The success message appears after the server saves the record.
3. **Review in the office:** Sign in as an Office Manager or Admin. Open **Office inbox**, select a record, and download its original attachment if needed. Enter quantity and rate, then choose **Approve to Ready**. The app shows a calculated subtotal; QuickBooks sending is not implemented yet.
4. **Find a ticket:** Open **File history** and search by ticket number, customer, vendor, truck, PO, material, or date. Front Line Staff can see their own submissions; Office Managers and Admins can see the shared inbox.
5. **Change appearance:** Tap **Theme** to switch between light and dark on that browser.

## Run locally

Python 3.12 or newer is required. No Python packages are needed.

1. Set `FLOWCAPTURE_ADMIN_USER` and `FLOWCAPTURE_ADMIN_PASSWORD` to create the initial Admin (password minimum 12 characters).
2. Run `python app.py`.
3. Open `http://127.0.0.1:8000` and sign in. Use **Team access** to create office and staff accounts.

The initial Admin environment settings are used only when the database is empty. Data is saved in `data/` by default; set `FLOWCAPTURE_DATA` to choose another persistent directory. Stop the server before backing up, and include **both** the SQLite database and the `files/` folder. Test restores before relying on backups.

## Container pilot

Build with `docker build -t flowcapture .`. Run with a writable persistent volume mounted at `/data`, and supply the two Admin environment variables using your hosting provider's secret settings. The process runs as UID 10001; ensure it can write to the mounted directory. `FLOWCAPTURE_SECURE_COOKIES=1` requires HTTPS, so use TLS at a trusted reverse proxy. The application listens on port 8000.

The pilot uses SQLite and local file storage. **Do not deploy it to a platform with ephemeral disk storage**, including a default stateless App Platform container: records and documents would be lost on redeploy. This pilot has not been hardened or validated for internet-facing production, and requires a protected network. Managed PostgreSQL/object storage, encrypted backups, authentication hardening, production deployment, and recovery testing are future work.

## Tests

Run `python -m unittest discover -s tests -v` and `node --check static/app.js`.

## License

GPL-3.0; see [LICENSE](LICENSE).
