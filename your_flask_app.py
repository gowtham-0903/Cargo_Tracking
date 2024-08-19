from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import mysql.connector
import os
import time

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your_secret_key')

def get_db_connection():
    connection = mysql.connector.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        user=os.getenv('DB_USER', 'root'),
        password=os.getenv('DB_PASSWORD', 'Gowtham@0903'),
        database=os.getenv('DB_NAME', 'cargo_tracking_db')
    )
    return connection

@app.route('/', methods=['GET'])
def home():
    if 'username' in session:
        return redirect(url_for('waybill_entry_form'))
    return redirect(url_for('login'))

@app.route('/waybill_entry_form', methods=['GET'])
def waybill_entry_form():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('waybill_entry.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        db = get_db_connection()
        cursor = db.cursor(dictionary=True)
        cursor.execute('SELECT * FROM Users WHERE email = %s AND password = %s', (email, password))
        user = cursor.fetchone()
        cursor.close()
        db.close()

        if user:
            session['username'] = user['username']
            session['last_activity'] = time.time()
            return redirect(url_for('waybill_entry_form'))
        else:
            return jsonify(error='Invalid email or password'), 400

    return render_template('login.html')

@app.route('/logout', methods=['GET'])
def logout():
    session.pop('username', None)
    session.pop('last_activity', None)
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        branch = request.form.get('branch')

        if not username or not email or not password or not confirm_password or not branch:
            return jsonify(error='All fields are required'), 400

        if password != confirm_password:
            return jsonify(error='Passwords do not match'), 400

        db = get_db_connection()
        cursor = db.cursor()

        try:
            # Check if email already exists
            cursor.execute('SELECT * FROM Users WHERE email = %s', (email,))
            if cursor.fetchone():
                return jsonify(error='Email already registered'), 400

            sql = 'INSERT INTO Users (username, email, password, branch) VALUES (%s, %s, %s, %s)'
            values = (username, email, password, branch)
            cursor.execute(sql, values)
            db.commit()
            return jsonify(message='Registration successful'), 201
        except mysql.connector.Error as err:
            print(f'Error registering user: {err}')
            db.rollback()
            return jsonify(error=f'Failed to register user: {err}'), 500
        finally:
            cursor.close()
            db.close()

    return render_template('register.html')

@app.route('/submit_waybill', methods=['POST'])
def submit_waybill():
    date = request.form.get('date')
    waybill_numbers = request.form.get('waybillNumbers')
    booking_location = request.form.get('booking_location')
    status = request.form.get('status')

    if not date or not waybill_numbers or not booking_location or not status:
        return jsonify(error='All fields are required'), 400

    waybill_numbers_list = [number.strip() for number in waybill_numbers.split(',')]

    db = get_db_connection()
    cursor = db.cursor()

    try:
        for waybill_number in waybill_numbers_list:
            sql = '''
            INSERT INTO Waybills (date, waybill_number, booking_location, status)
            VALUES (%s, %s, %s, %s)
            '''
            values = (date, waybill_number, booking_location, status)
            cursor.execute(sql, values)
        
        db.commit()
        return jsonify(message='Waybill(s) submitted successfully'), 200
    except mysql.connector.Error as err:
        print(f'Error submitting waybill(s): {err}')
        db.rollback()
        return jsonify(error=f'Failed to submit waybill(s): {err}'), 500
    finally:
        cursor.close()
        db.close()

@app.route('/get_locations', methods=['GET'])
def get_locations():
    try:
        db = get_db_connection()
        cursor = db.cursor()
        cursor.execute('SELECT location_name FROM Locations')
        locations = cursor.fetchall()
        return jsonify([location[0] for location in locations])
    except mysql.connector.Error as err:
        print(f'Error fetching locations: {err}')
        return jsonify(error='Failed to fetch locations'), 500
    finally:
        cursor.close()
        db.close()

@app.before_request
def before_request():
    if 'username' in session:
        if 'last_activity' in session:
            if time.time() - session['last_activity'] > 2 * 60:  # 2 minutes
                session.pop('username', None)
                session.pop('last_activity', None)
                return redirect(url_for('login'))
        session['last_activity'] = time.time()

@app.teardown_appcontext
def close_db(error):
    pass

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5002)
