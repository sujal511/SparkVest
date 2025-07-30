from flask import render_template, redirect, url_for, flash, request, session, jsonify
from app import app, db, mail, Message, google
from models import User, Project, Investment, TeamMember, Comment, CommentLike
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import os
from werkzeug.utils import secure_filename
from functools import wraps
import razorpay
import json
import uuid
import random
import string
from fpdf import FPDF

UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Initialize Razorpay client
razorpay_client = razorpay.Client(auth=("rzp_test_key", "rzp_test_secret"))

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Helper decorators
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.')
            return redirect(url_for('login'))
        
        user = User.query.get(session['user_id'])
        if user.user_type != 'admin':
            flash('You do not have permission to access this page.')
            return redirect(url_for('dashboard'))
            
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    # Get featured projects for the homepage
    featured_projects = Project.query.filter_by(status='approved').limit(4).all()
    return render_template('index.html', projects=featured_projects)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        phone_number = request.form.get('phone_number')
        password = request.form.get('password')
        user_type = request.form.get('user_type', 'investor')
        
        # Check if user already exists
        user_exists = User.query.filter_by(username=username).first() or User.query.filter_by(email=email).first()
        
        if user_exists:
            flash('Username or email already exists!', 'error')
            return redirect(url_for('register'))
        
        # Create new user
        new_user = User(
            username=username,
            email=email,
            phone_number=phone_number,
            password_hash=generate_password_hash(password),
            user_type=user_type,
            is_verified=False
        )
        
        try:
            db.session.add(new_user)
            db.session.commit()
            
            # Generate OTP
            otp = ''.join(random.choices(string.digits, k=6))
            session['registration_otp'] = otp
            session['user_email'] = email
            session['user_id'] = new_user.id
            
            # Send OTP via email
            send_otp_email(email, otp)
            
            return redirect(url_for('verify_otp', email=email))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred during registration. Please try again.', 'error')
            return redirect(url_for('register'))
            
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        
        # First check if email and password are correct
        if user and check_password_hash(user.password_hash, password):
            # Then check if user is verified
            if not user.is_verified:
                flash('Please verify your email address to continue.', 'error')
                
                # Generate new OTP
                otp = ''.join(random.choices(string.digits, k=6))
                session['registration_otp'] = otp
                session['user_email'] = email
                session['user_id'] = user.id
                
                # Send OTP via email
                send_otp_email(email, otp)
                
                # Redirect to OTP verification with login flag
                return redirect(url_for('verify_otp', email=email, login_after_verify=True))
            
            # If verified, proceed with login
            session['user_id'] = user.id
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        
        flash('Invalid email or password.', 'error')
        return redirect(url_for('login'))
            
    return render_template('login.html')

@app.route('/login/google')
def login_google():
    redirect_uri = url_for('authorize_google', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route('/authorize/google') # This is the callback URI registered with Google
def authorize_google():
    try:
        token = google.authorize_access_token()
    except Exception as e:
        app.logger.error(f"Error authorizing access token: {e}")
        flash('Error authorizing with Google. Please try again.', 'error')
        return redirect(url_for('login'))

    if token is None:
        flash('Access denied by Google or an error occurred.', 'error')
        return redirect(url_for('login'))

    try:
        user_info = google.parse_id_token(token, nonce=None) # Using parse_id_token for OpenID Connect
        # If you need more profile info not in id_token, you might use: user_info = google.get('userinfo', token=token).json()
    except Exception as e:
        app.logger.error(f"Error fetching user info from Google: {e}")
        flash('Error fetching your information from Google. Please try again.', 'error')
        return redirect(url_for('login'))

    google_user_id = user_info.get('sub') # Standard OpenID field for user ID
    email = user_info.get('email')
    # name = user_info.get('name')
    # picture = user_info.get('picture')

    if not email:
        flash('Could not retrieve email from Google. Please ensure your Google account has an email.', 'error')
        return redirect(url_for('login'))

    user = User.query.filter_by(email=email).first()

    if user:
        # User exists, log them in
        if not user.is_verified: # Verify if somehow they were not verified before
            user.is_verified = True
            db.session.commit()
        session['user_id'] = user.id
        flash('Successfully logged in with Google!', 'success')
        return redirect(url_for('dashboard'))
    else:
        # New user, create an account
        # Generate a username (e.g., from email or make unique)
        username_base = email.split('@')[0]
        username = username_base
        counter = 1
        while User.query.filter_by(username=username).first():
            username = f"{username_base}{counter}"
            counter += 1

        # Generate a secure random password as a placeholder (not used for OAuth login)
        placeholder_password = ''.join(random.choices(string.ascii_letters + string.digits + string.punctuation, k=16))
        
        new_user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(placeholder_password),
            is_verified=True, # Verified by Google
            user_type='investor' # Default user type, can be changed later or made selectable
            # phone_number can be added later by the user
        )
        db.session.add(new_user)
        try:
            db.session.commit()
            session['user_id'] = new_user.id
            flash('Account created and logged in with Google!', 'success')
            return redirect(url_for('dashboard'))
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error creating Google user: {e}")
            flash('Error creating your account. Please try again.', 'error')
            return redirect(url_for('register'))

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('You have been logged out.')
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    user = User.query.get(session['user_id'])
    
    # If user is admin, redirect to admin dashboard
    if user.user_type == 'admin':
        return redirect(url_for('admin_dashboard'))
    
    user_projects = Project.query.filter_by(user_id=user.id).all()
    user_investments = Investment.query.filter_by(user_id=user.id).all()
    
    # Redirect to appropriate dashboard based on user type
    if user.user_type == 'idea_owner':
        return render_template('idea_owner_dashboard.html', user=user, projects=user_projects, investments=user_investments)
    else:  # investor
        # Get featured and trending projects for investor dashboard
        featured_projects = Project.query.filter(Project.user_id != user.id, Project.status == 'approved').order_by(Project.current_amount.desc()).limit(3).all()
        trending_projects = Project.query.filter(Project.user_id != user.id, Project.status == 'approved').order_by(Project.created_at.desc()).limit(4).all()
        return render_template('investor_dashboard.html', user=user, investments=user_investments, featured_projects=featured_projects, trending_projects=trending_projects)

@app.route('/browse-ideas')
@login_required
def browse_ideas():
    user = User.query.get(session['user_id'])
    
    # Get query parameters
    search = request.args.get('search', '')
    category = request.args.get('category', '')
    sort_by = request.args.get('sort', 'newest')
    
    # Base query: don't show user's own projects and only show approved projects
    query = Project.query.filter(Project.user_id != user.id, Project.status == 'approved')
    
    # Apply search if provided
    if search:
        query = query.filter(Project.title.ilike(f'%{search}%') | Project.description.ilike(f'%{search}%'))
    
    # Apply category filter if provided
    if category:
        query = query.filter(Project.category == category)
    
    # Apply sorting
    if sort_by == 'newest':
        query = query.order_by(Project.created_at.desc())
    elif sort_by == 'popular':
        query = query.order_by(Project.current_amount.desc())
    elif sort_by == 'ending-soon':
        query = query.order_by(Project.end_date.asc())
    elif sort_by == 'most-funded':
        query = query.order_by(Project.progress_percentage.desc())
    elif sort_by == 'least-funded':
        query = query.order_by(Project.progress_percentage.asc())
        
    projects = query.all()
    
    return render_template('browse_ideas.html', user=user, projects=projects)

@app.route('/submit-idea', methods=['GET', 'POST'])
@login_required
def submit_idea():
    user = User.query.get(session['user_id'])
    
    # Check if user is an idea owner
    if user.user_type != 'idea_owner':
        flash('Only idea owners can submit ideas.')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        title = request.form.get('title')
        short_description = request.form.get('short_description')
        description = request.form.get('description')
        category = request.form.get('category')
        goal_amount = request.form.get('goal_amount')
        duration_days = request.form.get('duration')  # Field name in form is 'duration'
        market_opportunity = request.form.get('market_opportunity')
        use_of_funds = request.form.get('use_of_funds')
        return_type = request.form.get('return_type', 'reward')
        stake_terms = request.form.get('stake_terms') if return_type == 'stake' else None
        video_url = request.form.get('video_url')  # Get YouTube video URL
        
        # Check for required fields only
        if not title or not description or not goal_amount or not duration_days or not market_opportunity or not use_of_funds:
            flash('Please fill in all required fields.')
            return redirect(url_for('submit_idea'))
            
        # If return type is stake, check for stake terms
        if return_type == 'stake' and not stake_terms:
            flash('Please provide stake terms for equity-based funding.')
            return redirect(url_for('submit_idea'))
            
        # Process main image if uploaded
        image_url = None
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                # Create uploads directory if it doesn't exist
                if not os.path.exists(app.config['UPLOAD_FOLDER']):
                    os.makedirs(app.config['UPLOAD_FOLDER'])
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                image_url = '/' + file_path
        
        # Process additional images if uploaded
        additional_images = []
        if 'additional_images' in request.files:
            files = request.files.getlist('additional_images')
            for file in files:
                if file and file.filename and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(file_path)
                    additional_images.append('/' + file_path)
        
        # Process research report - now required
        research_report_url = None
        if 'research_report' in request.files:
            file = request.files['research_report']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                research_report_url = '/' + file_path
        
        # Check if research report was uploaded
        if not research_report_url:
            flash('Please upload a research report.')
            return redirect(url_for('submit_idea'))
        
        # Create new project
        end_date = datetime.utcnow() + timedelta(days=int(duration_days))
        
        new_project = Project(
            title=title,
            description=description,
            short_description=short_description,
            category=category,
            goal=float(goal_amount),
            current_amount=0,
            end_date=end_date,
            user_id=user.id,
            image_url=image_url,
            additional_images=','.join(additional_images) if additional_images else None,  # Store as comma-separated string
            video_url=video_url,
            research_report_url=research_report_url,
            market_opportunity=market_opportunity,
            use_of_funds=use_of_funds,
            return_type=return_type,
            stake_terms=stake_terms,
            status='pending'  # All new projects start as pending
        )
        
        try:
            db.session.add(new_project)
            db.session.commit()  # Commit to get the project ID
            
            # Process registered team members from the hidden input field
            registered_members_value = request.form.get('registered_team_members', '')
            if registered_members_value:
                registered_member_ids = [id.strip() for id in registered_members_value.split(',') if id.strip()]
                
                for member_id in registered_member_ids:
                    # Get the role if provided
                    role_field_name = f'team_member_role_{member_id}'
                    role = request.form.get(role_field_name, '')
                    
                    team_member = TeamMember(
                        project_id=new_project.id,
                        user_id=int(member_id),
                        role=role
                    )
                    db.session.add(team_member)
            
            # Process custom team members
            if 'team_member_names[]' in request.form:
                names = request.form.getlist('team_member_names[]')
                roles = request.form.getlist('team_member_roles[]')
                linkedin_profiles = request.form.getlist('team_member_linkedin[]')
                
                for i in range(len(names)):
                    if names[i]:  # Only add if name is provided
                        role = roles[i] if i < len(roles) else ''
                        linkedin = linkedin_profiles[i] if i < len(linkedin_profiles) else ''
                        
                        team_member = TeamMember(
                            project_id=new_project.id,
                            name=names[i],
                            role=role,
                            linkedin_profile=linkedin
                        )
                        db.session.add(team_member)
            
            db.session.commit()
            flash('Your idea has been submitted and is pending admin approval.')
            return redirect(url_for('dashboard'))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while submitting your idea. Please try again.')
            return redirect(url_for('submit_idea'))
    
    # For GET request, fetch all users to populate the team members dropdown
    all_users = User.query.filter(User.id != user.id).all()
    return render_template('submit_idea.html', user=user, all_users=all_users)

@app.route('/project/<int:project_id>')
@login_required
def project_detail(project_id):
    # Redirect to the correct URL pattern
    return redirect(url_for('view_project', project_id=project_id))

@app.route('/projects/<int:project_id>')
@login_required
def view_project(project_id):
    user = User.query.get(session['user_id'])
    project = Project.query.get_or_404(project_id)
    
    # Check if project is approved or if user is the owner or an admin
    if project.status != 'approved' and project.user_id != user.id and user.user_type != 'admin':
        flash('This project is not available for viewing.')
        return redirect(url_for('dashboard'))
    
    # Check if user has already invested in this project
    user_investment = Investment.query.filter_by(user_id=user.id, project_id=project.id).first()
    
    # Get all top-level comments for this project (no parent)
    comments = Comment.query.filter_by(
        project_id=project.id, 
        parent_id=None
    ).order_by(Comment.created_at.desc()).all()
    
    # For each comment, check if the current user has liked it
    for comment in comments:
        comment.user_liked = CommentLike.query.filter_by(
            user_id=user.id,
            comment_id=comment.id
        ).first() is not None
        
        # Also check for replies and if user liked them
        for reply in comment.replies:
            reply.user_liked = CommentLike.query.filter_by(
                user_id=user.id,
                comment_id=reply.id
            ).first() is not None
    
    return render_template('project_details.html', 
                          user=user, 
                          project=project, 
                          user_investment=user_investment,
                          comments=comments)

@app.route('/projects/<int:project_id>/invest', methods=['GET', 'POST'])
@login_required
def invest(project_id):
    user = User.query.get(session['user_id'])
    
    # Check if user is an investor
    if user.user_type != 'investor':
        flash('Only investors can invest in ideas.')
        return redirect(url_for('dashboard'))
    
    project = Project.query.get_or_404(project_id)
    
    # Check if project is approved
    if project.status != 'approved':
        flash('This project is not available for investment.')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        amount = request.form.get('amount')
        
        if not amount:
            flash('Please enter an investment amount.')
            return redirect(url_for('invest', project_id=project.id))
            
        try:
            amount = float(amount)
            
            # Create Razorpay order
            order_amount = int(amount * 100)  # Convert to paisa (smallest currency unit)
            order_currency = 'INR'
            order_receipt = f'receipt_{project.id}_{user.id}_{uuid.uuid4().hex[:8]}'
            
            payment_data = {
                'amount': order_amount,
                'currency': order_currency,
                'receipt': order_receipt,
                'notes': {
                    'project_id': project.id,
                    'user_id': user.id,
                    'project_title': project.title
                }
            }
            
            # Create Razorpay Order
            razorpay_order = razorpay_client.order.create(data=payment_data)
            
            # Store order details in session for verification after payment
            session['razorpay_order_id'] = razorpay_order['id']
            session['project_id'] = project.id
            session['investment_amount'] = amount
            
            # Render payment page with Razorpay details
            return render_template(
                'payment.html',
                user=user,
                project=project,
                amount=amount,
                razorpay_order_id=razorpay_order['id'],
                razorpay_merchant_key="rzp_test_key",
                callback_url=url_for('payment_callback', _external=True)
            )
            
        except ValueError:
            flash('Please enter a valid amount.')
            return redirect(url_for('invest', project_id=project.id))
        except Exception as e:
            flash(f'An error occurred while processing your payment: {str(e)}')
            return redirect(url_for('invest', project_id=project.id))
    
    return render_template('invest.html', user=user, project=project)

@app.route('/invest/<int:project_id>', methods=['GET', 'POST'])
@login_required
def invest_alternative(project_id):
    # Redirect to the canonical URL
    return redirect(url_for('invest', project_id=project_id))

@app.route('/payment/callback', methods=['POST'])
@login_required
def payment_callback():
    user = User.query.get(session['user_id'])
    
    # Get payment verification data
    razorpay_payment_id = request.form.get('razorpay_payment_id')
    razorpay_order_id = request.form.get('razorpay_order_id')
    razorpay_signature = request.form.get('razorpay_signature')
    
    # Get stored order details from session
    order_id = session.get('razorpay_order_id')
    project_id = session.get('project_id')
    amount = session.get('investment_amount')
    
    # Clear session data
    session.pop('razorpay_order_id', None)
    session.pop('project_id', None)
    session.pop('investment_amount', None)
    
    if not all([razorpay_payment_id, razorpay_order_id, razorpay_signature, order_id, project_id, amount]):
        flash('Invalid payment data. Please try again.')
        return redirect(url_for('dashboard'))
    
    # Verify payment signature
    try:
        razorpay_client.utility.verify_payment_signature({
            'razorpay_order_id': razorpay_order_id,
            'razorpay_payment_id': razorpay_payment_id,
            'razorpay_signature': razorpay_signature
        })
        
        # Get project
        project = Project.query.get_or_404(project_id)
        
        # Generate certificate if it's a stake project
        certificate_url = None
        if project.return_type == 'stake':
            certificate_url = generate_stake_certificate(user, project, amount)
        
        # Create investment record
        new_investment = Investment(
            amount=amount,
            user_id=user.id,
            project_id=project.id,
            certificate_url=certificate_url
        )
        
        # Update project's current amount
        project.current_amount += amount
        
        db.session.add(new_investment)
        db.session.commit()
        
        flash(f'You have successfully invested ₹{amount:.2f} in {project.title}!')
        
        if certificate_url:
            flash(f'Your stake certificate has been generated and is available for download.')
            
        return redirect(url_for('view_project', project_id=project.id))
        
    except Exception as e:
        flash(f'Payment verification failed: {str(e)}')
        return redirect(url_for('dashboard'))

def generate_stake_certificate(user, project, amount):
    """Generate a PDF certificate for stake investments"""
    # Create certificates directory if it doesn't exist
    certificates_dir = os.path.join(app.static_folder, 'certificates')
    if not os.path.exists(certificates_dir):
        os.makedirs(certificates_dir)
    
    # Calculate stake percentage based on investment amount and project goal
    stake_percentage = (amount / project.goal) * 100
    
    # Generate a unique filename
    filename = f"stake_certificate_{project.id}_{user.id}_{uuid.uuid4().hex[:8]}.pdf"
    filepath = os.path.join(certificates_dir, filename)
    
    # Create PDF
    pdf = FPDF()
    pdf.add_page()
    
    # Header
    pdf.set_font('Arial', 'B', 16)
    pdf.cell(190, 10, 'EQUITY STAKE CERTIFICATE', 0, 1, 'C')
    pdf.set_font('Arial', '', 12)
    pdf.cell(190, 10, 'SparkVest Platform', 0, 1, 'C')
    pdf.line(10, 30, 200, 30)
    pdf.ln(10)
    
    # Certificate details
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(190, 10, 'CERTIFICATE OF EQUITY STAKE', 0, 1, 'C')
    pdf.set_font('Arial', '', 10)
    pdf.cell(190, 10, f'Certificate Number: SC-{project.id}-{user.id}-{uuid.uuid4().hex[:6]}', 0, 1, 'C')
    pdf.cell(190, 10, f'Issue Date: {datetime.utcnow().strftime("%d %B %Y")}', 0, 1, 'C')
    pdf.ln(10)
    
    # Project and investor details
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(190, 10, 'This certificate confirms that:', 0, 1)
    pdf.set_font('Arial', '', 12)
    pdf.cell(190, 10, f'Investor: {user.username} ({user.email})', 0, 1)
    pdf.cell(190, 10, f'Has invested ₹{amount:.2f} in:', 0, 1)
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(190, 10, f'{project.title}', 0, 1)
    pdf.set_font('Arial', '', 10)
    pdf.multi_cell(190, 10, f'Description: {project.short_description}', 0)
    pdf.ln(5)
    
    # Stake details
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(190, 10, 'Equity Stake Details:', 0, 1)
    pdf.set_font('Arial', '', 10)
    pdf.cell(190, 10, f'Investment Amount: ₹{amount:.2f}', 0, 1)
    pdf.cell(190, 10, f'Project Valuation: ₹{project.goal:.2f}', 0, 1)
    pdf.cell(190, 10, f'Equity Stake: {stake_percentage:.2f}%', 0, 1)
    pdf.ln(5)
    
    # Terms and conditions
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(190, 10, 'Terms and Conditions:', 0, 1)
    pdf.set_font('Arial', '', 9)
    pdf.multi_cell(190, 10, project.stake_terms or 'Standard equity terms apply as per platform regulations.', 0)
    pdf.ln(10)
    
    # Signatures
    pdf.set_font('Arial', 'I', 10)
    pdf.cell(95, 10, 'Platform Representative', 0, 0, 'C')
    pdf.cell(95, 10, 'Project Owner', 0, 1, 'C')
    pdf.cell(95, 20, '', 'B', 0, 'C')
    pdf.cell(95, 20, '', 'B', 1, 'C')
    pdf.ln(10)
    
    # Footer
    pdf.set_font('Arial', 'I', 8)
    pdf.cell(190, 10, 'This certificate serves as proof of equity stake in the project and is subject to all applicable securities regulations.', 0, 1, 'C')
    pdf.cell(190, 10, f'Generated on {datetime.utcnow().strftime("%d %B %Y at %H:%M:%S")} - SparkVest Platform', 0, 1, 'C')
    
    # Save PDF
    pdf.output(filepath)
    
    # Return the relative path to be stored in the database
    return f'/static/certificates/{filename}'

@app.route('/explore')
def explore():
    # Only show approved projects to the public
    projects = Project.query.filter_by(status='approved').all()
    return render_template('explore.html', projects=projects)

@app.route('/how-it-works')
def how_it_works():
    return render_template('howitswork.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/privacy-policy')
def privacy_policy():
    return render_template('privacy_policy.html')

@app.route('/terms-and-conditions')
def terms_and_conditions():
    return render_template('terms_and_conditions.html')

# New search endpoint for team members
@app.route('/search-users', methods=['GET'])
@login_required
def search_users():
    search_query = request.args.get('q', '').strip()
    
    if not search_query or len(search_query) < 2:
        return jsonify({'users': []})
    
    # Search for users by username or email, excluding the current user
    current_user_id = session.get('user_id')
    users = User.query.filter(
        User.id != current_user_id,  # Exclude current user
        (User.username.ilike(f'%{search_query}%') | User.email.ilike(f'%{search_query}%'))
    ).limit(10).all()
    
    # Convert users to JSON-serializable format
    users_data = [
        {
            'id': user.id,
            'username': user.username,
            'email': user.email
        }
        for user in users
    ]
    
    return jsonify({'users': users_data})

# Comments and Community Section Routes
@app.route('/projects/<int:project_id>/comments', methods=['GET', 'POST'])
@login_required
def project_comments(project_id):
    user = User.query.get(session['user_id'])
    project = Project.query.get_or_404(project_id)
    
    if request.method == 'POST':
        content = request.form.get('content')
        if content:
            comment = Comment(
                content=content,
                user_id=user.id,
                project_id=project_id
            )
            db.session.add(comment)
            db.session.commit()
            flash('Comment posted successfully')
            
    # Always redirect back to the project page to show the comments
    return redirect(url_for('view_project', project_id=project_id))

@app.route('/comments/<int:comment_id>/reply', methods=['POST'])
@login_required
def reply_to_comment(comment_id):
    user = User.query.get(session['user_id'])
    parent_comment = Comment.query.get_or_404(comment_id)
    
    content = request.form.get('content')
    if content:
        reply = Comment(
            content=content,
            user_id=user.id,
            project_id=parent_comment.project_id,
            parent_id=comment_id
        )
        db.session.add(reply)
        db.session.commit()
        flash('Reply posted successfully')
    
    return redirect(url_for('view_project', project_id=parent_comment.project_id))

@app.route('/comments/<int:comment_id>/like', methods=['POST'])
@login_required
def like_comment(comment_id):
    user = User.query.get(session['user_id'])
    comment = Comment.query.get_or_404(comment_id)
    
    # Check if user already liked this comment
    existing_like = CommentLike.query.filter_by(
        user_id=user.id, 
        comment_id=comment_id
    ).first()
    
    if existing_like:
        # User already liked, so unlike
        db.session.delete(existing_like)
        db.session.commit()
        return jsonify({'liked': False, 'count': comment.like_count})
    else:
        # User hasn't liked, so add like
        like = CommentLike(
            user_id=user.id,
            comment_id=comment_id
        )
        db.session.add(like)
        db.session.commit()
        return jsonify({'liked': True, 'count': comment.like_count})

@app.route('/comments/<int:comment_id>/delete', methods=['POST'])
@login_required
def delete_comment(comment_id):
    user = User.query.get(session['user_id'])
    comment = Comment.query.get_or_404(comment_id)
    
    # Only allow comment deletion if the user is the comment author or an admin
    if comment.user_id == user.id or user.user_type == 'admin':
        project_id = comment.project_id
        db.session.delete(comment)
        db.session.commit()
        flash('Comment deleted successfully')
        return redirect(url_for('view_project', project_id=project_id))
    else:
        flash('You do not have permission to delete this comment')
        return redirect(url_for('view_project', project_id=comment.project_id))

# Admin Routes
@app.route('/admin')
@admin_required
def admin_dashboard():
    user = User.query.get(session['user_id'])
    
    # Get stats for dashboard
    total_users = User.query.count()
    pending_projects = Project.query.filter_by(status='pending').count()
    approved_projects = Project.query.filter_by(status='approved').count()
    total_investments = Investment.query.count()
    total_amount = db.session.query(db.func.sum(Investment.amount)).scalar() or 0
    
    # Get pending projects for review
    pending_projects_list = Project.query.filter_by(status='pending').order_by(Project.created_at.desc()).limit(5).all()
    
    # Get recent users
    recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
    
    stats = {
        'total_users': total_users,
        'pending_projects': pending_projects,
        'approved_projects': approved_projects,
        'total_investments': total_investments,
        'total_amount': total_amount
    }
    
    return render_template('admin_dashboard.html', 
                          user=user, 
                          stats=stats, 
                          pending_projects=pending_projects_list, 
                          recent_users=recent_users)

@app.route('/admin/projects')
@admin_required
def admin_projects():
    user = User.query.get(session['user_id'])
    
    # Get filter parameters
    status = request.args.get('status', '')
    search = request.args.get('search', '')
    category = request.args.get('category', '')
    
    # Build query
    query = Project.query
    
    if status:
        query = query.filter(Project.status == status)
    
    if search:
        query = query.filter(Project.title.ilike(f'%{search}%') | Project.description.ilike(f'%{search}%'))
    
    if category:
        query = query.filter(Project.category == category)
    
    # Sort by newest first by default
    projects = query.order_by(Project.created_at.desc()).all()
    
    return render_template('admin_projects.html', user=user, projects=projects, filter_status=status)

@app.route('/admin/projects/<int:project_id>')
@admin_required
def admin_review_project(project_id):
    user = User.query.get(session['user_id'])
    project = Project.query.get_or_404(project_id)
    
    # Fetch team members for this project
    team_members = TeamMember.query.filter_by(project_id=project_id).all()
    
    return render_template('admin_project_review.html', user=user, project=project, team_members=team_members)

@app.route('/admin/projects/<int:project_id>/approve', methods=['POST'])
@admin_required
def admin_approve_project(project_id):
    project = Project.query.get_or_404(project_id)
    project.status = 'approved'
    
    try:
        db.session.commit()
        flash(f'Project "{project.title}" has been approved and is now live.')
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while approving the project.')
    
    return redirect(url_for('admin_projects'))

@app.route('/admin/projects/<int:project_id>/reject', methods=['POST'])
@admin_required
def admin_reject_project(project_id):
    project = Project.query.get_or_404(project_id)
    project.status = 'rejected'
    
    try:
        db.session.commit()
        flash(f'Project "{project.title}" has been rejected.')
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while rejecting the project.')
    
    return redirect(url_for('admin_projects'))

@app.route('/admin/projects/<int:project_id>/feedback', methods=['POST'])
@admin_required
def admin_project_feedback(project_id):
    project = Project.query.get_or_404(project_id)
    feedback = request.form.get('feedback', '')
    
    project.admin_feedback = feedback
    
    try:
        db.session.commit()
        flash('Feedback has been saved.')
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while saving feedback.')
    
    return redirect(url_for('admin_review_project', project_id=project.id))

@app.route('/admin/users')
@admin_required
def admin_users():
    user = User.query.get(session['user_id'])
    
    # Get filter and search parameters
    search = request.args.get('search', '')
    user_type = request.args.get('user_type', '')
    sort = request.args.get('sort', 'newest')
    
    # Build query
    query = User.query
    
    if search:
        query = query.filter(User.username.ilike(f'%{search}%') | User.email.ilike(f'%{search}%'))
    
    if user_type:
        query = query.filter(User.user_type == user_type)
    
    # Apply sorting
    if sort == 'newest':
        query = query.order_by(User.created_at.desc())
    elif sort == 'oldest':
        query = query.order_by(User.created_at.asc())
    elif sort == 'username':
        query = query.order_by(User.username.asc())
    
    # Get all users
    users = query.all()
    
    return render_template('admin_users.html', user=user, users=users, request=request)

@app.route('/admin/users/<int:user_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_edit_user(user_id):
    admin = User.query.get(session['user_id'])
    edit_user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        user_type = request.form.get('user_type')
        
        # Check if username already exists for another user
        existing_user = User.query.filter(User.username == username, User.id != user_id).first()
        if existing_user:
            flash('Username already exists.')
            return redirect(url_for('admin_edit_user', user_id=user_id))
        
        # Check if email already exists for another user
        existing_email = User.query.filter(User.email == email, User.id != user_id).first()
        if existing_email:
            flash('Email already exists.')
            return redirect(url_for('admin_edit_user', user_id=user_id))
        
        # Update user
        edit_user.username = username
        edit_user.email = email
        edit_user.user_type = user_type
        
        # Update password if provided
        new_password = request.form.get('new_password')
        if new_password:
            edit_user.password_hash = generate_password_hash(new_password)
        
        try:
            db.session.commit()
            flash('User updated successfully.')
            return redirect(url_for('admin_users'))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while updating the user.')
            return redirect(url_for('admin_edit_user', user_id=user_id))
    
    return render_template('admin_edit_user.html', user=admin, edit_user=edit_user)

@app.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@admin_required
def admin_delete_user(user_id):
    # Prevent self-deletion
    if user_id == session['user_id']:
        flash('You cannot delete your own account.')
        return redirect(url_for('admin_users'))
    
    user_to_delete = User.query.get_or_404(user_id)
    
    try:
        # Delete associated projects and investments first
        Project.query.filter_by(user_id=user_id).delete()
        Investment.query.filter_by(user_id=user_id).delete()
        
        db.session.delete(user_to_delete)
        db.session.commit()
        flash('User and all associated data deleted successfully.')
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while deleting the user.')
    
    return redirect(url_for('admin_users'))

# Helper function for sending OTP email
def send_otp_email(email, otp, purpose="verification"):
    if purpose == "verification":
        subject = "Verify Your Email - SparkVest"
        title = "Verify Your Email"
        message = "Thank you for registering with SparkVest. To complete your registration, please use the following verification code:"
    elif purpose == "password_reset":
        subject = "Password Reset - SparkVest"
        title = "Reset Your Password"
        message = "You requested to reset your password. Please use the following verification code to proceed:"
    else:
        subject = "Verification Code - SparkVest"
        title = "Your Verification Code"
        message = "Please use the following verification code:"
    
    msg = Message(subject=subject, recipients=[email])
    msg.html = f'''
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 5px;">
        <div style="text-align: center; margin-bottom: 20px;">
            <h1 style="color: #3D5BA9;">SparkVest</h1>
        </div>
        <div style="padding: 20px; background-color: #f9f9f9; border-radius: 5px;">
            <h2 style="margin-top: 0;">{title}</h2>
            <p>{message}</p>
            <div style="text-align: center; margin: 30px 0;">
                <div style="font-size: 24px; font-weight: bold; letter-spacing: 5px; padding: 15px; background-color: #efefef; border-radius: 5px;">{otp}</div>
            </div>
            <p>This code will expire in 10 minutes.</p>
            <p>If you did not request this verification, please ignore this email.</p>
        </div>
        <div style="margin-top: 20px; text-align: center; color: #888; font-size: 12px;">
            <p>&copy; 2025 SparkVest. All rights reserved.</p>
        </div>
    </div>
    '''
    mail.send(msg)

# Routes for OTP verification
@app.route('/verify-otp', methods=['GET'])
@app.route('/verify_otp', methods=['GET'])
def verify_otp():
    email = request.args.get('email')
    login_after_verify = request.args.get('login_after_verify', 'false') == 'true'
    
    if not email or 'user_id' not in session:
        flash('Invalid verification request.', 'error')
        return redirect(url_for('register'))
    
    return render_template('verify_otp.html', email=email, user_id=session.get('user_id'), login_after_verify=login_after_verify)

@app.route('/verify', methods=['POST'])
def verify():
    email = request.form.get('email')
    user_id = request.form.get('user_id')
    otp = request.form.get('otp')
    login_after_verify = request.form.get('login_after_verify', 'false') == 'true'
    
    if not email or not otp or not user_id:
        flash('Invalid verification request.', 'error')
        return redirect(url_for('login'))
    
    if 'registration_otp' not in session or session['registration_otp'] != otp:
        flash('Invalid verification code. Please try again.', 'error')
        return redirect(url_for('verify_otp', email=email))
    
    # Verify the user
    user = User.query.get(int(user_id))
    if user:
        user.is_verified = True
        db.session.commit()
        
        # Clear OTP session
        session.pop('registration_otp', None)
        session.pop('user_email', None)
        
        # If user was attempting to login, log them in automatically
        if login_after_verify:
            session['user_id'] = user.id
            flash('Email verification successful! You are now logged in.', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Email verification successful! You can now log in.', 'success')
            return redirect(url_for('login'))
    else:
        flash('User not found.', 'error')
        return redirect(url_for('register'))

@app.route('/resend-otp')
def resend_otp():
    email = request.args.get('email')
    
    if not email or 'user_id' not in session:
        flash('Invalid request.', 'error')
        return redirect(url_for('login'))
    
    # Generate new OTP
    otp = ''.join(random.choices(string.digits, k=6))
    session['registration_otp'] = otp
    
    # Send OTP via email
    send_otp_email(email, otp)
    
    flash('Verification code has been resent to your email.', 'success')
    return redirect(url_for('verify_otp', email=email))

# Password reset routes
@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        
        # Check if user exists
        user = User.query.filter_by(email=email).first()
        
        if not user:
            flash('No account found with that email address.', 'error')
            return redirect(url_for('forgot_password'))
        
        # Generate OTP
        otp = ''.join(random.choices(string.digits, k=6))
        session['reset_otp'] = otp
        session['reset_email'] = email
        session['reset_user_id'] = user.id
        
        # Send OTP via email
        send_otp_email(email, otp, purpose="password_reset")
        
        flash('A verification code has been sent to your email.', 'success')
        return redirect(url_for('verify_password_otp', email=email))
    
    return render_template('forgot_password.html')

@app.route('/verify-password-otp', methods=['GET'])
def verify_password_otp():
    email = request.args.get('email')
    if not email or 'reset_email' not in session:
        flash('Invalid verification request.', 'error')
        return redirect(url_for('forgot_password'))
    
    return render_template('verify_otp.html', email=email, user_id=session.get('reset_user_id'), is_password_reset=True)

@app.route('/verify-password', methods=['POST'])
def verify_password():
    email = request.form.get('email')
    otp = request.form.get('otp')
    
    if not email or not otp or 'reset_email' not in session:
        flash('Invalid verification request.', 'error')
        return redirect(url_for('forgot_password'))
    
    if 'reset_otp' not in session or session['reset_otp'] != otp:
        flash('Invalid verification code. Please try again.', 'error')
        return redirect(url_for('verify_password_otp', email=email))
    
    # Generate a reset token
    reset_token = ''.join(random.choices(string.ascii_letters + string.digits, k=32))
    session['reset_token'] = reset_token
    
    return redirect(url_for('reset_password', token=reset_token, email=email))

@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'GET':
        token = request.args.get('token')
        email = request.args.get('email')
        
        if not token or not email or 'reset_token' not in session or session['reset_token'] != token:
            flash('Invalid or expired password reset link.', 'error')
            return redirect(url_for('login'))
        
        return render_template('reset_password.html', reset_token=token, email=email)
    
    elif request.method == 'POST':
        token = request.form.get('reset_token')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if not token or not email or not password or not confirm_password:
            flash('All fields are required.', 'error')
            return redirect(url_for('reset_password', token=token, email=email))
        
        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return redirect(url_for('reset_password', token=token, email=email))
        
        if 'reset_token' not in session or session['reset_token'] != token:
            flash('Invalid or expired password reset link.', 'error')
            return redirect(url_for('login'))
        
        # Update the user's password
        user = User.query.filter_by(email=email).first()
        if user:
            user.password_hash = generate_password_hash(password)
            db.session.commit()
            
            # Clear all reset-related session data
            session.pop('reset_otp', None)
            session.pop('reset_email', None)
            session.pop('reset_user_id', None)
            session.pop('reset_token', None)
            
            flash('Your password has been successfully reset. You can now log in with your new password.', 'success')
            return redirect(url_for('login'))
        else:
            flash('User not found.', 'error')
            return redirect(url_for('login'))

# Compute some properties for templates
@app.context_processor
def utility_processor():
    def project_progress_percentage(project):
        if project.goal <= 0:
            return 0
        return min(int((project.current_amount / project.goal) * 100), 100)
    
    def project_days_remaining(project):
        now = datetime.utcnow()
        if project.end_date < now:
            return 0
        return (project.end_date - now).days
    
    def project_is_funded(project):
        return project.current_amount >= project.goal
    
    return {
        'project_progress_percentage': project_progress_percentage,
        'project_days_remaining': project_days_remaining,
        'project_is_funded': project_is_funded
    }

# Get user by ID filter for templates
@app.template_filter('get_user_by_id')
def get_user_by_id(user_id):
    return User.query.get(user_id)

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user = User.query.get(session['user_id'])
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        # Check if username already exists for another user
        if username != user.username:
            existing_user = User.query.filter_by(username=username).first()
            if existing_user:
                flash('Username already exists.', 'error')
                return redirect(url_for('profile'))
        
        # Check if email already exists for another user
        if email != user.email:
            existing_email = User.query.filter_by(email=email).first()
            if existing_email:
                flash('Email already exists.', 'error')
                return redirect(url_for('profile'))
        
        # Update basic information
        user.username = username
        user.email = email
        
        # Update password if provided
        if current_password and new_password and confirm_password:
            if not check_password_hash(user.password_hash, current_password):
                flash('Current password is incorrect.', 'error')
                return redirect(url_for('profile'))
                
            if new_password != confirm_password:
                flash('New passwords do not match.', 'error')
                return redirect(url_for('profile'))
                
            user.password_hash = generate_password_hash(new_password)
            flash('Password updated successfully.', 'success')
        
        try:
            db.session.commit()
            flash('Profile updated successfully.', 'success')
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while updating your profile.', 'error')
        
        return redirect(url_for('profile'))
    
    return render_template('profile.html', user=user)