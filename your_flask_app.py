from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import mysql.connector
import os
import time
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your_secret_key')

def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        user=os.getenv('DB_USER', 'root'),
        password=os.getenv('DB_PASSWORD', 'Gowtham@0903'),
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
            return jsonify(error='Email, password, and user type are required'), 400

        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        if user_type == 'admin':
            # Admin login
            cursor.execute('SELECT * FROM Admins WHERE email = %s AND password = %s', (email, password))
            user = cursor.fetchone()
            redirect_url = 'register'
        else:
            # User login
            cursor.execute('SELECT * FROM Users WHERE email = %s AND password = %s', (email, password))
            user = cursor.fetchone()
            redirect_url = 'waybill_entry_form'
        
        cursor.close()
        db.close()

        if user:
            session['username'] = user['username']
            session['last_activity'] = time.time()
            session['is_admin'] = (user_type == 'admin')
            return redirect(url_for(redirect_url))
        else:
            return jsonify(error='Invalid email or password'), 400

    return render_template('login.html')

@app.route('/logout', methods=['GET'])
def logout():
    session.pop('username', None)
    session.pop('is_admin', None)
    session.pop('last_activity', None)
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
            # Check if the consignment number already exists with 'BOOKED' status
            cursor.execute('SELECT status FROM Waybills WHERE waybill_number = %s ORDER BY id DESC LIMIT 1', (waybill_number,))
            result = cursor.fetchone()

            if result:
                current_status = result[0]
                valid_statuses = ['BOOKED', 'DISPATCHED', 'RECEIVED', 'TAKEN FOR DELIVERY', 'DELIVERED', 'NOT DELIVERED', 'RETURN']
                if valid_statuses.index(status) <= valid_statuses.index(current_status):
                    return jsonify(error='Invalid status transition.'), 400
                if current_status == 'DELIVERED':
                    return jsonify(error='Cannot update status. Consignment is already delivered.'), 400

            # Insert or update the status with the current submission time
            submission_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')  # Current time in 'YYYY-MM-DD HH:MM:SS' format

            sql = '''
            INSERT INTO Waybills (date, waybill_number, booking_location, status, submission_time)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE 
                date = VALUES(date),
                booking_location = VALUES(booking_location),
                status = VALUES(status),
                submission_time = VALUES(submission_time),
                updated_at = CURRENT_TIMESTAMP
            '''
            values = (date, waybill_number, booking_location, status, submission_time)
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
