import os
import urllib3
import spoonacular

from flask import Flask
from flask_login import LoginManager
from flask_marshmallow import Marshmallow
from flask_restx import Api
from flask_sqlalchemy import SQLAlchemy

from apscheduler.schedulers.background import BackgroundScheduler

# Disable SSL warning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Init app
app = Flask("PlateUp")
basedir = os.path.abspath(os.path.dirname(__file__))

# Database set up
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + \
    os.path.join(basedir, 'db.sqlite')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = "PLATEUP"

# Init db
db = SQLAlchemy(app)

# Init ma
ma = Marshmallow(app)

api = Api(app, version='1.1', title='PLATEUP API',
          description='The backend API for PlateUp, a chef\'s co-pilot!')

# Init login manager
login_manager = LoginManager()
login_manager.init_app(app)

# Init Schedular for background updates
scheduler = BackgroundScheduler()

# Init Spoonacular API service
sp_api = spoonacular.API("2285bbff227b4b198ef446e6dfb192e3")
