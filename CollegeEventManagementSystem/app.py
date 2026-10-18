import os, io, csv, secrets, json, base64
from datetime import datetime, date
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, abort, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy
import qrcode

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-development-secret")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///cems.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = os.path.join("static", "uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
db = SQLAlchemy(app)

DEPARTMENTS = ["AIDS", "CS", "IOT", "MECH", "CIVIL", "ELEC", "BBA", "BCA", "Open to All"]
CATEGORIES = ["Technical", "Non-Technical"]
EVENT_TYPES = ["Individual", "Team"]

def generate_qr_base64(data_str):
    """Generate high quality QR code as a base64 PNG data string."""
    try:
        qr = qrcode.QRCode(version=1, box_size=8, border=2)
        qr.add_data(data_str)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#0b2545", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception as e:
        print("QR generation error:", e)
        return ""

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(180), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    department = db.Column(db.String(40), default="")
    role = db.Column(db.String(20), default="student")  # student/admin/organizer
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    category = db.Column(db.String(30), nullable=False)  # Technical, Non-Technical
    department = db.Column(db.String(40), nullable=False)  # Arranging Department
    event_type = db.Column(db.String(20), default="Individual")  # Individual, Team
    min_team_size = db.Column(db.Integer, default=1)
    max_team_size = db.Column(db.Integer, default=1)
    event_date = db.Column(db.String(20), nullable=False)
    event_time = db.Column(db.String(30), default="")
    venue = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text, default="")
    deadline = db.Column(db.String(20), default="")
    fee = db.Column(db.Float, default=0)
    capacity = db.Column(db.Integer, default=100)
    poster = db.Column(db.String(255), default="")
    status = db.Column(db.String(20), default="Published")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def is_team_event(self):
        return self.event_type == "Team"

    @property
    def confirmed_count(self):
        return Registration.query.filter_by(event_id=self.id).count()

    @property
    def seats_left(self):
        return max(0, self.capacity - self.confirmed_count)

class Registration(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey("event.id"), nullable=False)
    participation_type = db.Column(db.String(20), default="Individual")
    team_name = db.Column(db.String(120), default="")
    team_size = db.Column(db.Integer, default=1)
    team_members = db.Column(db.Text, default="")  # JSON array string
    phone = db.Column(db.String(30), default="")
    status = db.Column(db.String(30), default="Confirmed")
    payment_status = db.Column(db.String(30), default="Pending")
    payment_reference = db.Column(db.String(120), default="")
    ticket_code = db.Column(db.String(32), unique=True, default=lambda: secrets.token_hex(6).upper())
    attended = db.Column(db.Boolean, default=False)
    feedback_rating = db.Column(db.Integer, nullable=True)
    feedback = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship("User")
    event = db.relationship("Event")
    __table_args__ = (db.UniqueConstraint("user_id", "event_id", name="unique_user_event"),)

    def parsed_members(self):
        """Returns parsed list of team member dictionaries."""
        if not self.team_members:
            return []
        try:
            items = json.loads(self.team_members)
            return items if isinstance(items, list) else []
        except Exception:
            return []

class Notice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    message = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    read = db.Column(db.Boolean, default=False)

def login_required(role=None):
    def decorator(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if not session.get("user_id"):
                flash("Please log in to continue.", "warning")
                return redirect(url_for("student_login" if role != "admin" else "admin_login"))
            if role and session.get("role") != role:
                abort(403)
            return fn(*args, **kwargs)
        return wrapped
    return decorator

def current_user():
    return db.session.get(User, session.get("user_id")) if session.get("user_id") else None

@app.context_processor
def inject_globals():
    return {
        "current_user": current_user(),
        "departments": DEPARTMENTS,
        "categories": CATEGORIES,
        "event_types": EVENT_TYPES
    }

@app.route("/")
def index():
    events = Event.query.filter_by(status="Published").order_by(Event.event_date).all()
    return render_template("index.html", events=events)

@app.route("/student/register", methods=["GET", "POST"])
def student_register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        department = request.form.get("department", "")
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if not name or not email or department not in DEPARTMENTS[:-1] or len(password) < 8:
            flash("Complete all fields. Password must contain at least 8 characters.", "danger")
        elif password != confirm:
            flash("Passwords do not match.", "danger")
        elif User.query.filter_by(email=email).first():
            flash("An account with this email already exists.", "danger")
        else:
            user = User(name=name, email=email, department=department,
                        password_hash=generate_password_hash(password), role="student")
            db.session.add(user)
            db.session.commit()
            flash("Student account created successfully. Please log in.", "success")
            return redirect(url_for("student_login"))
    return render_template("student_register.html")

@app.route("/student/login", methods=["GET", "POST"])
def student_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email, role="student").first()
        if user and check_password_hash(user.password_hash, password):
            session.clear()
            session["user_id"] = user.id
            session["role"] = "student"
            return redirect(url_for("student_dashboard"))
        flash("Invalid student email or password.", "danger")
    return render_template("student_login.html")

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email, role="admin").first()
        if user and check_password_hash(user.password_hash, password):
            session.clear()
            session["user_id"] = user.id
            session["role"] = "admin"
            return redirect(url_for("admin_dashboard"))
        flash("Invalid admin credentials.", "danger")
    return render_template("admin_login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have logged out.", "info")
    return redirect(url_for("index"))

@app.route("/student/dashboard")
@login_required("student")
def student_dashboard():
    user = current_user()
    regs = Registration.query.filter_by(user_id=user.id).order_by(Registration.created_at.desc()).all()
    notices = Notice.query.filter((Notice.user_id == user.id) | (Notice.user_id.is_(None))).order_by(Notice.created_at.desc()).limit(10).all()
    events = Event.query.filter_by(status="Published").order_by(Event.event_date).all()

    # Calculate interactive dashboard stats
    stats = {
        "total_registered": len(regs),
        "confirmed": len([r for r in regs if r.status in ["Confirmed", "Paid"] or r.payment_status in ["Paid", "Not Required"]]),
        "attended": len([r for r in regs if r.attended]),
        "certificates": len([r for r in regs if r.attended]),
        "pending_pay": len([r for r in regs if r.event.fee > 0 and r.payment_status not in ["Paid", "Not Required"]])
    }

    # Find next upcoming registered event
    today_str = date.today().isoformat()
    upcoming_regs = [r for r in regs if r.event.event_date >= today_str]
    upcoming_regs.sort(key=lambda r: (r.event.event_date, r.event.event_time or ""))
    next_reg = upcoming_regs[0] if upcoming_regs else None

    # Pre-generate QR data mapping for quick modal view
    qr_map = {}
    for r in regs:
        qr_map[r.id] = generate_qr_base64(r.ticket_code)

    return render_template("student_dashboard.html",
                           user=user,
                           regs=regs,
                           events=events,
                           notices=notices,
                           stats=stats,
                           next_reg=next_reg,
                           qr_map=qr_map)

@app.route("/events")
def browse_events():
    category = request.args.get("category", "")
    department = request.args.get("department", "")
    event_type = request.args.get("event_type", "")
    search = request.args.get("q", "").strip()

    query = Event.query.filter_by(status="Published")
    if category in CATEGORIES:
        query = query.filter_by(category=category)
    if department and department in DEPARTMENTS:
        # Any student can register, this filters by ARRANGING department
        query = query.filter_by(department=department)
    if event_type in EVENT_TYPES:
        query = query.filter_by(event_type=event_type)
    if search:
        query = query.filter((Event.title.ilike(f"%{search}%")) | (Event.description.ilike(f"%{search}%")) | (Event.venue.ilike(f"%{search}%")))

    events = query.order_by(Event.event_date).all()
    return render_template("events.html", events=events,
                           selected_category=category,
                           selected_department=department,
                           selected_type=event_type,
                           search=search)

@app.route("/event/<int:event_id>")
def event_detail(event_id):
    event = db.get_or_404(Event, event_id)
    registration = None
    if session.get("role") == "student":
        registration = Registration.query.filter_by(user_id=session["user_id"], event_id=event.id).first()
    return render_template("event_detail.html", event=event, registration=registration)

@app.route("/event/<int:event_id>/register", methods=["GET", "POST"])
@login_required("student")
def register_event(event_id):
    event = db.get_or_404(Event, event_id)
    user = current_user()

    # Check if already registered
    existing_reg = Registration.query.filter_by(user_id=user.id, event_id=event.id).first()
    if existing_reg:
        flash("You are already registered for this event. View your pass below.", "info")
        return redirect(url_for("view_ticket", registration_id=existing_reg.id))

    if event.status != "Published":
        flash("This event is currently not open for registration.", "danger")
        return redirect(url_for("event_detail", event_id=event.id))

    if event.deadline and event.deadline < date.today().isoformat():
        flash("The registration deadline for this event has passed.", "danger")
        return redirect(url_for("event_detail", event_id=event.id))

    if Registration.query.filter_by(event_id=event.id).count() >= event.capacity:
        flash("Sorry, this event is already full.", "warning")
        return redirect(url_for("event_detail", event_id=event.id))

    if request.method == "GET":
        return render_template("register_event.html", event=event, user=user)

    # POST - Process Registration
    phone = request.form.get("phone", "").strip()
    notes = request.form.get("notes", "").strip()

    participation_type = event.event_type or "Individual"
    team_name = ""
    team_size = 1
    team_members_json = ""

    if event.is_team_event:
        team_name = request.form.get("team_name", "").strip()
        if not team_name:
            flash("Please enter a Team Name for your team.", "danger")
            return render_template("register_event.html", event=event, user=user)

        member_names = request.form.getlist("member_name[]")
        member_depts = request.form.getlist("member_dept[]")
        member_emails = request.form.getlist("member_email[]")
        member_rolls = request.form.getlist("member_roll[]")

        # Member 1 is the leader (current user)
        roster = [{
            "name": user.name,
            "department": user.department,
            "email": user.email,
            "roll": request.form.get("leader_roll", "").strip() or "Leader",
            "phone": phone,
            "role": "Team Leader"
        }]

        # Add additional members
        for idx in range(len(member_names)):
            m_name = member_names[idx].strip()
            if m_name:
                m_dept = member_depts[idx].strip() if idx < len(member_depts) else user.department
                m_email = member_emails[idx].strip() if idx < len(member_emails) else ""
                m_roll = member_rolls[idx].strip() if idx < len(member_rolls) else ""
                roster.append({
                    "name": m_name,
                    "department": m_dept,
                    "email": m_email,
                    "roll": m_roll,
                    "role": f"Member {len(roster) + 1}"
                })

        team_size = len(roster)
        if team_size < (event.min_team_size or 2):
            flash(f"Your team must have at least {event.min_team_size or 2} members (including leader). Current: {team_size}.", "danger")
            return render_template("register_event.html", event=event, user=user)

        if event.max_team_size and team_size > event.max_team_size:
            flash(f"Team size exceeds maximum allowed of {event.max_team_size} members.", "danger")
            return render_template("register_event.html", event=event, user=user)

        team_members_json = json.dumps(roster)
        participation_type = "Team"

    is_free = (event.fee == 0)
    reg = Registration(
        user_id=user.id,
        event_id=event.id,
        participation_type=participation_type,
        team_name=team_name,
        team_size=team_size,
        team_members=team_members_json,
        phone=phone,
        status="Confirmed" if is_free else "Pending Payment",
        payment_status="Not Required" if is_free else "Pending"
    )
    db.session.add(reg)
    db.session.flush()

    db.session.add(Notice(
        user_id=user.id,
        message=f"Registration submitted for {event.title} (Ticket: {reg.ticket_code})."
    ))
    db.session.commit()

    if not is_free:
        flash("Registration details saved! Please complete payment to confirm your seat.", "info")
        return redirect(url_for("payment", registration_id=reg.id))

    flash(f"Registration successful for {event.title}! Here is your digital ticket.", "success")
    return redirect(url_for("view_ticket", registration_id=reg.id))

@app.route("/ticket/<int:registration_id>")
@login_required()
def view_ticket(registration_id):
    reg = db.get_or_404(Registration, registration_id)
    # Only owner student or admin can view ticket
    if session.get("role") != "admin" and reg.user_id != session.get("user_id"):
        abort(403)

    qr_base64 = generate_qr_base64(reg.ticket_code)
    return render_template("ticket.html", reg=reg, qr_base64=qr_base64)

@app.route("/payment/<int:registration_id>", methods=["GET", "POST"])
@login_required("student")
def payment(registration_id):
    reg = db.get_or_404(Registration, registration_id)
    if reg.user_id != session["user_id"]:
        abort(403)
    if reg.payment_status == "Paid":
        return redirect(url_for("view_ticket", registration_id=reg.id))

    # Generate real UPI string and QR code
    upi_pa = "cems@sbi"
    upi_pn = "College Events"
    upi_url = f"upi://pay?pa={upi_pa}&pn={upi_pn}&am={reg.event.fee:.2f}&cu=INR&tn={reg.ticket_code}"
    qr_base64 = generate_qr_base64(upi_url)

    if request.method == "POST":
        action = request.form.get("action", "")
        if action == "instant_pay":
            # Instant demo payment for hassle-free evaluation
            reg.payment_status = "Paid"
            reg.status = "Confirmed"
            reg.payment_reference = f"UPI-DEMO-{secrets.token_hex(4).upper()}"
            db.session.commit()
            db.session.add(Notice(user_id=reg.user_id, message=f"Payment received for {reg.event.title}. Entry confirmed!"))
            db.session.commit()
            flash("Demo payment verified successfully! Your entry pass is activated.", "success")
            return redirect(url_for("view_ticket", registration_id=reg.id))

        ref = request.form.get("payment_reference", "").strip()
        if ref:
            reg.payment_reference = ref
            reg.payment_status = "Pending Verification"
            reg.status = "Confirmed (Under Verification)"
            db.session.commit()
            flash(f"Payment reference #{ref} submitted! Admin will verify and activate your pass shortly.", "success")
            return redirect(url_for("view_ticket", registration_id=reg.id))
        else:
            flash("Please enter your 12-digit UPI UTR number or use Instant Demo Pay.", "warning")

    return render_template("payment.html", reg=reg, qr_base64=qr_base64, upi_url=upi_url, upi_pa=upi_pa)

@app.route("/student/cancel/<int:registration_id>", methods=["POST"])
@login_required("student")
def cancel_registration(registration_id):
    reg = db.get_or_404(Registration, registration_id)
    if reg.user_id != session["user_id"]:
        abort(403)
    if reg.payment_status != "Paid":
        event_title = reg.event.title
        db.session.delete(reg)
        db.session.commit()
        flash(f"Registration for {event_title} has been cancelled.", "success")
    else:
        flash("Paid registrations require administrator review for cancellation.", "warning")
    return redirect(url_for("student_dashboard"))

@app.route("/admin")
@login_required("admin")
def admin_dashboard():
    event_count = Event.query.count()
    student_count = User.query.filter_by(role="student").count()
    registration_count = Registration.query.count()
    paid_total = db.session.query(db.func.sum(Event.fee)).join(Registration, Event.id==Registration.event_id).filter(Registration.payment_status=="Paid").scalar() or 0
    attended_count = Registration.query.filter_by(attended=True).count()

    dept_counts = {}
    for r in Registration.query.all():
        d = r.user.department or "General"
        dept_counts[d] = dept_counts.get(d, 0) + 1

    team_count = Registration.query.filter_by(participation_type="Team").count()
    solo_count = Registration.query.filter_by(participation_type="Individual").count()

    return render_template("admin_dashboard.html",
        event_count=event_count,
        student_count=student_count,
        registration_count=registration_count,
        paid_total=paid_total,
        attended_count=attended_count,
        dept_counts=dept_counts,
        team_count=team_count,
        solo_count=solo_count,
        events=Event.query.order_by(Event.created_at.desc()).limit(8).all(),
        registrations=Registration.query.order_by(Registration.created_at.desc()).limit(12).all())

@app.route("/admin/events")
@login_required("admin")
def admin_events():
    return render_template("admin_events.html", events=Event.query.order_by(Event.created_at.desc()).all())

@app.route("/admin/events/add", methods=["GET", "POST"])
@app.route("/admin/events/<int:event_id>/edit", methods=["GET", "POST"])
@login_required("admin")
def admin_event_form(event_id=None):
    event = db.get_or_404(Event, event_id) if event_id else None
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        category = request.form.get("category", "")
        department = request.form.get("department", "")
        event_type = request.form.get("event_type", "Individual")
        min_team = request.form.get("min_team_size", "1")
        max_team = request.form.get("max_team_size", "1")
        fee = request.form.get("fee", "0")
        capacity = request.form.get("capacity", "100")

        if not title or category not in CATEGORIES or department not in DEPARTMENTS or not request.form.get("event_date") or not request.form.get("venue", "").strip():
            flash("Please complete all required fields.", "danger")
            return render_template("admin_event_form.html", event=event)

        try:
            fee_value = max(0.0, float(fee))
            capacity_value = max(1, int(capacity))
            min_team_val = max(1, int(min_team)) if event_type == "Team" else 1
            max_team_val = max(min_team_val, int(max_team)) if event_type == "Team" else 1
        except ValueError:
            flash("Numeric fields (Fee, Capacity, Team Size) must contain valid numbers.", "danger")
            return render_template("admin_event_form.html", event=event)

        if not event:
            event = Event()

        event.title = title
        event.category = category
        event.department = department
        event.event_type = event_type
        event.min_team_size = min_team_val
        event.max_team_size = max_team_val
        event.event_date = request.form["event_date"]
        event.event_time = request.form.get("event_time", "")
        event.venue = request.form["venue"].strip()
        event.description = request.form.get("description", "").strip()
        event.deadline = request.form.get("deadline", "")
        event.fee = fee_value
        event.capacity = capacity_value
        event.status = request.form.get("status", "Published") if request.form.get("status") in ["Published", "Draft", "Cancelled"] else "Draft"

        uploaded = request.files.get("poster")
        if uploaded and uploaded.filename:
            filename = secure_filename(uploaded.filename)
            if filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                unique = f"{secrets.token_hex(6)}_{filename}"
                uploaded.save(os.path.join(app.config["UPLOAD_FOLDER"], unique))
                event.poster = unique

        db.session.add(event)
        db.session.commit()
        flash("Event saved successfully.", "success")
        return redirect(url_for("admin_events"))

    return render_template("admin_event_form.html", event=event)

@app.route("/admin/events/<int:event_id>/delete", methods=["POST"])
@login_required("admin")
def admin_event_delete(event_id):
    event = db.get_or_404(Event, event_id)
    if Registration.query.filter_by(event_id=event.id).count():
        event.status = "Cancelled"
        flash("Event has registrations, so it was marked Cancelled instead of deleting.", "warning")
    else:
        db.session.delete(event)
        flash("Event deleted successfully.", "success")
    db.session.commit()
    return redirect(url_for("admin_events"))

@app.route("/admin/registrations")
@login_required("admin")
def admin_registrations():
    regs = Registration.query.order_by(Registration.created_at.desc()).all()
    return render_template("admin_registrations.html", regs=regs)

@app.route("/admin/registration/<int:registration_id>/mark-paid", methods=["POST"])
@login_required("admin")
def admin_mark_paid(registration_id):
    reg = db.get_or_404(Registration, registration_id)
    reg.payment_status = "Paid"
    reg.status = "Confirmed"
    db.session.commit()
    flash(f"Payment approved for {reg.user.name} ({reg.event.title}).", "success")
    return redirect(url_for("admin_registrations"))

@app.route("/admin/registration/<int:registration_id>/toggle-attendance", methods=["POST"])
@login_required("admin")
def admin_toggle_attendance(registration_id):
    reg = db.get_or_404(Registration, registration_id)
    reg.attended = not reg.attended
    db.session.commit()
    state = "Checked in" if reg.attended else "Unchecked"
    flash(f"Attendance status changed to '{state}' for {reg.user.name}.", "info")
    return redirect(url_for("admin_registrations"))

@app.route("/admin/attendance", methods=["GET", "POST"])
@login_required("admin")
def admin_attendance():
    result = None
    if request.method == "POST":
        code = request.form.get("ticket_code", "").strip().upper()
        result = Registration.query.filter_by(ticket_code=code).first()
        if result:
            if result.payment_status not in ["Paid", "Not Required"] and result.event.fee > 0:
                flash(f"Payment is not verified for this ticket ({result.payment_status}).", "danger")
            elif result.attended:
                flash("Notice: This ticket has already been checked in.", "warning")
            else:
                result.attended = True
                db.session.commit()
                flash(f"Attendance marked successfully for {result.user.name}!", "success")
        else:
            flash("Ticket code not found. Please verify the code and try again.", "danger")
    return render_template("admin_attendance.html", result=result)

@app.route("/admin/registrations.csv")
@login_required("admin")
def export_registrations():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Student / Leader", "Student Dept", "Email", "Phone",
        "Event Title", "Arranging Dept", "Category", "Event Type",
        "Team Name", "Team Size", "Team Members Roster",
        "Fee", "Payment Status", "Payment Ref", "Ticket Code", "Attended", "Registered At"
    ])
    for r in Registration.query.order_by(Registration.created_at.desc()).all():
        members_summary = "; ".join([f"{m.get('name')} ({m.get('dept', '')})" for m in r.parsed_members()]) if r.parsed_members() else ""
        writer.writerow([
            r.user.name, r.user.department, r.user.email, r.phone,
            r.event.title, r.event.department, r.event.category, r.participation_type,
            r.team_name, r.team_size, members_summary,
            r.event.fee, r.payment_status, r.payment_reference, r.ticket_code, r.attended,
            r.created_at.strftime("%Y-%m-%d %H:%M")
        ])
    mem = io.BytesIO(output.getvalue().encode("utf-8-sig"))
    mem.seek(0)
    return send_file(mem, mimetype="text/csv", as_attachment=True, download_name="cems_all_registrations.csv")

@app.route("/student/feedback/<int:registration_id>", methods=["POST"])
@login_required("student")
def feedback(registration_id):
    reg = db.get_or_404(Registration, registration_id)
    if reg.user_id != session["user_id"]:
        abort(403)
    try:
        rating = int(request.form.get("rating", "5"))
    except ValueError:
        rating = 5
    reg.feedback_rating = min(5, max(1, rating))
    reg.feedback = request.form.get("feedback", "").strip()[:1000]
    db.session.commit()
    flash("Thank you for your feedback!", "success")
    return redirect(url_for("student_dashboard"))

@app.route("/student/certificate/<int:registration_id>")
@login_required()
def certificate(registration_id):
    reg = db.get_or_404(Registration, registration_id)
    if session.get("role") != "admin" and reg.user_id != session.get("user_id"):
        abort(403)
    if not reg.attended and session.get("role") != "admin":
        flash("Certificate is available only after attendance check-in is complete at the event.", "warning")
        return redirect(url_for("student_dashboard"))

    verify_url = request.host_url.rstrip("/") + url_for("verify_certificate", ticket_code=reg.ticket_code)
    cert_qr = generate_qr_base64(verify_url)
    return render_template("certificate.html", reg=reg, cert_qr=cert_qr, verify_url=verify_url)

@app.route("/verify-certificate/<string:ticket_code>")
def verify_certificate(ticket_code):
    reg = Registration.query.filter_by(ticket_code=ticket_code.strip().upper()).first()
    return render_template("verify_certificate.html", reg=reg, ticket_code=ticket_code.strip().upper())

@app.cli.command("create-admin")
def create_admin():
    """Create administrator account: flask --app app create-admin"""
    import getpass
    email = input("Admin email: ").strip().lower()
    name = input("Admin name: ").strip() or "Administrator"
    password = getpass.getpass("Admin password (min 8 chars): ")
    if len(password) < 8:
        print("Password must be at least 8 characters.")
        return
    if User.query.filter_by(email=email).first():
        print("That email already exists.")
        return
    db.session.add(User(name=name, email=email, password_hash=generate_password_hash(password), role="admin"))
    db.session.commit()
    print("Admin account created. Use the separate Admin Login page.")

def seed_database():
    """Seeds default admin and at least 12 rich events if needed."""
    with app.app_context():
        db.create_all()

        # Seed Admin
        admin = User.query.filter_by(role="admin").first()
        if not admin:
            admin = User(name="College Administrator", email="admin@college.edu",
                         password_hash=generate_password_hash("admin1234"), role="admin")
            db.session.add(admin)
            db.session.commit()
            print("Default admin created: admin@college.edu / admin1234")

        # Seed Events if count is less than 10
        if Event.query.count() < 10:
            sample_events = [
                Event(
                    title="HackSphere 2026: 36-Hour National AI Hackathon",
                    category="Technical",
                    department="CS",
                    event_type="Team",
                    min_team_size=2,
                    max_team_size=4,
                    event_date="2026-11-15",
                    event_time="09:00 AM - 09:00 PM (Next Day)",
                    venue="Central Computing & Innovation Hub",
                    description="Annual flagship 36-hour hackathon. Build scalable solutions in Generative AI, Web3, Smart Cities, or Healthcare. Open to all branches! Cash prizes up to ₹1,00,000, industry mentorship, and fast-track interview opportunities.",
                    deadline="2026-11-12",
                    fee=200.0,
                    capacity=250,
                    status="Published"
                ),
                Event(
                    title="DataVortex: GenAI & Predictive Modeling Summit",
                    category="Technical",
                    department="AIDS",
                    event_type="Individual",
                    min_team_size=1,
                    max_team_size=1,
                    event_date="2026-11-18",
                    event_time="10:00 AM - 04:00 PM",
                    venue="Turing Auditorium, AI Block",
                    description="Intensive data science and deep learning contest. Participants will build, fine-tune, and evaluate LLMs and predictive pipelines on live real-world datasets within 6 hours. High-end GPU workstations provided.",
                    deadline="2026-11-16",
                    fee=100.0,
                    capacity=150,
                    status="Published"
                ),
                Event(
                    title="SmartCity IoT & Embedded Systems Expo",
                    category="Technical",
                    department="IOT",
                    event_type="Team",
                    min_team_size=2,
                    max_team_size=3,
                    event_date="2026-11-22",
                    event_time="10:00 AM - 05:00 PM",
                    venue="IoT Center of Excellence, Room 402",
                    description="Showcase and prototype connected smart hardware using ESP32, Raspberry Pi, and sensor arrays. Prototype smart traffic, energy grids, or environmental monitoring systems with real-time dashboards.",
                    deadline="2026-11-20",
                    fee=150.0,
                    capacity=120,
                    status="Published"
                ),
                Event(
                    title="RoboWars: Steel Gladiators Combat Arena",
                    category="Technical",
                    department="MECH",
                    event_type="Team",
                    min_team_size=3,
                    max_team_size=5,
                    event_date="2026-11-25",
                    event_time="11:00 AM - 06:00 PM",
                    venue="Open Workshop Battle Arena",
                    description="The ultimate bot combat showdown! Custom 15kg/30kg wired or wireless combat robots battle in an enclosed steel arena with hazards, flippers, and spinners. Pit your engineering against the best in the state.",
                    deadline="2026-11-22",
                    fee=300.0,
                    capacity=200,
                    status="Published"
                ),
                Event(
                    title="Bridge-O-Mania: Truss Structural Design Challenge",
                    category="Technical",
                    department="CIVIL",
                    event_type="Team",
                    min_team_size=2,
                    max_team_size=4,
                    event_date="2026-11-28",
                    event_time="09:30 AM - 02:30 PM",
                    venue="Civil Engineering Structures Lab",
                    description="Design and construct load-bearing bridge models using balsa wood and popsicles within tight geometric constraints. All bridges will be tested to destruction on the hydraulic load cell! Certificates for maximum load-to-weight ratio.",
                    deadline="2026-11-26",
                    fee=0.0,
                    capacity=100,
                    status="Published"
                ),
                Event(
                    title="Circuitron: Reverse Engineering & PCB Debugging",
                    category="Technical",
                    department="ELEC",
                    event_type="Team",
                    min_team_size=2,
                    max_team_size=3,
                    event_date="2026-12-02",
                    event_time="10:30 AM - 03:30 PM",
                    venue="Microcontroller & Circuit Design Lab",
                    description="Hands-on circuit analysis sprint. Diagnose faults on analog/digital PCBs, solder fixes, and reprogram STM32 microcontrollers to complete the mission against the clock.",
                    deadline="2026-11-30",
                    fee=100.0,
                    capacity=90,
                    status="Published"
                ),
                Event(
                    title="BizIgnite: Shark Tank & Venture Pitching Arena",
                    category="Non-Technical",
                    department="BBA",
                    event_type="Team",
                    min_team_size=2,
                    max_team_size=4,
                    event_date="2026-12-05",
                    event_time="10:00 AM - 04:00 PM",
                    venue="Management Development Center Auditorium",
                    description="Pitch your startup idea to actual angel investors and venture capitalists! Submit executive summaries, pitch decks, and financial projections for seed grants and incubation support.",
                    deadline="2026-12-02",
                    fee=150.0,
                    capacity=160,
                    status="Published"
                ),
                Event(
                    title="WebCrafters: 4-Hour Speed UI/UX & Frontend Sprint",
                    category="Technical",
                    department="BCA",
                    event_type="Individual",
                    min_team_size=1,
                    max_team_size=1,
                    event_date="2026-12-08",
                    event_time="01:00 PM - 05:00 PM",
                    venue="Digital Media & Software Lab 2",
                    description="Speed design and frontend challenge. Transform an unexpected prompt into a stunning, responsive, interactive web application within 4 hours using HTML, CSS, JavaScript or modern frameworks.",
                    deadline="2026-12-06",
                    fee=0.0,
                    capacity=120,
                    status="Published"
                ),
                Event(
                    title="Symphony 2026: Inter-Collegiate Battle of Bands & Group Dance",
                    category="Non-Technical",
                    department="Open to All",
                    event_type="Team",
                    min_team_size=4,
                    max_team_size=10,
                    event_date="2026-12-12",
                    event_time="04:00 PM - 10:00 PM",
                    venue="Grand Open Air Amphitheatre",
                    description="The premier cultural celebration of acoustic bands, western group dance, and classical fusion. Huge stage, dynamic light shows, celebrity judges, and mega trophy awards.",
                    deadline="2026-12-10",
                    fee=0.0,
                    capacity=1000,
                    status="Published"
                ),
                Event(
                    title="Clash of Titans: Inter-Department E-Sports Championship",
                    category="Non-Technical",
                    department="Open to All",
                    event_type="Team",
                    min_team_size=4,
                    max_team_size=5,
                    event_date="2026-12-15",
                    event_time="10:00 AM - 08:00 PM",
                    venue="Indoor Esports Arena & Streaming Studio",
                    description="Inter-department competitive gaming showdown in Valorant (5v5) and BGMI (Squads). Custom LAN servers, professional casters, live YouTube streaming, and prizes.",
                    deadline="2026-12-13",
                    fee=250.0,
                    capacity=300,
                    status="Published"
                ),
                Event(
                    title="CodeCombat: 1v1 Rapid Algorithmic Duel",
                    category="Technical",
                    department="CS",
                    event_type="Individual",
                    min_team_size=1,
                    max_team_size=1,
                    event_date="2026-12-18",
                    event_time="02:00 PM - 05:00 PM",
                    venue="Central Computing Lab 4",
                    description="Fast-paced 1v1 knockout coding tournament testing dynamic programming, graph algorithms, and data structure speed. Live leaderboard projection and spot rewards.",
                    deadline="2026-12-16",
                    fee=0.0,
                    capacity=150,
                    status="Published"
                ),
                Event(
                    title="Ad-Venture: Creative Marketing & Brand Spoof",
                    category="Non-Technical",
                    department="BBA",
                    event_type="Team",
                    min_team_size=2,
                    max_team_size=4,
                    event_date="2026-12-20",
                    event_time="11:00 AM - 03:00 PM",
                    venue="BBA Seminar Hall B",
                    description="Test your creative marketing wit! Teams receive a wacky fictional product and have 60 minutes to script, act, and pitch an hilarious yet compelling 3-minute advertisement in front of the audience.",
                    deadline="2026-12-18",
                    fee=0.0,
                    capacity=100,
                    status="Published"
                )
            ]
            for ev in sample_events:
                # Avoid duplicate title
                if not Event.query.filter_by(title=ev.title).first():
                    db.session.add(ev)
            db.session.commit()
            print("12+ Diverse events across departments successfully seeded.")

# Run seeding on startup
seed_database()

if __name__ == "__main__":
    app.run(debug=True)
