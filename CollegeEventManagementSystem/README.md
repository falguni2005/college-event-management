# College Event Management System (CEMS)

A Flask + SQLite starter application with separate student account creation/login and admin login.

## Included
- Separate Student Create Account and Student Login pages
- Separate Admin Login page; admin accounts cannot be created from public registration
- Role-based route protection
- Admin dashboard and event management (add/edit/publish/draft/cancel/delete)
- Technical / Non-Technical categories
- Department dropdown: AIDS, CS, IOT, MECH, CIVIL, ELEC, BBA, BCA, Open to All
- Event search/filtering, fee, capacity, deadline, poster upload
- Student registration, registration history, cancellation for unpaid registrations
- Payment screen responsive to device: mobile UPI handoff guidance and laptop QR presentation
- Payment status fields, unique ticket code, attendance check-in, CSV export, feedback
- Notifications, digital certificate page after attendance, basic reports
- Secure password hashing and server-side role checks

## Run on Windows
1. Install Python 3.10 or newer.
2. Extract this ZIP.
3. Open Command Prompt inside the extracted `CollegeEventManagementSystem` folder.
4. Run:
   ```bat
   py -m venv .venv
   .venv\\Scripts\\activate
   pip install -r requirements.txt
   flask --app app create-admin
   py app.py
   ```
5. Open `http://127.0.0.1:5000` in your browser.
6. Students use **Student Create Account** first, then **Student Login**.
7. Admin uses **Admin Login** with the account created by `flask --app app create-admin`.

## Important payment note
The payment page is intentionally not allowed to mark an order as paid from a browser form. Live payment collection is NOT enabled in this starter ZIP. For real UPI payments, create a merchant account with a supported payment gateway, configure its keys as environment variables, create orders on the server, verify signatures/webhooks on the server, and only then mark a registration as Paid. Never put secret keys in HTML/JavaScript or accept screenshots as proof of payment. A static QR code does not verify payment. See `PAYMENTS.md`.

## Security and deployment
- Change `SECRET_KEY` before deployment.
- Use HTTPS in production, CSRF protection, rate limiting, secure cookies, database backups, and proper authorization.
- Do not use Flask debug mode in production.
- Review privacy/consent and refund policies before collecting real student data or money.
