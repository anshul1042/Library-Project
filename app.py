# app.py
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import qrcode
import os
from functools import wraps
from flask import g

# Add at the top of app.py
if not os.path.exists('instance'):
    os.makedirs('instance')

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///library.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['QR_CODE_FOLDER'] = 'static/qr_codes'

db = SQLAlchemy(app)

# Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    borrowed_books = db.relationship('BorrowedBook', backref='user', lazy=True)

class Shelf(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    qr_code_path = db.Column(db.String(200))
    racks = db.relationship('Rack', backref='shelf', lazy=True)

class Rack(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.Integer, nullable=False)
    shelf_id = db.Column(db.Integer, db.ForeignKey('shelf.id'), nullable=False)
    books = db.relationship('Book', backref='rack', lazy=True)

class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    author = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    rack_id = db.Column(db.Integer, db.ForeignKey('rack.id'), nullable=False)
    borrowed_records = db.relationship('BorrowedBook', backref='book', lazy=True)

class BorrowedBook(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('book.id'), nullable=False)
    borrow_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    due_date = db.Column(db.DateTime, nullable=False)
    returned = db.Column(db.Boolean, default=False)

# Login decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to access this page', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or not User.query.get(session['user_id']).is_admin:
            flash('Admin access required', 'danger')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

@app.context_processor
def utility_processor():
    def get_current_user():
        if 'user_id' in session:
            return User.query.get(session['user_id'])
        return None
    return dict(current_user=get_current_user())

# Routes
@app.route('/')
def home():
    books = Book.query.all()
    return render_template('home.html', books=books)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']  # In production, hash the password!
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'danger')
            return redirect(url_for('register'))
            
        user = User(username=username, password=password)
        db.session.add(user)
        db.session.commit()
        flash('Registration successful', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username, password=password).first()
        
        if user:
            session['user_id'] = user.id
            flash('Login successful', 'success')
            return redirect(url_for('dashboard' if user.is_admin else 'user_dashboard'))
        flash('Invalid credentials', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('Logged out successfully', 'success')
    return redirect(url_for('home'))

@app.route('/dashboard')
@admin_required
def dashboard():
    books = Book.query.all()
    shelves = Shelf.query.all()
    return render_template('dashboard.html', books=books, shelves=shelves)

@app.route('/user_dashboard')
@login_required
def user_dashboard():
    user = User.query.get(session['user_id'])
    borrowed_books = BorrowedBook.query.filter_by(user_id=user.id, returned=False).all()
    return render_template('user_dashboard.html', borrowed_books=borrowed_books)

@app.route('/add_shelf', methods=['GET', 'POST'])
@admin_required
def add_shelf():
    if request.method == 'POST':
        name = request.form['name']
        shelf = Shelf(name=name)
        db.session.add(shelf)
        db.session.commit()
        
        # Use your Render URL here
        base_url = "https://library-management-project-in5j.onrender.com"  # Replace with your actual Render URL
        shelf_url = f"{base_url}/shelf/{shelf.id}"
        
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(shelf_url)
        qr.make(fit=True)
        qr_image = qr.make_image(fill_color="black", back_color="white")
        
        # Save QR code
        if not os.path.exists(app.config['QR_CODE_FOLDER']):
            os.makedirs(app.config['QR_CODE_FOLDER'])
        
        qr_path = f'qr_codes/shelf_{shelf.id}_qr.png'
        full_path = os.path.join(app.static_folder, qr_path)
        qr_image.save(full_path)
        
        shelf.qr_code_path = qr_path
        db.session.commit()
        
        flash('Shelf added successfully', 'success')
        return redirect(url_for('dashboard'))
    return render_template('add_edit_shelf.html')

@app.route('/regenerate_shelf_qr/<int:shelf_id>')
@admin_required
def regenerate_shelf_qr(shelf_id):
    shelf = Shelf.query.get_or_404(shelf_id)
    
    # Generate new QR code with URL
    shelf_url = url_for('view_shelf', shelf_id=shelf.id, _external=True)
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(shelf_url)
    qr.make(fit=True)
    qr_image = qr.make_image(fill_color="black", back_color="white")
    
    # Save new QR code
    qr_path = f'qr_codes/shelf_{shelf.id}_qr.png'
    full_path = os.path.join(app.static_folder, qr_path)
    
    # Remove old QR code if it exists
    if shelf.qr_code_path and os.path.exists(full_path):
        os.remove(full_path)
    
    qr_image.save(full_path)
    shelf.qr_code_path = qr_path
    db.session.commit()
    
    flash('QR code regenerated successfully', 'success')
    return redirect(url_for('dashboard'))

@app.route('/borrow/<int:book_id>')
@login_required
def borrow_book(book_id):
    book = Book.query.get_or_404(book_id)
    user = User.query.get(session['user_id'])
    
    # Check if book is available
    if book.quantity <= 0:
        flash('Book not available', 'danger')
        return redirect(url_for('home'))
    
    # Check if user already has this book
    existing_borrow = BorrowedBook.query.filter_by(
        user_id=user.id,
        book_id=book.id,
        returned=False
    ).first()
    
    if existing_borrow:
        flash('You already have this book borrowed', 'warning')
        return redirect(url_for('user_dashboard'))
    
    # Create borrowed book record
    due_date = datetime.utcnow() + timedelta(days=15)
    borrowed_book = BorrowedBook(
        user_id=user.id,
        book_id=book.id,
        due_date=due_date
    )
    
    book.quantity -= 1
    db.session.add(borrowed_book)
    db.session.commit()
    
    flash(f'Book borrowed successfully. Due date: {due_date.strftime("%Y-%m-%d")}', 'success')
    return redirect(url_for('user_dashboard'))

@app.route('/return/<int:borrow_id>')
@login_required
def return_book(borrow_id):
    borrowed_book = BorrowedBook.query.get_or_404(borrow_id)
    
    if borrowed_book.user_id != session['user_id']:
        flash('Unauthorized action', 'danger')
        return redirect(url_for('user_dashboard'))
    
    borrowed_book.returned = True
    borrowed_book.book.quantity += 1
    db.session.commit()
    
    flash('Book returned successfully', 'success')
    return redirect(url_for('user_dashboard'))

@app.route('/reissue/<int:borrow_id>')
@login_required
def reissue_book(borrow_id):
    borrowed_book = BorrowedBook.query.get_or_404(borrow_id)
    
    if borrowed_book.user_id != session['user_id']:
        flash('Unauthorized action', 'danger')
        return redirect(url_for('user_dashboard'))
    
    borrowed_book.due_date = datetime.utcnow() + timedelta(days=15)
    db.session.commit()
    
    flash('Book reissued successfully', 'success')
    return redirect(url_for('user_dashboard'))

@app.route('/add_book', methods=['GET', 'POST'])
@admin_required
def add_book():
    if request.method == 'POST':
        title = request.form['title']
        author = request.form['author']
        quantity = int(request.form['quantity'])
        rack_id = int(request.form['rack_id'])
        
        book = Book(
            title=title,
            author=author,
            quantity=quantity,
            rack_id=rack_id
        )
        db.session.add(book)
        db.session.commit()
        
        flash('Book added successfully', 'success')
        return redirect(url_for('dashboard'))
    
    # Get all racks for the dropdown
    racks = Rack.query.all()
    return render_template('add_edit_book.html', racks=racks)

@app.route('/edit_book/<int:book_id>', methods=['GET', 'POST'])
@admin_required
def edit_book(book_id):
    book = Book.query.get_or_404(book_id)
    
    if request.method == 'POST':
        book.title = request.form['title']
        book.author = request.form['author']
        book.quantity = int(request.form['quantity'])
        book.rack_id = int(request.form['rack_id'])
        
        db.session.commit()
        flash('Book updated successfully', 'success')
        return redirect(url_for('dashboard'))
    
    racks = Rack.query.all()
    return render_template('add_edit_book.html', book=book, racks=racks)

@app.route('/delete_book/<int:book_id>')
@admin_required
def delete_book(book_id):
    book = Book.query.get_or_404(book_id)
    db.session.delete(book)
    db.session.commit()
    
    flash('Book deleted successfully', 'success')
    return redirect(url_for('dashboard'))

@app.route('/add_rack', methods=['GET', 'POST'])
@admin_required
def add_rack():
    if request.method == 'POST':
        number = int(request.form['number'])
        shelf_id = int(request.form['shelf_id'])
        
        rack = Rack(number=number, shelf_id=shelf_id)
        db.session.add(rack)
        db.session.commit()
        
        flash('Rack added successfully', 'success')
        return redirect(url_for('dashboard'))
    
    shelves = Shelf.query.all()
    return render_template('add_rack.html', shelves=shelves)

@app.route('/shelf/<int:shelf_id>')
def view_shelf(shelf_id):
    shelf = Shelf.query.get_or_404(shelf_id)
    return render_template('shelf_details.html', shelf=shelf)

# At the bottom of app.py, change:
if __name__ == '__main__':
    if not os.path.exists(app.config['QR_CODE_FOLDER']):
        os.makedirs(app.config['QR_CODE_FOLDER'])
    app.run(host='0.0.0.0', port=10000)  # Remove debug=True