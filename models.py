from app import db
from datetime import datetime

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone_number = db.Column(db.String(20), nullable=True)
    password_hash = db.Column(db.String(200), nullable=False)
    user_type = db.Column(db.String(20), nullable=False, default='investor')  # 'investor', 'idea_owner', or 'admin'
    is_verified = db.Column(db.Boolean, default=False)  # Email verification status
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    projects = db.relationship('Project', backref='creator', lazy=True)
    investments = db.relationship('Investment', backref='investor', lazy=True)
    
    def __repr__(self):
        return f'<User {self.username}>'

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    short_description = db.Column(db.String(150), nullable=True)
    description = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50), nullable=True)
    goal = db.Column(db.Float, nullable=False)
    current_amount = db.Column(db.Float, default=0)
    start_date = db.Column(db.DateTime, default=datetime.utcnow)
    end_date = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    investments = db.relationship('Investment', backref='project', lazy=True)
    image_url = db.Column(db.String(255), nullable=True)
    additional_images = db.Column(db.Text, nullable=True)  # Comma-separated list of image URLs
    video_url = db.Column(db.String(255), nullable=True)  # YouTube or other video platform URL
    research_report_url = db.Column(db.String(255), nullable=True)  # URL to uploaded research report
    team_info = db.Column(db.Text, nullable=True)  # Legacy field, keeping for backward compatibility
    team_members = db.relationship('TeamMember', backref='project', lazy=True, cascade="all, delete-orphan")
    market_opportunity = db.Column(db.Text, nullable=True)
    use_of_funds = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='pending', nullable=False)  # 'pending', 'approved', 'rejected'
    admin_feedback = db.Column(db.Text, nullable=True)
    return_type = db.Column(db.String(20), default='reward', nullable=False)  # 'reward' or 'stake'
    stake_terms = db.Column(db.Text, nullable=True)  # Terms for stake offerings
    
    @property
    def days_remaining(self):
        now = datetime.utcnow()
        if self.end_date < now:
            return 0
        return (self.end_date - now).days
    
    @property
    def progress_percentage(self):
        if self.goal <= 0:
            return 0
        return min(int((self.current_amount / self.goal) * 100), 100)
    
    @property
    def is_funded(self):
        return self.current_amount >= self.goal
    
    def __repr__(self):
        return f'<Project {self.title}>'

class Investment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    certificate_url = db.Column(db.String(255), nullable=True)  # URL to the stake certificate if applicable
    
    def __repr__(self):
        return f'<Investment ${self.amount}>'

class TeamMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    # For registered users
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    # For external team members
    name = db.Column(db.String(100), nullable=True)
    role = db.Column(db.String(100), nullable=True)
    linkedin_profile = db.Column(db.String(255), nullable=True)
    
    def __repr__(self):
        if self.user_id:
            return f'<TeamMember {self.user_id} (Registered User)>'
        else:
            return f'<TeamMember {self.name} (External)>'

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('comment.id'), nullable=True)
    
    # Relationships
    user = db.relationship('User', backref='comments')
    project = db.relationship('Project', backref='comments')
    replies = db.relationship('Comment', backref=db.backref('parent', remote_side=[id]), lazy='dynamic')
    likes = db.relationship('CommentLike', backref='comment', lazy='dynamic', cascade="all, delete-orphan")
    
    @property
    def like_count(self):
        return self.likes.count()
    
    def __repr__(self):
        return f'<Comment {self.id}>'

class CommentLike(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    comment_id = db.Column(db.Integer, db.ForeignKey('comment.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Set up a unique constraint to prevent duplicate likes
    __table_args__ = (db.UniqueConstraint('user_id', 'comment_id', name='unique_user_comment_like'),)
    
    user = db.relationship('User')
    
    def __repr__(self):
        return f'<CommentLike {self.user_id} on {self.comment_id}>'