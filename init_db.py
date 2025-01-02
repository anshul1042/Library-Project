from app import app, db, User

# Create an application context
with app.app_context():
    # Create all database tables
    db.create_all()
    
    # Create admin user
    admin = User(username="admin", password="admin123", is_admin=True)
    db.session.add(admin)
    db.session.commit()