from uuid import uuid1
from flask_login import UserMixin
from werkzeug.security import generate_password_hash
from initializer import db


# -----------------------------------------------------------------------------
# DB Models
# Models are fairly simple to read, so no additional comments are added
# to avoid being too verbose.
#
# These models define SQL tables as python sqlalchemy objects to allow
# easy object manipulation using python syntax.
# -----------------------------------------------------------------------------
class User(db.Model, UserMixin):
    __tablename__ = "user"

    id = db.Column(db.String(40), primary_key=True)
    name = db.Column(db.String(50))
    email = db.Column(db.String(40))
    password = db.Column(db.String)
    settings_id = db.Column(db.String(40))
    shopping_id = db.Column(db.String(40))
    inventory_id = db.Column(db.String(40))

    def __init__(self, name, email, password):
        self.id = str(uuid1())
        self.name = name
        self.email = email
        self.password = generate_password_hash(password, "pbkdf2:sha256")
        self.settings_id = str(uuid1())
        self.shopping_id = str(uuid1())
        self.inventory_id = str(uuid1())


class Recipe(db.Model):
    __tablename__ = "recipe"
    id = db.Column(db.String(40), primary_key=True)
    name = db.Column(db.String(150))
    ingredients = db.Column(db.String)
    time_h = db.Column(db.Integer)
    time_min = db.Column(db.Integer)
    cost = db.Column(db.Float)
    preview_text = db.Column(db.String)
    preview_media_url = db.Column(db.String)
    tags = db.Column(db.String)

    def __init__(self, name, ingredients, time_h, time_min, cost,
                 preview_text, preview_media, tags):
        self.id = str(uuid1())
        self.name = name
        self.ingredients = ingredients
        self.time_h = time_h
        self.time_min = time_min
        self.cost = cost
        self.preview_text = preview_text
        self.preview_media_url = preview_media
        self.tags = tags


class Instruction(db.Model):
    __tablename__ = "recipe_instruction"
    recipe_id = db.Column(db.String(40), db.ForeignKey(
        'recipe.id'), primary_key=True)
    step_num = db.Column(db.Integer, primary_key=True)
    step_instruction = db.Column(db.String)
    equipment = db.Column(db.String)
    ingredient = db.Column(db.String)

    def __init__(self, recipe_id, step_num, step, equipement, ingredient):
        self.recipe_id = recipe_id
        self.step_num = step_num
        self.step_instruction = step
        self.equipment = equipement
        self.ingredient = ingredient


class Inventory(db.Model):
    __tablename__ = "inventory"

    user_id = db.Column(db.String(40), db.ForeignKey(
        'user.id'), primary_key=True)
    ingredient_name = db.Column(db.String(50), primary_key=True)
    quantity = db.Column(db.Float)
    unit = db.Column(db.String(20))

    def __init__(self, user_id, ingredient_name, quantity, unit):
        self.user_id = user_id
        self.ingredient_name = ingredient_name
        self.quantity = quantity
        self.unit = unit


class ShoppingList(db.Model):
    __tablename__ = "shoppinglist"

    user_id = db.Column(db.String(40), db.ForeignKey(
        'user.id'), primary_key=True)
    ingredient_name = db.Column(db.String(50), primary_key=True)
    quantity = db.Column(db.Float)
    unit = db.Column(db.String(20))

    def __init__(self, user_id, ingredient_name, quantity, unit):
        self.user_id = user_id
        self.ingredient_name = ingredient_name
        self.quantity = quantity
        self.unit = unit
