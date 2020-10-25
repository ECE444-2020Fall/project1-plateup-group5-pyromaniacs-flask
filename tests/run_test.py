import pytest
import os,sys,inspect
sys.path.insert(1, os.path.join(sys.path[0], '..'))
import json
from pathlib import Path
from initializer import api, app, db, login_manager, ma, scheduler, sp_api
from models import User, Recipe, Instruction, ShoppingList
from run import UserSchema

BASE_DIR = Path(__file__).resolve().parent
TEST_DB = os.path.join(BASE_DIR, 'test_db.sqlite')
app.config["EMAIL"] = "noreply.plateup@gmail.com"
app.config["PASSWORD"] =  "test-pw"

################################################################################
# Implemented by Kevin Zhang for Lab 6 - 2020/10/19
################################################################################
@pytest.fixture
def client():
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = 'sqlite:///' + TEST_DB
    db.create_all()  # setup
    yield app.test_client()  # tests run here
    db.drop_all()  # teardown

def login(client, email, password):
    """Login helper function"""
    return client.post("/login", json=dict(email=email, password=password))

def logout(client):
    """Logout helper function"""
    return client.delete("/login", follow_redirects=True)

def test_database(client):
    """initial test. ensure that the database exists"""
    tester = Path(TEST_DB).is_file()
    assert tester

def test_success_login_logout(client):
    """Test login and logout using helper functions"""
    new_user = User("Test", app.config["EMAIL"], app.config["PASSWORD"])
    db.session.add(new_user)
    db.session.commit()

    rv = login(client, app.config["EMAIL"], app.config["PASSWORD"])
    assert rv.json["email"] == app.config["EMAIL"]

    rv = logout(client)
    assert rv.data == ('Logout successful. User %s' %  new_user.id).encode()

def test_failure_login_logout(client):
    """Test (failed) login and logout using helper functions"""
    new_user = User("Test", app.config["EMAIL"], app.config["PASSWORD"])
    db.session.add(new_user)
    db.session.commit()

    rv = login(client, app.config["EMAIL"] + "x", app.config["PASSWORD"])
    assert rv.status == "403 FORBIDDEN"

    rv = login(client, app.config["EMAIL"], app.config["PASSWORD"] + "x")
    assert rv.status == "403 FORBIDDEN"
    


################################################################################
# Implemented by XXXX for Lab 6 - 2020/10/XX
################################################################################