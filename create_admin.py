from app import app, db
from models import User
from werkzeug.security import generate_password_hash
from flask import session

# Create application context
with app.app_context():
    # Check if admin already exists
    admin = User.query.filter_by(email='admin@gmail.com').first()
    
    if admin:
        print("Admin user already exists!")
    else:
        # Create admin user
        admin = User(
            username='admin',
            email='admin@gmail.com',
            password_hash=generate_password_hash('123'),
            user_type='admin'
        )
        
        # Add to database
        db.session.add(admin)
        db.session.commit()
        
        print("Admin user created successfully!")
        print("Email: admin@gmail.com")
        print("Password: 123")
        print("You can now log in using these credentials and access the admin panel.") 