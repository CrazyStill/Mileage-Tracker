import os
import calendar
from io import BytesIO
from functools import wraps
from datetime import timedelta, datetime, date

from flask import (
    Flask, render_template, request, redirect, url_for, flash,
    send_from_directory, session, send_file
)
from sqlalchemy import func

# ── Imports from your database module ──────────────────────────────────────────
from database import (
    db, Trip, start_new_trip, finish_trip,
    get_started_trips, export_to_excel,
    create_prepared_trip, get_prepared_trips, delete_prepared_trip,
    WorkDay, WorkSegment, PreparedTrip,
    archive_year, list_archived_years, get_trips_by_archived_year,
    ensure_archive_columns
)

# ── Import Blueprints ────────────────────────────────────────────────────────
from blueprints.work import work_bp

basedir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)  # 30-day session
app.config['SECRET_KEY'] = 'isasecret'

# ── Register Blueprints ────────────────────────────────────────────────────────
app.register_blueprint(work_bp)

# Ensure templates are not cached in debug mode
app.config['TEMPLATES_AUTO_RELOAD'] = True

# Set explicit template folder
app.template_folder = os.path.join(basedir, 'templates')

# ─── DATABASE PATH SETUP ──────────────────────────────────────────────────────
basedir = os.path.abspath(os.path.dirname(__file__))
db_dir = os.getenv('DATABASE_DIR', os.path.join(basedir, 'database'))
os.makedirs(db_dir, exist_ok=True)

DATABASE_PATH = os.getenv('DATABASE_PATH', os.path.join(db_dir, 'mileage_tracker.db'))
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DATABASE_PATH}'

# ── INIT DB ───────────────────────────────────────────────────────────────────
db.init_app(app)
with app.app_context():
    db.create_all()
    # Ensure the archived_year columns exist (adds column if missing)
    try:
        ensure_archive_columns(db.engine)
    except Exception:
        # non-fatal; app will continue to work but archive UI may fail
        pass

# ─── AUTH SETUP ───────────────────────────────────────────────────────────────
from auth import login_required

# ─── LOGIN / LOGOUT ───────────────────────────────────────────────────────────
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form['password'] == '2620':
            session.permanent = True
            session['logged_in'] = True
            flash('You have successfully logged in.', 'success')
            # After login, go to the Work/Officiating chooser
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid password.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    session.pop('logged_in', None)
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))

# ─── Dashboard choice (Work vs Officiating) ───────────────────────────────────
@app.route('/dashboard')
@login_required
def dashboard():
    # Template should have buttons linking to url_for('work_list') and url_for('home')
    return render_template('dashboard_choice.html')

# Treat root as Officiating home (existing behavior)
@app.route('/')
@login_required
def home():
    return render_template('officiating_home.html')

# ─── OFFICIATING ROUTES ─────────────────────────────────────────────────────
@app.route('/prepare_trip', methods=['GET', 'POST'])
@login_required
def prepare_trip():
    if request.method == 'POST':
        create_prepared_trip(
            request.form['date'],
            request.form['time'],
            request.form['sport'],
            request.form['venue'],
            request.form['home_team'],
            request.form['away_team']
        )
        flash('Trip prepared successfully.', 'success')
        return redirect(url_for('home'))
    return render_template('officiating_prepare_trip.html')

@app.route('/new_trip', methods=['GET', 'POST'])
@login_required
def new_trip():
    prepared = get_prepared_trips()
    if request.method == 'POST':
        if request.form.get('prepared_id'):
            pid = int(request.form['prepared_id'])
            od_start = float(request.form['odometer_start'])
            prep = next((p for p in prepared if p.id == pid), None)
            if not prep:
                flash('Prepared trip not found.', 'danger')
            else:
                start_new_trip(
                    prep.date, prep.time, prep.sport,
                    prep.venue, prep.home_team, prep.away_team,
                    od_start
                )
                delete_prepared_trip(pid)
                flash('Prepared trip started.', 'success')
        else:
            try:
                start_new_trip(
                    request.form['date'], request.form['time'],
                    request.form['sport'], request.form['venue'],
                    request.form['home_team'], request.form['away_team'],
                    float(request.form['odometer_start'])
                )
                flash('New trip started successfully.', 'success')
            except ValueError:
                flash('Invalid odometer reading. Please enter a numeric value.', 'danger')
        return redirect(url_for('home'))
    return render_template('officiating_new_trip.html', prepared=prepared)

@app.route('/finish_trip', methods=['GET', 'POST'])
@login_required
def finish_trip_route():
    if request.method == 'POST':
        try:
            finish_trip(
                request.form['Level_of_Play'],
                int(request.form['trip_id']),
                float(request.form['odometer_end']),
                float(request.form['amount_paid'])
            )
            flash('Trip completed successfully.', 'success')
            return redirect(url_for('home'))
        except ValueError:
            flash('Invalid input. Please check your entries.', 'danger')
        except Exception as e:
            flash(str(e), 'danger')
    started_trips = get_started_trips()
    return render_template('officiating_finish_trip.html', trips=started_trips)

@app.route('/trips')
@login_required
def view_trips():
    prepared = get_prepared_trips()
    # show only non-archived trips in the main view
    trips = Trip.query.filter(Trip.archived_year == None).order_by(Trip.id.desc()).all()
    return render_template('officiating_view_trips.html',
                           prepared_trips=prepared,
                           trips=trips)

@app.route('/delete_prepared_trip/<int:prep_id>', methods=['POST'])
@login_required
def delete_prepared_trip_route(prep_id):
    delete_prepared_trip(prep_id)
    flash('Prepared trip removed.', 'success')
    return redirect(url_for('view_trips'))


@app.route('/edit_trip/<int:trip_id>', methods=['GET', 'POST'])
@login_required
def edit_trip(trip_id):
    trip = Trip.query.get_or_404(trip_id)
    if request.method == 'POST':
        try:
            trip.date = request.form['date']
            trip.time = request.form['time']
            trip.sport = request.form['sport']
            trip.venue = request.form['venue']
            trip.home_team = request.form['home_team']
            trip.away_team = request.form['away_team']
            trip.odometer_start = float(request.form['odometer_start'])
            odometer_end = request.form.get('odometer_end')
            trip.odometer_end = float(odometer_end) if odometer_end else None
            miles = request.form.get('miles')
            trip.miles = float(miles) if miles else None
            trip.Level_of_Play = request.form.get('Level_of_Play')
            amount_paid = request.form.get('amount_paid')
            trip.amount_paid = float(amount_paid) if amount_paid else None
            trip.status = request.form['status']
            db.session.commit()
            flash('Trip updated successfully.', 'success')
            return redirect(url_for('view_trips'))
        except ValueError:
            flash('Invalid input. Please enter numeric values where required.', 'danger')
    return render_template('officiating_edit_trip.html', trip=trip)

# --- DELETE TRIP ROUTE ---
@app.route('/delete_trip/<int:trip_id>', methods=['POST'])
@login_required
def delete_trip(trip_id):
    trip = Trip.query.get_or_404(trip_id)
    db.session.delete(trip)
    db.session.commit()
    flash('Trip deleted successfully.', 'success')
    return redirect(url_for('view_trips'))

@app.route('/totals')
@login_required
def view_totals():
    total_miles = db.session.query(func.sum(Trip.miles)).filter(Trip.archived_year == None).scalar() or 0
    total_revenue = db.session.query(func.sum(Trip.amount_paid)).filter(Trip.archived_year == None).scalar() or 0
    return render_template('officiating_totals.html', total_miles=total_miles, total_revenue=total_revenue)

@app.route('/export_data')
@login_required
def export_data():
    year = request.args.get('year')
    if year:
        try:
            y = int(year)
        except ValueError:
            flash('Invalid year.', 'danger')
            return redirect(url_for('home'))
        filenames = export_to_excel(y)
    else:
        filenames = export_to_excel()
    if filenames:
        return send_from_directory(os.getcwd(), filenames[-1], as_attachment=True)
    flash('No completed trips to export.', 'warning')
    return redirect(url_for('home'))

@app.route('/clear_data', methods=['POST'])
@login_required
def clear_data():
    # Repurpose clear_data to archive a year if provided via form.
    year = request.form.get('year')
    if not year:
        flash('No year provided. Use the Archive page to archive a year.', 'warning')
        return redirect(url_for('archive'))
    try:
        y = int(year)
    except ValueError:
        flash('Invalid year provided.', 'danger')
        return redirect(url_for('archive'))
    try:
        archive_year(y)
        flash(f'Year {y} archived. Current view now shows active year only.', 'success')
    except Exception as e:
        flash(f'Error archiving year: {e}', 'danger')
    return redirect(url_for('home'))


@app.route('/archive', methods=['GET', 'POST'])
@login_required
def archive():
    if request.method == 'POST':
        year = request.form.get('year')
        try:
            y = int(year)
        except Exception:
            flash('Please enter a valid year (e.g. 2024).', 'danger')
            return redirect(url_for('archive'))
        try:
            archive_year(y)
            flash(f'Year {y} archived successfully.', 'success')
            return redirect(url_for('home'))
        except Exception as e:
            flash(f'Error archiving year: {e}', 'danger')
            return redirect(url_for('archive'))
    years = list_archived_years()
    return render_template('archive.html', archived_years=years)


@app.route('/archived')
@login_required
def archived_index():
    years = list_archived_years()
    return render_template('archived_index.html', archived_years=years)


@app.route('/archived/<int:year>')
@login_required
def archived_year_view(year):
    trips = get_trips_by_archived_year(year)
    return render_template('archived_year.html', year=year, trips=trips)

# ──────────────────────────────────────────────────────────────────────────────
# ── TRIPS ────────────────────────────────────────────────────────────────────────

# ─── RUN ───────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    app.run(host='0.0.0.0')
