from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, session
from database import db, Trip, start_new_trip, finish_trip, get_started_trips, export_to_excel
from sqlalchemy import func
from functools import wraps
import os

app = Flask(__name__)

DATABASE_PATH = os.getenv('DATABASE_PATH', '/app/database/mileage_tracker.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DATABASE_PATH}'
app.config['SECRET_KEY'] = 'isasecret'  

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
        password = request.form['password']
        if password == '2620':
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

@app.route('/new_trip', methods=['GET', 'POST'])
@login_required
def new_trip():
    if request.method == 'POST':
        date = request.form['date']
        time = request.form['time']
        sport = request.form['sport']
        venue = request.form['venue']
        home_team = request.form['home_team']
        away_team = request.form['away_team']
        odometer_start = request.form['odometer_start']
        try:
            odometer_start = float(odometer_start)
            start_new_trip(date, time, sport, venue, home_team, away_team, odometer_start)
            flash('New trip started successfully.', 'success')
            return redirect(url_for('home'))
        except ValueError:
            flash('Invalid odometer reading. Please enter a numeric value.', 'danger')
    return render_template('new_trip.html')

@app.route('/finish_trip', methods=['GET', 'POST'])
@login_required
def finish_trip_route():
    if request.method == 'POST':
        trip_id = request.form['trip_id']
        Level_of_Play = request.form['Level_of_Play']
        odometer_end = request.form['odometer_end']
        amount_paid = request.form['amount_paid']
        try:
            trip_id = int(trip_id)
            odometer_end = float(odometer_end)
            amount_paid = float(amount_paid)
            finish_trip(Level_of_Play, trip_id, odometer_end, amount_paid)
            flash('Trip completed successfully.', 'success')
            return redirect(url_for('home'))
        except ValueError:
            flash('Invalid input. Please enter numeric values where required.', 'danger')
        except Exception as e:
            flash(str(e), 'danger')
    started_trips = get_started_trips()
    return render_template('finish_trip.html', trips=started_trips)

@app.route('/trips')
@login_required
def view_trips():
    trips = Trip.query.order_by(Trip.id.desc()).all()
    return render_template('view_trips.html', trips=trips)


@app.route('/edit_trip/<int:trip_id>', methods=['GET', 'POST'])
@login_required
def edit_trip(trip_id):
    trip = Trip.query.get_or_404(trip_id)
    if request.method == 'POST':
        try:
            # Update trip details from form data
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
            amount_paid = request.form.get('amount_paid')
            trip.Level_of_Play = request.form.get('Level_of_Play')
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
        latest_file = filenames[-1]
        directory = os.getcwd()
        return send_from_directory(directory, latest_file, as_attachment=True)
    else:
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
