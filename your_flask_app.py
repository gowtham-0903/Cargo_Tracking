from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import mysql.connector
import os
import time
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your_secret_key')

def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv('DB_HOST', '34.93.117.53'),
        user=os.getenv('DB_USER', 'root'),
        password=os.getenv('DB_PASSWORD', 'TwedO@#0903'),
        database=os.getenv('DB_NAME', 'cargo_tracking_db')
    )

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
        user_type = request.form.get('user_type')  # Added field to distinguish between user and admin

        if not email or not password or not user_type:
            return redirect(url_for('login', error='All fields are required'))

        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        if user_type == 'admin':
            # Admin login (case-sensitive comparison)
            cursor.execute('SELECT * FROM admins WHERE BINARY email = %s AND BINARY password = %s', (email, password))
            user = cursor.fetchone()
            redirect_url = 'register'
        else:
            # User login (case-sensitive comparison)
            cursor.execute('SELECT * FROM Users WHERE BINARY email = %s AND BINARY password = %s', (email, password))
            user = cursor.fetchone()
            redirect_url = 'waybill_entry_form'
        
        cursor.close()
        db.close()

        if user:
            session['username'] = user['username']
            session['last_activity'] = time.time()
            session['is_admin'] = (user_type == 'admin')
            session['branch'] = user.get('branch')  # Store branch in session if available
            return redirect(url_for(redirect_url))
        else:
            return redirect(url_for('login', error='Invalid email or password'))

    return render_template('login.html')

@app.route('/logout', methods=['GET'])
def logout():
    session.pop('username', None)
    session.pop('is_admin', None)
    session.pop('last_activity', None)
    session.pop('branch', None)
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'is_admin' not in session or not session['is_admin']:
        return redirect(url_for('login'))

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
    date = request.form.get('date')  # Expected format: 'YYYY-MM-DD'
    waybill_numbers = request.form.get('waybillNumbers')
    status = request.form.get('status')
    booking_location = request.form.get('booking_location')  # Booking location from the form

    # Validate date format
    try:
        datetime.strptime(date, '%Y-%m-%d')
    except ValueError:
        return jsonify(error='Invalid date format'), 400

    waybill_numbers_list = [number.strip() for number in waybill_numbers.split(',')]

    # Ensure the user is logged in
    if 'username' not in session:
        return jsonify(error='User not logged in'), 401

    # Fetch the user's branch
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    if not session.get('is_admin'):
        # Fetch the user's branch if not an admin
        cursor.execute('SELECT branch FROM Users WHERE username = %s', (session['username'],))
        user = cursor.fetchone()
        if not user:
            cursor.close()
            db.close()
            return jsonify(error='User not found'), 404
        
        user_branch = user['branch']  # Set branch based on the logged-in user
    else:
        # Admins should use the booking_location provided in the form
        user_branch = booking_location

    valid_statuses = ['BOOKED', 'DISPATCHED', 'RECEIVED', 'TAKEN FOR DELIVERY', 'DELIVERED', 'NOT DELIVERED', 'RETURN']
    
    try:
        for waybill_number in waybill_numbers_list:
            cursor.execute('SELECT status FROM Waybills WHERE waybill_number = %s ORDER BY id DESC LIMIT 1', (waybill_number,))
            result = cursor.fetchone()

            if result:
                current_status = result['status']
                print(f"Current Status: {current_status}")  # Debugging output
                print(f"New Status: {status}")  # Debugging output

                if not session.get('is_admin'):
                    if valid_statuses.index(status) <= valid_statuses.index(current_status):
                        return jsonify(error='Status already updated.'), 400
                    if current_status == 'DELIVERED':
                        return jsonify(error='Cannot update status. Consignment is already delivered.'), 400

            submission_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')  # Current time in 'YYYY-MM-DD HH:MM:SS' format

            # Use user_branch for non-admin users, and booking_location for admins
            effective_branch = booking_location if session.get('is_admin') else user_branch

            sql = '''
            INSERT INTO Waybills (date, waybill_number, booking_location, status, updated_at)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE 
                date = VALUES(date),
                booking_location = VALUES(booking_location),
                status = VALUES(status),
                updated_at = VALUES(updated_at)
            '''
            values = (date, waybill_number, effective_branch, status, submission_time)
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

if __name__ == '__main__':
    app.run(debug=True)
