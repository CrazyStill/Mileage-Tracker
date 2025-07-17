import os
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, session
from database import (
    db, Trip, start_new_trip, finish_trip,
    get_started_trips, export_to_excel,
    create_prepared_trip, get_prepared_trips, delete_prepared_trip
)
from sqlalchemy import func
from functools import wraps
from datetime import timedelta



app = Flask(__name__)
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30) # Set session lifetime to 30 days

# ─── DATABASE PATH SETUP ────────────────────────────────────────────────────────
# Base directory of this script
basedir = os.path.abspath(os.path.dirname(__file__))

# Directory where we’ll keep the SQLite file
db_dir = os.getenv('DATABASE_DIR', os.path.join(basedir, 'database'))
# Create it if it doesn't exist
os.makedirs(db_dir, exist_ok=True)

# Full path to the DB file
DATABASE_PATH = os.getenv('DATABASE_PATH', os.path.join(db_dir, 'mileage_tracker.db'))
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DATABASE_PATH}'
app.config['SECRET_KEY'] = 'isasecret'
# ────────────────────────────────────────────────────────────────────────────────

db.init_app(app)
with app.app_context():
    db.create_all()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form['password'] == '2620':
            session.permanent = True
            session['logged_in'] = True
            flash('You have successfully logged in.', 'success')
            return redirect(url_for('home'))
        else:
            flash('Invalid password.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    session.pop('logged_in', None)
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))

@app.route('/')
@login_required
def home():
    return render_template('home.html')

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
    return render_template('prepare_trip.html')

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
    return render_template('new_trip.html', prepared=prepared)

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
    return render_template('finish_trip.html', trips=started_trips)

@app.route('/trips')
@login_required
def view_trips():
    prepared = get_prepared_trips()
    trips = Trip.query.order_by(Trip.id.desc()).all()
    return render_template('view_trips.html',
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
    return render_template('edit_trip.html', trip=trip)

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
    total_miles = db.session.query(func.sum(Trip.miles)).scalar() or 0
    total_revenue = db.session.query(func.sum(Trip.amount_paid)).scalar() or 0
    return render_template('totals.html', total_miles=total_miles, total_revenue=total_revenue)

@app.route('/export_data')
@login_required
def export_data():
    filenames = export_to_excel()
    if filenames:
        return send_from_directory(os.getcwd(), filenames[-1], as_attachment=True)
    flash('No completed trips to export.', 'warning')
    return redirect(url_for('home'))

@app.route('/clear_data', methods=['POST'])
@login_required
def clear_data():
    try:
        db.drop_all()
        db.create_all()
        flash('Database cleared.', 'success')
    except Exception as e:
        flash(f'Error clearing database: {e}', 'danger')
    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(host='0.0.0.0')
