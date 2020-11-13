import json
import os
import pytest
import sys

from pathlib import Path
from initializer import api, app, db, login_manager, ma, scheduler, sp_api
from models import User, Recipe, Instruction, ShoppingList, Inventory
from run import UserSchema, RecipeSchema, InstructionSchema

sys.path.insert(1, os.path.join(sys.path[0], '..'))

BASE_DIR = Path(__file__).resolve().parent
TEST_DB = os.path.join(BASE_DIR, 'test_db.sqlite')
app.config["EMAIL"] = "noreply.plateup@gmail.com"
app.config["PASSWORD"] = "test-pw"


################################################################################
# Implemented by Kevin Zhang for Lab 6 - 2020/10/19
################################################################################
@pytest.fixture
def client():
    # Database setup
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = 'sqlite:///' + TEST_DB
    db.create_all()

    # Add test user
    test_user = User("Test", app.config["EMAIL"], app.config["PASSWORD"])
    app.config["TEST_USER_ID"] = test_user.id
    db.session.add(test_user)
    db.session.commit()

    # Run tests
    yield app.test_client()

    # Teardown
    db.drop_all()


def login(client, email, password):
    """ Login helper function. """
    return client.post("/login", json=dict(email=email, password=password))


def logout(client):
    """ Logout helper function. """
    return client.delete("/login", follow_redirects=True)


def post_recipe(client, recipe):
    """ Post recipe helper function. """
    return client.post("/recipe", json=recipe)


def get_recipes(client, query=""):
    """ Get recipes helper function. """
    return client.get(f"/recipe{query}")


def test_database(client):
    """ Initial test. ensure that the database exists. """
    tester = Path(TEST_DB).is_file()
    assert tester


def test_success_login_logout(client):
    """ Test login and logout using helper functions. """
    rv = login(client, app.config["EMAIL"], app.config["PASSWORD"])
    assert rv.json["email"] == app.config["EMAIL"]

    rv = logout(client)
    assert rv.data == ('Logout successful. User %s' % app.config["TEST_USER_ID"]).encode()


def test_failure_login_logout(client):
    """ Test (failed) login and logout using helper functions. """
    rv = login(client, app.config["EMAIL"] + "x", app.config["PASSWORD"])
    assert rv.status == "403 FORBIDDEN"

    rv = login(client, app.config["EMAIL"], app.config["PASSWORD"] + "x")
    assert rv.status == "403 FORBIDDEN"


################################################################################
# Implemented by Eliano Anile for Lab 6 - 2020/10/26
################################################################################
def test_add_recipe(client):
    """ Test adding a recipe to the database. """
    rv = login(client, app.config["EMAIL"], app.config["PASSWORD"])
    assert rv.json["email"] == app.config["EMAIL"]

    rv = post_recipe(client, {
        "Name": "Test recipe name",
        "Ingredients": json.dumps([{"Test ingr 1": 6, "Test ingr 2": "1.5 Tbs"}]),
        "time_h": 1,
        "time_min": 30,
        "cost": 1000.0,
        "preview_text": "Test preview string",
        "preview_media_url": "https://testurl.com/img/test.jpg",
        "tags": "vegetarian, vegan"
    })

    assert rv.status == "200 OK"

    rv = get_recipes(client)
    assert rv.status == "200 OK"
    assert len(rv.json["recipes"]) == 1
    assert rv.json["recipes"][0]["name"] == "Test recipe name"


def test_get_random_recipes(client):
    """ Test getting random recipes from the database (i.e. no search keywords
        or filters specified).
    """
    rv = login(client, app.config["EMAIL"], app.config["PASSWORD"])
    assert rv.json["email"] == app.config["EMAIL"]

    rv = get_recipes(client)
    assert rv.status == "200 OK"
    assert rv.json["is_random"]


################################################################################
# Implemented by Jingxuan Su for Lab 6 - 2020/10/29
################################################################################

def post_instructions(client, instructions):
    return client.post("/recipe/1", json=instructions)


def get_instructions(client, recipeId):
    return client.get("/recipe/" + str(recipeId))


def add_instructions(client, id):
    new_instruction = {
        'recipe_id': "random",
        "step_num": 1,
        "step_instruction": "random_1",
        "ingredients": "random_1",
        "equipment": "random_1",
    }
    post_instructions(client, instructions=new_instruction)
    new_instruction = {
        'recipe_id': "random",
        "step_num": 2,
        "step_instruction": "random_2",
        "ingredients": "random_2",
        "equipment": "random_2",
    }
    post_instructions(client, instructions=new_instruction)
    new_instruction = {
        'recipe_id': str(id),
        "step_num": 1,
        "step_instruction": "step_instruction_test_1",
        "ingredients": "[{\"name\": \"test_1_ing_txt\", \"img\": \"test_i_ing_txt\"}]",
        "equipment": "[{\"name\": \"test_1_equ_txt\", \"img\": \"test_i_equ_txt\"}]",
    }
    post_instructions(client, instructions=new_instruction)
    new_instruction = {
        'recipe_id': str(id),
        "step_num": 2,
        "step_instruction": "step_instruction_test_2",
        "ingredients": "[{\"name\": \"test_2_ing_txt\", \"img\": \"test_2_ing_txt\"}]",
        "equipment": "[{\"name\": \"test_2_equ_txt\", \"img\": \"test_2_equ_txt\"}]",
    }
    post_instructions(client, instructions=new_instruction)
    new_instruction = {
        'recipe_id': str(id),
        "step_num": 3,
        "step_instruction": "step_instruction_test_3",
        "ingredients": "[{\"name\": \"test_3_ing_txt\", \"img\": \"test_3_ing_txt\"}]",
        "equipment": "[{\"name\": \"test_3_equ_txt\", \"img\": \"test_3_equ_txt\"}]",
    }
    post_instructions(client, instructions=new_instruction)


def add_recipe(client):
    post_recipe(client, {
        "Name": "Test recipe name",
        "Ingredients": json.dumps([{"tea": "1 unit", "beef": "2 unit"}]),
        "time_h": 0,
        "time_min": 5,
        "cost": 1.0,
        "preview_text": "Test preview string",
        "preview_media_url": "https://testurl.com/img/test.jpg",
        "tags": "vegetarian, vegan"
    })


def get_id(client):
    rv = get_recipes(client)
    return rv.json["recipes"][0]["id"]


def drop_table(client):
    # Recipe.__table__.drop(db.engine)
    # Instruction.__table__.drop(db.engine)
    db.session.query(Recipe).delete()
    db.session.query(Instruction).delete()


def debug_show_table():
    list = db.session.query(Instruction).all()
    print("current table")
    for i in range(len(list)):
        print(list[i].recipe_id)
        print(list[i].step_num)
        print(list[i].step_instruction)
        print(list[i].ingredients)
        print(list[i].equipment)
    print("end")
    list = db.session.query(Recipe).all()
    print("current table")
    for i in range(len(list)):
        print(list[i].id)
        print(list[i].name)
    print("end")


def test_get_instructions(client):
    rv = login(client, app.config["EMAIL"], app.config["PASSWORD"])
    assert rv.json["email"] == app.config["EMAIL"]
    drop_table(client)
    add_recipe(client)
    recipe_id = get_id(client)
    add_instructions(client, recipe_id)
    rv = get_instructions(client, recipe_id)
    if rv.status != "200 OK":
        debug_show_table()

    assert rv.json["recipe_instruction"][0]["step_instruction"] == "step_instruction_test_1"
    assert rv.json["recipe_instruction"][1]["step_instruction"] == "step_instruction_test_2"
    assert rv.json["recipe_instruction"][2]["step_instruction"] == "step_instruction_test_3"
    assert rv.json["recipe_instruction"][0]["ingredients"][0]["name"] == "test_1_ing_txt"
    assert rv.json["recipe_instruction"][0]["equipment"][0]["name"] == "test_1_equ_txt"

################################################################################
# Implemented by Jingxuan Su for Inventory - 2020/11/11
################################################################################

def get_inventory(client, user_id):
    return client.get("/inventory/user1")

def post_inventory(client, inventory):
    return client.post("/inventory/user1", json=inventory)

def test_get_post_Inventory(client):
    rv = login(client, app.config["EMAIL"], app.config["PASSWORD"])
    assert rv.json["email"] == app.config["EMAIL"]
    inventory={"inventory": {"name1": {"qty": 13.4,"unit": "string"}}}
    rv=post_inventory(client, inventory)
    assert rv.json["inventory"]["name1"]["qty"] == 13.4
    rv=get_inventory(client, "1")

    assert rv.json["inventory"]["name1"]["qty"] == 13.4

################################################################################
# Implemented by Jingxuan Su for Shopping list API - 2020/11/11
################################################################################

def get_shopping(client, user_id):
    return client.get("/shopping/user1")

def post_shopping(client, shopping):
    return client.post("/shopping/user1", json=shopping)

def test_get_post_shopping(client):
    rv = login(client, app.config["EMAIL"], app.config["PASSWORD"])
    assert rv.json["email"] == app.config["EMAIL"]
    shopping={"shopping": {"name1": {"qty": 13.4,"unit": "string"}}}
    rv=post_shopping(client, shopping)
    assert rv.json["shopping"]["name1"]["qty"] == 13.4
    rv=get_shopping(client, "1")

    assert rv.json["shopping"]["name1"]["qty"] == 13.4

################################################################################
# Implemented by Jingxuan Su for RecipeInventoryCheckerAPI - 2020/11/11
################################################################################

def activate_checker(client):
    recipe_id = get_id(client)
    return client.get("/recipe/"+str(recipe_id)+"/check/user1")

def add_recipe_version_two(client):
    rv=post_recipe(client, {
        "Name": "Test recipe name",
        "Ingredients": json.dumps({"tea": "1 unit", "beef": "2 unit"}),
        "time_h": 0,
        "time_min": 5,
        "cost": 1.0,
        "preview_text": "Test preview string",
        "preview_media_url": "https://testurl.com/img/test.jpg",
        "tags": "vegetarian, vegan"
    })

def test_get_recipe_inventory_checker(client):
    rv = login(client, app.config["EMAIL"], app.config["PASSWORD"])
    assert rv.json["email"] == app.config["EMAIL"]

    add_recipe_version_two(client)
    inventory = {"inventory": {"tea": {"qty": 13.4, "unit": "unit"}, "beef": {"qty": 13.4, "unit": "unit"}}}
    rv = post_inventory(client, inventory)
    assert rv.json["inventory"]["tea"]["qty"] == 13.4

    rv=activate_checker(client)
    assert rv.status == "200 OK"
    assert rv.data == b"Inventory updated, enough ingredients to proceed!"

    rv=get_inventory(client,"user1")
    assert rv.json["inventory"]["tea"]["qty"] == 12.4
    assert rv.json["inventory"]["beef"]["qty"] == 11.4

################################################################################
# Implemented by Jingxuan Su for Flash API - 2020/11/11
################################################################################

def activate_flash(client):
    return client.post("/shopping/flash", json={"user_id" : "user1"})

def test_flash(client):
    rv = login(client, app.config["EMAIL"], app.config["PASSWORD"])
    assert rv.json["email"] == app.config["EMAIL"]

    shopping = {"shopping": {"name1": {"qty": 13.4, "unit": "string"}, "tea": {"qty": 13.4, "unit": "unit"}, "beef": {"qty": 13.4, "unit": "unit"}}}
    rv = post_shopping(client, shopping)
    assert rv.json["shopping"]["name1"]["qty"] == 13.4

    inventory = {"inventory": {"tea": {"qty": 13.4, "unit": "unit"}, "beef": {"qty": 13.4, "unit": "unit"}}}
    rv = post_inventory(client, inventory)
    assert rv.json["inventory"]["tea"]["qty"] == 13.4

    rv = activate_flash(client)
    print(rv)
    assert rv.json["inventory"]["tea"]["qty"] == 26.8
    assert rv.json["inventory"]["beef"]["qty"] == 26.8

