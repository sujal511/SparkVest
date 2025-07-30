# SparkVest - Crowdfunding Platform

SparkVest is a modern crowdfunding web application built with Flask and Tailwind CSS. It allows creators to launch funding campaigns and backers to invest in innovative ideas.

## Features

- **User Authentication:** Register, login, and manage user accounts
- **Project Creation:** Users can create funding campaigns with details, goals, and images
- **Project Discovery:** Browse and search for active projects
- **Investment System:** Back projects with financial contributions
- **Dashboard:** Track projects and investments in a personal dashboard
- **Responsive Design:** Beautiful, mobile-friendly interface

## Tech Stack

- **Backend:**
  - Flask (Python web framework)
  - SQLAlchemy (ORM for database operations)
  - SQLite (Database)
  - Werkzeug (Password hashing, security tools)

- **Frontend:**
  - HTML5
  - Tailwind CSS (Utility-first CSS framework)
  - JavaScript (ES6+)
  - Jinja2 (Templating)

## Project Structure

```
SparkVest/
│
├── app.py             # Main application file
├── models.py          # Database models
├── routes.py          # URL routes and view functions
├── .env               # Environment variables (create from .env.example)
├── requirements.txt   # Project dependencies
│
├── static/            # Static files (CSS, JS, images)
│   └── uploads/       # User-uploaded files
│
└── templates/         # HTML templates
    ├── index.html     # Homepage/landing page
    ├── register.html  # User registration
    ├── login.html     # User login
    ├── dashboard.html # User dashboard
    └── ...            # Other templates
```

## Getting Started

### Prerequisites

- Python 3.8 or higher
- pip (Python package manager)

### Installation

1. Clone the repository:
   ```
   git clone https://github.com/yourusername/sparkVest.git
   cd sparkVest
   ```

2. Create and activate a virtual environment:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Create a `.env` file based on `.env.example`:
   ```
   SECRET_KEY=your_secure_secret_key
   DATABASE_URI=sqlite:///sparkVest.db
   UPLOAD_FOLDER=static/uploads
   ```

5. Initialize the database:
   ```
   python
   >>> from app import app, db
   >>> with app.app_context():
   >>>     db.create_all()
   >>> exit()
   ```

6. Run the application:
   ```
   python app.py
   ```

7. Visit `http://localhost:5000` in your browser.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Built with the power of Flask and Tailwind CSS
- Inspired by platforms like Kickstarter and Indiegogo 