import time
import random
import json
import os
import operator

from flask import jsonify, request, Response
from flask_login import current_user, login_user, login_required, logout_user
from flask_restx import fields, Resource
from werkzeug.security import check_password_hash

from emailservice import send_email_as_plateup
from initializer import api, app, db, login_manager, ma, scheduler, sp_api
from models import User, Recipe, Instruction, ShoppingList, Ingredient, Equipment, Inventory


# -----------------------------------------------------------------------------
# Configure Namespaces
# Same as configuring routes in vanilla flask, but more organized
# For example, everything in the userR namespace will default attach /user
# to the root endpoint.
#
# The API documentation not only lives through comments and docstrings here,
# but also presented neatly through OpenAPI (Swagger).
# It can be viewed here: https://sheltered-thicket-73220.herokuapp.com/
# Or run locally and access the root endpoint.
# -----------------------------------------------------------------------------
plateupR = api.namespace('plate-up', description='PlateUp operations')
userR = api.namespace('user', description='User operations')
loginR = api.namespace('login', description='Login/logout operations')
mailR = api.namespace('mail', description='Mailing operations')
recipeR = api.namespace('recipe', description='Preview of recipes')
recipeDetailR = api.namespace(
    'recipeDetail', description='Instruction level details for recipes')
inventoryR = api.namespace(
    'inventory', description='User inventory operations')
shoppingR = api.namespace(
    'shopping', description='User shopping list operations')


# -----------------------------------------------------------------------------
# DB Schemas (Marshmallow)
#
# These schemas define the serialization from sqlalchemy objects to JSON
# documents suitable for return from the API, and vice-versa (loading json
# into objects).
# -----------------------------------------------------------------------------

# Schema to serialize and deserialize the user object
class UserSchema(ma.Schema):
    class Meta:
        fields = (
            'id',
            'name',
            'email',
            'password',
            'settings_id',
            'shopping_id',
            'inventory_id'
        )


# Schema to serialize and deserialize the recipe overview object
class RecipeSchema(ma.Schema):
    class Meta:
        fields = (
            'id',
            'name',
            'ingredients',
            'time_h',
            'time_min',
            'cost',
            'preview_text',
            'preview_media_url',
            'tags'
        )


# Schema to serialize and deserialize the recipe instruction object
class InstructionSchema(ma.Schema):
    class Meta:
        fields = ('step_instruction',)


# Schema to serialize and deserialize the step equipment object
class EquipmentSchema(ma.Schema):
    class Meta:
        fields = ('name', 'img',)


# Schema to serialize and deserialize the step ingredient object
class IngredientSchema(ma.Schema):
    class Meta:
        fields = ('name', 'img',)


# Initialize schemas (many = True auto formats several objects into an array)
user_schema = UserSchema()
users_schema = UserSchema(many=True)
recipe_schema = RecipeSchema()
recipes_schema = RecipeSchema(many=True)
instructions_schema = InstructionSchema(many=True)
equipments_schema = EquipmentSchema(many=True)
ingredients_schema = IngredientSchema(many=True)


# -----------------------------------------------------------------------------
# Flask API start
#
# All routes are defined subsequently
# -----------------------------------------------------------------------------
# The default route, for testing basic user login and access. A hello world
# message for the backend service.
@plateupR.route("")
class Main(Resource):
    '''
        HTTP GET /
        Returns a hello world message if and only if the user is logged in.
    '''
    @login_required
    def get(self):
        return "Hello! This is the backend for PlateUp - a chef's co-pilot."

# The user route, for all user related functinoality such as creating users,
# retrieving users, and deleting users.


@userR.route('')
class UserAPI(Resource):
    '''
        Resource model definition for the user information required to
        onboard a new user.

        Name, email, and password are collected for user acc creation.
    '''
    resource_fields = userR.model('User Information', {
        'name': fields.String,
        'email': fields.String,
        'password': fields.String,
    })

    '''
        HTTP GET /user
        Returns the complete list of all users in the system.
    '''
    @login_required
    @userR.doc(description="Get information for all users.")
    def get(self):
        all_users = User.query.all()
        result = users_schema.dump(all_users)
        result = {"users": result}
        return jsonify(result)

    '''
        HTTP POST /user
        Creates a new user and returns the new user details.
        Validates the User Information resource fields.
        Login is not required as this is for new user account creation.
    '''
    @userR.doc(description="Register a new user to the system with complete information.")
    @userR.expect(resource_fields, validate=True)
    def post(self):
        name = request.json['name']
        email = request.json['email']
        password = request.json['password']

        # Checks that the user email is unique
        currEmails = flat_list(User.query.with_entities(User.email).all())
        if email in currEmails:
            return Response(
                "The user with email "
                + email +
                " already exists! Please log in instead.",
                status=409
            )

        new_user = User(name, email, password)

        # Sends welcome email to user, if it doesn't work, then the email address is likely invalid
        if not send_welcome_email(email, new_user):
            return Response(
                "Mail not sent! Invalid email or server issues, user not saved.",
                status=400
            )

        db.session.add(new_user)
        db.session.commit()

        return user_schema.jsonify(new_user)

    '''
        HTTP DELETE /user
        Deletes all the users in the database (same as resetting database for users).
        Used only in testing, not production friendly.
    '''
    @userR.doc(description="WARNING: Delete all user information stored in the database.")
    @login_required
    def delete(self):
        num_rows_deleted = db.session.query(User).delete()
        db.session.commit()
        return "%i records deleted." % num_rows_deleted


# The login route used for authenticating and de-authenticating users.
@loginR.route('')
class LoginAPI(Resource):
    '''
        Resource model definition for the login information required to
        authenticate a user. Leverages flask-login, session-based.

        Email and password are necessary for login.
    '''
    resource_fields = userR.model('Login Information', {
        'email': fields.String,
        'password': fields.String,
    })

    '''
        HTTP POST /login
        Logins the user into the system with the provided email and password.
        The password is checked against the hash stored in the database.
        A hash of the password is stored for security purposes (uncrackable if DB leak).
    '''
    @loginR.doc(
        description="Logging a user into the system and authenticating for access to deeper APIs."
    )
    @loginR.expect(resource_fields, validate=True)
    def post(self):
        email = request.json['email']
        password = request.json['password']
        user = User.query.filter_by(email=email).first()

        if user is not None and check_password_hash(user.password, password):
            login_user(user)
            return user_schema.jsonify(user)

        return Response(
            "Login failed! Please confirm that the email and password are correct.",
            status=403
        )

    '''
        HTTP DELETE /login
        Logs the current user out, based on session id from the client side. 
    '''
    @loginR.doc(description="Logging current user out.")
    @login_required
    def delete(self):
        userId = current_user.id
        logout_user()
        return Response("Logout successful. User %s" % userId, status=200)


# The mail route used for sending messages to the user, including welcome emails
# and shopping list reminders.
@mailR.route('')
class MailAPI(Resource):
    '''
        HTTP GET /mail?userID=<user_id>
        Sends a welcome email to user with user_id. 
        Used mainly for testing the mailing pipeline. 
        Emails are often sent directly and not through nested API calls.
    '''
    @mailR.doc(
        description="Sends a welcome email to user with their client ID \
            and default password information."
    )
    @mailR.param("userID")
    @login_required
    def get(self):
        userID = request.args.get("userID")
        receipient = User.query.get(userID).email

        if send_welcome_email(receipient, userID):
            return Response("OK - Mail Sent!", status=200)

        return Response("NOT OK - Mail NOT Sent!", status=400)

# Comment


@recipeR.route('/<id>', methods=['GET', 'POST'])
class RecipeDetailAPI(Resource):
    resourceFields = recipeR.model('Information to get recipe instruction', {
        'recipe_id': fields.String,
        'step_num': fields.Integer,
        'step_instruction': fields.String,
        'ingredients_text': fields.String,
        'ingredients_image': fields.String,
        'equipment_text': fields.String,
        'equipment_image': fields.String,
    })

    def __get_recipe_instructions_by_id(self, recipe_id):
        recipe_found = db.session.query(Instruction).filter(
            Instruction.recipe_id.like(recipe_id)).all()
        return recipe_found

    def __get_recipe_ingredient_by_id(self, recipe_id):
        recipe_found = db.session.query(Ingredient).filter(
            Ingredient.recipe_id.like(recipe_id)).all()
        return recipe_found

    def __get_recipe_equipment_by_id(self, recipe_id):
        recipe_found = db.session.query(Equipment).filter(
            Equipment.recipe_id.like(recipe_id)).all()
        return recipe_found

    def __get_recipe_preview_by_id(self, recipe_id):
        recipe_found = db.session.query(Recipe).filter(
            Recipe.id.like(recipe_id)).all()
        return recipe_found

    def __sort_by_step(self, unsorted_list):
        sorted_list = sorted(
            unsorted_list, key=operator.attrgetter("step_num"), reverse=False)
        return sorted_list

    def __get_object_for_one_step(self, object_list, step_num):
        list_for_one_step = []
        for i in range(len(object_list)):
            if object_list[i].step_num == step_num:
                list_for_one_step.append(object_list[i])
        return list_for_one_step

    def __not_exist_instruction(self, recipe_instruction_object):
        instruction_list = self.__get_recipe_instructions_by_id(
            recipe_instruction_object.recipe_id)
        for i in range(len(instruction_list)):
            if instruction_list[i].step_num == recipe_instruction_object.step_num:
                return False
        return True

    def __organize_return_object(self, recipe_instruction_list,
                                 recipe_ingredient_list_sorted,
                                 recipe_equipment_list_sorted):
        dict_list = []
        for i in range(len(recipe_instruction_list)):
            step_instruction = recipe_instruction_list[i]
            step_number = step_instruction.step_num
            step_ingredient = self.__get_object_for_one_step(
                recipe_ingredient_list_sorted, step_number)
            step_equipement = self.__get_object_for_one_step(
                recipe_equipment_list_sorted, step_number)

            return_ingredient = ingredients_schema.dump(step_ingredient)
            return_equipment = equipments_schema.dump(step_equipement)
            return_dict = {"step_instruction": step_instruction.step_instruction,
                           "ingredients": return_ingredient, "equipment": return_equipment, }
            dict_list.append(return_dict)
        return dict_list

    @login_required
    def get(self, id):
        recipe_id = id

        recipe_instruction_list_unsorted = self.__get_recipe_instructions_by_id(
            recipe_id)
        recipe_ingredient_list_unsorted = self.__get_recipe_ingredient_by_id(
            recipe_id)
        recipe_equipment_list_unsorted = self.__get_recipe_equipment_by_id(
            recipe_id)

        recipe_instruction_list_sorted = self.__sort_by_step(
            recipe_instruction_list_unsorted)
        recipe_ingredient_list_sorted = self.__sort_by_step(
            recipe_ingredient_list_unsorted)
        recipe_equipment_list_sorted = self.__sort_by_step(
            recipe_equipment_list_unsorted)

        recipe_preview = self.__get_recipe_preview_by_id(id)

        if len(recipe_instruction_list_sorted) == 0:
            return Response("recipe instruction not found!", status=500)

        if len(recipe_preview) == 0:
            return Response("recipe preview not found!", status=500)
        return_step_list = self.__organize_return_object(recipe_instruction_list_sorted, recipe_ingredient_list_sorted,
                                                         recipe_equipment_list_sorted)
        return_preview = recipe_schema.dump(recipe_preview[0])
        return_object = {"recipe_preview": return_preview,
                         "recipe_instruction": return_step_list}

        return jsonify(return_object)

    @recipeR.doc(description="Insert recipe instruction to database")
    @recipeR.expect(resourceFields, validate=True)
    @login_required
    def post(self, id):
        new_instruction_recipe_id = request.json["recipe_id"]
        new_instruction_step_num = request.json["step_num"]
        new_instruction_step_instruction = request.json["step_instruction"]
        new_instruction_ingredients_text = request.json["ingredients_text"]
        new_instruction_ingredients_image = request.json["ingredients_image"]
        new_instruction_equipment_text = request.json["equipment_text"]
        new_instruction_equipment_image = request.json["equipment_image"]

        new_instruction_description = Instruction(new_instruction_recipe_id, new_instruction_step_num,
                                                  new_instruction_step_instruction)
        new_instruction_ingredient = Ingredient(new_instruction_recipe_id, new_instruction_step_num,
                                                new_instruction_ingredients_text,
                                                new_instruction_ingredients_image)
        new_instruction_equipment = Equipment(new_instruction_recipe_id, new_instruction_step_num,
                                              new_instruction_equipment_text,
                                              new_instruction_equipment_image)
        if self.__not_exist_instruction(new_instruction_description):
            db.session.add(new_instruction_description)
        db.session.add(new_instruction_ingredient)
        db.session.add(new_instruction_equipment)
        db.session.commit()

        return Response("recipe instruction inserted!", status=200)


# Comment
@recipeR.route('', methods=['GET', 'POST'])
class RecipeAPI(Resource):
    resourceFields = recipeR.model('Information to get recipe preview', {
        'Name': fields.String,
        'Ingredients': fields.String,
        'time_h': fields.Integer,
        'time_min': fields.Integer,
        'cost': fields.Float,
        'preview_text': fields.String,
        'preview_media_url': fields.String,
        'tags': fields.String,
        'user_id': fields.String,
        'Filter_has_ingredients': fields.Boolean
    })

    __dataBaseLength = 0
    __parser = ''
    __debug = False
    random_pick = False

    # Retrive JSON stuff
    def __getJson(self, recipeItem):
        recipePreviewText = recipeItem.preview_text
        recipePreviewMedia = recipeItem.preview_media_url
        return recipePreviewText, recipePreviewMedia

    # Search by Name
    def __merge_list(self, oldList, newList):
        in_old = set(oldList)
        in_new = set(newList)
        in_new_not_old = in_new-in_old
        merged_list = oldList+list(in_new_not_old)
        return merged_list

    def __search_in_database_by_keyword_ingredient(self, keyword):
        recipe_found = db.session.query(Recipe).filter(
            Recipe.ingredients.like(keyword)).all()
        return recipe_found

    def __search_in_database_by_keyword_name(self, keyword):
        recipe_found = db.session.query(Recipe).filter(
            Recipe.name.like(keyword)).all()
        return recipe_found

    def __search_in_database_by_keyword_tag(self, keyword):
        recipe_found = db.session.query(Recipe).filter(
            Recipe.tags.like(keyword)).all()
        return recipe_found

    def __search_keyword_list_for_search_by_name(self, keyword):
        keyword_list = []
        keyword_list.append("% "+keyword+" %")
        keyword_list.append("%" + keyword + " %")
        keyword_list.append("% " + keyword + "%")
        keyword_list.append("%" + keyword + "%")
        return keyword_list

    def __search_keyword_list_for_search_by_ingredient(self, keyword):
        keyword_list = []
        keyword_list.append("%\"" + keyword + "\"%")
        keyword_list.append("%\"" + keyword + " %")
        keyword_list.append("%" + keyword + "\"%")
        keyword_list.append("% "+keyword+" %")
        keyword_list.append("%" + keyword + " %")
        keyword_list.append("% " + keyword + "%")
        keyword_list.append("%" + keyword + "%")
        return keyword_list

    def __search_for_recipes_by_tags(self, keyword):
        recipe_list = self.__search_in_database_by_keyword_tag(keyword)
        new_recipe_list = self.__search_in_database_by_keyword_tag(
            keyword.lower())
        recipe_list = self.__merge_list(recipe_list, new_recipe_list)
        return recipe_list

    def __search_for_recipes_by_name(self, keyword):
        recipe_list = []
        keywordList = self.__search_keyword_list_for_search_by_name(keyword)
        keywordList = keywordList + \
            self.__search_keyword_list_for_search_by_name(keyword.lower())
        for i in range(len(keywordList)):
            new_recipe_list = self.__search_in_database_by_keyword_name(
                keywordList[i])
            recipe_list = self.__merge_list(recipe_list, new_recipe_list)
        return recipe_list

    def __search_for_recipes_by_ingredient(self, keyword):
        recipe_list = []
        keywordList = self.__search_keyword_list_for_search_by_ingredient(
            keyword)
        keywordList = keywordList + \
            self.__search_keyword_list_for_search_by_ingredient(
                keyword.lower())
        for i in range(len(keywordList)):
            new_recipe_list = self.__search_in_database_by_keyword_ingredient(
                keywordList[i])
            recipe_list = self.__merge_list(recipe_list, new_recipe_list)
        return recipe_list
    '''
    filterRecipe
    '''

    def __filter_by_cost(self, recipe_list, filter_cost):
        recipe_list = [
            recipe for recipe in recipe_list if recipe.cost <= float(filter_cost)]
        return recipe_list

    def __filter_by_time(self, recipe_list, filter_time_h, filter_time_min):
        filter_time_h = int(filter_time_h)
        filter_time_min = int(filter_time_min)
        recipe_list_same_h = [
            recipe for recipe in recipe_list if recipe.time_h == int(filter_time_h)]
        recipe_list_same_h = [
            recipe for recipe in recipe_list_same_h if recipe.time_min <= int(filter_time_min)]
        recipe_list = [
            recipe for recipe in recipe_list if recipe.time_h < int(filter_time_h)]
        recipe_list = recipe_list_same_h+recipe_list
        return recipe_list

    '''
    [{"name": "apple", "img": "https://spoonacular.com/cdn/ingredients_250x250/apple.jpg"}, 
    {"name": "squash", "img": "https://spoonacular.com/cdn/ingredients_250x250/butternut-squash.jpg"},
    {"name": "soup", "img": "https://spoonacular.com/cdn/ingredients_250x250/"}]
    '''

    def __get_ingredient_from_recipe(self, recipe):
        ingredient_json = recipe.ingredients
        ingredient_list = json.loads(ingredient_json)
        name_list = []
        for ingredient in ingredient_list:
            name_list.append(ingredient["name"])
        return name_list

    def __check_ingredient_in_inventory(self, ingredient_name_list, user_id):
        for ingredient_name in ingredient_name_list:

            ingredient_in_inventory = db.session.query(Inventory).filter(
                Inventory.user_id.like(user_id),
                Inventory.ingredient_name.like(ingredient_name)).all()
            if len(ingredient_in_inventory) == 0:
                return False

            for inventory_entry in ingredient_in_inventory:
                if inventory_entry.quantity <= 0:
                    return False

        return True

    def __filter_by_ingredients(self, recipe_list, user_id):
        new_recipe_list = []
        for recipe in recipe_list:
            ingredients_name_list = self.__get_ingredient_from_recipe(recipe)

            if self.__check_ingredient_in_inventory(ingredients_name_list, user_id):
                new_recipe_list.append(recipe)
        return new_recipe_list

    def __filter_recipe(self, recipe_list, filter_cost, filter_time_h, filter_time_min,
                        filter_has_ingredient, user_id):
        if len(recipe_list) == 0:
            self.random_pick = True
            recipe_list = db.session.query(Recipe).all()

        if filter_cost != None:
            recipe_list = self.__filter_by_cost(recipe_list, filter_cost)
        if filter_time_h != None and filter_time_min != None:
            recipe_list = self.__filter_by_time(
                recipe_list, filter_time_h, filter_time_min)
        if filter_has_ingredient == True:
            recipe_list = self.__filter_by_ingredients(recipe_list, user_id)

        if len(recipe_list) == 0:
            self.random_pick = True
            recipe_list = db.session.query(Recipe).all()
        return recipe_list

    # insert recipe to database
    @recipeR.doc(description="Insert recipe to database")
    @recipeR.expect(resourceFields, validate=True)
    @login_required
    def post(self):
        new_recipe_name = request.json["Name"]
        new_recipe_ingredients = request.json["Ingredients"]
        new_recipe_time_h = request.json["time_h"]
        new_recipe_time_min = request.json["time_min"]
        new_recipe_cost = request.json["cost"]
        new_recipe_preview_text = request.json["preview_text"]
        new_recipe_preview_media_url = request.json["preview_media_url"]
        new_recipe_tags = request.json["tags"]

        if new_recipe_time_min > 60:
            new_recipe_time_h = new_recipe_time_h+int(new_recipe_time_min/60)
            new_recipe_time_min = new_recipe_time_min % 60

        new_recipe = Recipe(new_recipe_name, new_recipe_ingredients, new_recipe_time_h,
                            new_recipe_time_min, new_recipe_cost, new_recipe_preview_text,
                            new_recipe_preview_media_url, new_recipe_tags)

        db.session.add(new_recipe)
        db.session.commit()
        if self.__debug:
            self.__debug_show_table()
        return Response("recipe inserted!", status=200)

    # search recipe by Name and Filter
    # Example: http://127.0.0.1:5000/recipe?Search=juice&Filter_time_h=10&Filter_time_min=0&Filter_cost=10000&Page=0&Limit=2
    @recipeR.doc(description="Get recipe preview json by name and filter",
                 params={'Search': {'description': 'search by an ingredient, recipe name, or tag', 'type': 'string'},
                         'Filter_time_h': {'description': 'filter by max hours', 'type': 'int'},
                         'Filter_time_min': {'description': 'filter by max minutes (<60)', 'type': 'int'},
                         'Filter_cost': {'description': 'filter by max cost', 'type': 'float'},
                         'Filter_has_ingredients': {'description': 'filter by if user has all the appropriate ingredients', 'type': 'boolean'},
                         'Limit': {'description': 'number of recipes to return', 'type': 'int'},
                         'Page': {'description': 'page number determines range of data returned: [page x limit -> page x limit + limit]', 'type': 'int'}
                         })
    @login_required
    def get(self):
        # get params
        recipe_list = []
        search_query = request.args.get('Search')
        filter_time_h = request.args.get('Filter_time_h')
        filter_time_min = request.args.get('Filter_time_min')
        filter_cost = request.args.get('Filter_cost')
        filter_has_ingredients = bool(request.args.get(
            'Filter_has_ingredients') == True) if request.args.get('Filter_has_ingredients') else False
        limit = int(request.args.get('Limit')
                    ) if request.args.get('Limit') else 20
        page = int(request.args.get('Page')) if request.args.get('Page') else 0
        user_id = request.args.get(
            'user_id') if request.args.get('user_id') else ""

        if self.__debug == True:
            self.__debug_clear_table()
            self.__debug_add_recipe()
            self.__debug_show_table()

        self.random_pick = False
        # get list
        recipe_list_name = []
        recipe_list_ingredient = []
        recipe_list_tags = []

        if search_query != None:
            recipe_list_name = self.__search_for_recipes_by_name(search_query)
            recipe_list_ingredient = self.__search_for_recipes_by_ingredient(
                search_query)
            recipe_list_tags = self.__search_for_recipes_by_tags(search_query)

        recipe_list = self.__merge_list(
            recipe_list_name, recipe_list_ingredient)
        recipe_list = self.__merge_list(recipe_list, recipe_list_tags)

        recipe_list = self.__filter_recipe(recipe_list, filter_cost, filter_time_h,
                                           filter_time_min, filter_has_ingredients, user_id)

        if self.random_pick:
            recipe_list = random.sample(
                recipe_list, k=min(len(recipe_list), int(limit)))
            page = 0

        recipe_list = recipe_list[limit*page:limit*page+limit]

        return_result = recipes_schema.dump(recipe_list)

        return_dict = {"recipes": return_result, "is_random": self.random_pick}
        return jsonify(return_dict)


# The recipe checker route performs the function of validating whether or not a user has
# enough ingredients in their inventory to cook the specified recipe.
@recipeR.route('/<recipe_id>/check/<user_id>', methods=['GET'])
class RecipeInventoryCheckerAPI(Resource):
    '''
    HTTP GET /recipe/<recipe_id>/check/<user_id>

    This API call does one of two things:
    1. If the user has all the required ingredients for the recipe, it will deduct
    the ingredients from their inventory.
    2. If the user doesn't have all the required ingredients, it will check for the 
    missing ingredients and add them to the user's shopping list.

    In both cases, it is up to the client app to decide how to handle it. In case 1,
    the app should allow users to proceed to cooking. In case 2, the app should remind
    users to buy the required ingredients, or allow a manual override to continue
    cooking anyways. 
    '''
    @login_required
    def get(self, recipe_id, user_id):
        required_res = Recipe.query.get(recipe_id).ingredients
        required_res = json.loads(required_res)
        inventory_res = Inventory.query.filter_by(user_id=user_id).all()

        required = {}
        for ingredient_name in required_res:
            required[ingredient_name] = {
                "quantity": float(required_res[ingredient_name].split()[0]),
                "unit": required_res[ingredient_name].split()[1] if len(required_res[ingredient_name].split()) > 1 else ""
            }

        inventory = {}
        for entry in inventory_res:
            inventory[entry.ingredient_name] = {
                "quantity": entry.quantity,
                "unit": entry.unit
            }

        has_missing = False
        for entry in required:
            if entry in inventory:
                if required[entry]['unit'] != inventory[entry]['unit']:
                    return Response("Bad unit match while checking ingredient requirements for recipe.", status=400)
                if inventory[entry]['quantity'] - required[entry]['quantity'] >= 0:
                    inventory[entry]['quantity'] -= required[entry]['quantity']
                else:
                    has_missing = True
                    new_entry = ShoppingList(
                        user_id, entry, required[entry]['quantity']-inventory[entry]['quantity'], inventory[entry]['quantity'])
                    db.session.add(new_entry)
            else:
                has_missing = True
                new_entry = ShoppingList(
                    user_id, entry, required[entry]['quantity'], required[entry]['unit'])
                db.session.add(new_entry)

        if has_missing:
            db.session.commit()
            return Response("Not enough ingredients, added to shopping list", status=200)

        for entry in inventory:
            inventory_entry = Inventory.query.get((user_id, entry))
            if inventory[entry]['quantity'] != 0:
                inventory_entry.quantity = inventory[entry]['quantity']
            else:
                db.session.delete(inventory_entry)

        db.session.commit()

        return Response("Inventory updated, enough ingredients to proceed!", status=200)


# The inventory route is used for getting and setting the user's existing stock of groceries,
# which is referred to as the user's inventory.
@inventoryR.route('/<user_id>', methods=['GET', 'POST'])
class InventoryAPI(Resource):
    '''
        Resource model definitions for the inventory details required to update a
        user's inventory. It is defined in three components to clarify the nested
        structure.

        The full structure looks like this:
        inventory: {
            name0: {
                qty: xxx
                unit:xxx
            },
            name1: {
                qty: xxx
                unit:xxx
            },
        }
    '''
    quantity_fields = inventoryR.model('Quantity', {
        'qty': fields.Float,
        'unit': fields.String,
    })

    ingredient_fields = inventoryR.model('Ingredient', {
        'name': fields.Nested(quantity_fields),
    })

    inventory_fields = inventoryR.model('InventoryDetails', {
        'inventory': fields.Nested(ingredient_fields),
    })

    '''
    HTTP GET /inventory/<user_id>

    Returns the user's current inventory formatted as depicted in the resource
    field "inventory_fields" documentation. 
    '''
    @inventoryR.doc(description="Retrieving the user's current inventory.")
    @login_required
    def get(self, user_id):
        inventory_res = Inventory.query.filter_by(user_id=user_id).all()
        inventory = {}
        for entry in inventory_res:
            inventory[entry.ingredient_name] = {
                "qty": entry.quantity, "unit": entry.unit}
        response = {"inventory": inventory}
        return jsonify(response)

    '''
    HTTP {POST} /inventory/<user_id>

    Updates the user's current inventory, given an input formatted as depicted in the 
    resource field "inventory_fields" documentation. 

    Returns the updated inventory, which should be the same as the posted document
    less any errors.
    '''
    @inventoryR.doc(description="Posting a new or updated version of the user's inventory.")
    @inventoryR.expect(inventory_fields, validate=True)
    @login_required
    def post(self, user_id):
        inventory = request.json['inventory']
        inventory_res = Inventory.query.filter_by(user_id=user_id).delete()

        for entry_name in inventory:
            new_entry = Inventory(
                user_id, entry_name, inventory[entry_name]["qty"], inventory[entry_name]["unit"])
            db.session.add(new_entry)

        db.session.commit()

        inventory_res = Inventory.query.filter_by(user_id=user_id).all()
        inventory = {}

        for entry in inventory_res:
            inventory[entry.ingredient_name] = {
                "qty": entry.quantity, "unit": entry.unit}

        response = {"inventory": inventory}

        return jsonify(response)


# The shopping route is used in a similar manner as the inventory route, for getting and
# setting the user's shopping list.
@shoppingR.route('/<user_id>', methods=['GET', 'POST'])
class ShoppingListAPI(Resource):
    '''
        Resource model definitions for the inventory details required to update a
        user's shopping list. It is defined in three components to clarify the nested
        structure. Deliberately formatted similarly to inventory as these two
        are made to be easily transferrable (shopping list > inventory and vice versa).

        The full structure looks like this:
        shopping: {
            name0: {
                qty: xxx
                unit:xxx
            },
            name1: {
                qty: xxx
                unit:xxx
            },
        }
    '''
    quantity_fields = shoppingR.model('Quantity', {
        'qty': fields.Float,
        'unit': fields.String,
    })

    ingredient_fields = shoppingR.model('Ingredient', {
        'name': fields.Nested(quantity_fields),
    })

    shopping_fields = shoppingR.model('ShoppingList', {
        'shopping': fields.Nested(ingredient_fields)
    })

    '''
    HTTP GET /shopping/<user_id>

    Returns the user's current shopping list formatted as depicted in the resource
    field "shopping_fields" documentation. 
    '''
    @shoppingR.doc(description="Retrieving the user's current shopping list.")
    @login_required
    def get(self, user_id):

        shopping_res = ShoppingList.query.filter_by(user_id=user_id).all()
        shopping = {}

        for entry in shopping_res:
            shopping[entry.ingredient_name] = {
                "qty": entry.quantity, "unit": entry.unit}
        response = {"shopping": shopping}
        return jsonify(response)

    '''
    HTTP {POST} /shopping/<user_id>

    Updates the user's current shopping list, given an input formatted as depicted in the 
    resource field "shopping_fields" documentation. 

    Returns the updated shopping list, which should be the same as the posted document
    less any errors.
    '''
    @shoppingR.doc(description="Posting a new or updated version of the user's shopping list.")
    @shoppingR.expect(shopping_fields, validate=True)
    @login_required
    def post(self, user_id):
        shopping = request.json['shopping']
        shopping_res = ShoppingList.query.filter_by(user_id=user_id).delete()

        for entry_name in shopping:
            new_entry = ShoppingList(
                user_id, entry_name, shopping[entry_name]["qty"], shopping[entry_name]["unit"])
            db.session.add(new_entry)

        db.session.commit()

        shopping_res = ShoppingList.query.filter_by(user_id=user_id).all()
        shopping = {}

        for entry in shopping_res:
            shopping[entry.ingredient_name] = {
                "qty": entry.quantity, "unit": entry.unit}

        response = {"shopping": shopping}

        return jsonify(response)


# The shopping flash root that pushes all the user's shopping list items into
# their inventory, assuming that the user has purchased all the required ingredients.
# TODO: expand flash functionality to allow partial flashes
@shoppingR.route('/flash', methods=['POST'])
class ShoppingFlashToInventoryAPI(Resource):
    '''
    The only field required is the user id, but used as a post to follow REST protocols
    as this endpoint updates the data, not suitable for get. More param can be more 
    easily added in the future with a defined resource model. 
    '''
    resource_fields = shoppingR.model('User', {
        'user_id': fields.String,
    })

    '''
    HTTP {POST} /shopping/flash

    Updates the user's current inventory based on the items in the shopping list.

    For items that don't exist, new items are created in the user's inventory.
    For items that already exist, their quantities are modified. 

    Returns the updated user inventory.
    '''
    @inventoryR.doc(description="Push the user's shopping list to the user's inventory.")
    @inventoryR.expect(resource_fields, validate=True)
    @login_required
    def post(self):
        user_id = request.json['user_id']
        shopping_res = ShoppingList.query.filter_by(user_id=user_id).all()
        inventory_res = Inventory.query.filter_by(user_id=user_id).all()

        inventory = {}
        for entry in inventory_res:
            inventory[entry.ingredient_name] = entry.quantity

        for entry in shopping_res:
            if entry.ingredient_name not in inventory:
                new_entry = Inventory(
                    user_id, entry.ingredient_name, entry.quantity, entry.unit)
                db.session.add(new_entry)
            else:
                inventory_entry = Inventory.query.get(
                    (user_id, entry.ingredient_name))
                if entry.unit != inventory_entry.unit:
                    return Response("Bad unit match while flashing to inventory.", status=400)
                inventory_entry.quantity = inventory_entry.quantity + entry.quantity

        # Clear shopping list, after updating inventory
        shopping_res = ShoppingList.query.filter_by(user_id=user_id).delete()
        db.session.commit()

        # Fetches the latest inventory from DB to ensure no inconsistencies
        inventory_res = Inventory.query.filter_by(user_id=user_id).all()
        inventory = {}

        for entry in inventory_res:
            inventory[entry.ingredient_name] = {
                "qty": entry.quantity, "unit": entry.unit}

        response = {"inventory": inventory}

        return jsonify(response)


# -----------------------------------------------------------------------------
# Utility functions
# -----------------------------------------------------------------------------
# Flattens list into a string
def flat_list(l):
    return ["%s" % v for v in l]

# Callback to reload the user object
@login_manager.user_loader
def load_user(uid):
    return User.query.get(uid)

# Sends the welcome email, including the template
def send_welcome_email(receipient, user):
    name = user.name
    password = user.password
    email = user.email

    subject = 'Welcome to PlateUp - %s' % name
    body = '''
    <html>
    <head>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
    <!-- converted from rtf -->
    <style>
        <!-- .EmailQuote { margin-left: 1pt; padding-left: 4pt; border-left: #800000 2px solid; } -->
    </style>
    </head>
    <body>
    <font face="Calibri" size="2">
        <span style="font-size:20pt;color:red">
            Welcome to PlateUp by Team 5! Congratulations on taking your first step towards making your cooking journey easier. You will need the following information for future access to your account. <br>
            <br>
            Your email: %s <br>
            Your userID: %s <br>
            Your password: %s <br>
            <br>
            Click HERE to change your password. <br>
            <br>
            You will need your user ID and password to sign in whenever you use your PlateUp account. Do not share your password with anyone.
            Happy Cooking!
        </span>
    </font>
    </body>
    </html>''' % (email, str(user.id), password)

    return send_email_as_plateup(receipient, subject, body)

# Function to update the recipes read in from the json files stored in relative
# path /recipes to the database in the format expected by the various recipe routes.
def update_recipes():
    print("updating recipes...")

    i = 0
    while os.path.exists("recipes/recipes%s.json" % i):
        with open('recipes/recipes%s.json' % i, 'r') as outfile:
            print("processing recipes %s - %s..." % (i*100, i*100+100))
            recipes = json.load(outfile)
            i += 1
            try:
                for recipe in recipes['recipes']:
                    if Recipe.query.filter_by(name=recipe["title"]).first():
                        continue

                    new_recipe_name = recipe["title"]

                    ingredients = {}
                    for ingredient in recipe["extendedIngredients"]:
                        ingredients[ingredient["name"]] = str(
                            ingredient["amount"]) + " " + ingredient["unit"]

                    new_recipe_ingredients = json.dumps(ingredients)
                    new_recipe_time_h = 0
                    new_recipe_time_min = int(
                        recipe["readyInMinutes"]) if "readyInMinutes" in recipe else 60
                    new_recipe_cost = recipe["pricePerServing"]
                    new_recipe_preview_text = recipe["summary"]
                    new_recipe_preview_media_url = recipe["image"]
                    new_recipe_tags = construct_tag_string(recipe)

                    if new_recipe_time_min > 60:
                        new_recipe_time_h = new_recipe_time_h + \
                            int(new_recipe_time_min/60)
                        new_recipe_time_min = new_recipe_time_min % 60

                    new_recipe = Recipe(new_recipe_name, new_recipe_ingredients, new_recipe_time_h,
                                        new_recipe_time_min, new_recipe_cost, new_recipe_preview_text,
                                        new_recipe_preview_media_url, new_recipe_tags)

                    update_instructions(
                        new_recipe.id, recipe["analyzedInstructions"][0]["steps"])
                    db.session.add(new_recipe)
                    db.session.commit()

            except Exception as e:
                print(
                    "One recipe not updated due to missing fields or other error: %s \n" % e)
                print("skipping...")

    print("done updating recipes.")

# Helper function to update the instructions for each recipe into the database.
# Pulled out of the update_recipes function for better modularity and readability.
def update_instructions(recipe_id, instructions):
    for step in instructions:
        new_instruction_step_num = step["number"]
        new_instruction_step_instruction = step["step"]
        new_instruction_ingredients = json.dumps([{
            "name": ingredient["name"],
            "img":"https://spoonacular.com/cdn/ingredients_250x250/"+ingredient["image"]
        } for ingredient in step["ingredients"]])
        new_instruction_equipment = json.dumps([{
            "name": equipment["name"],
            "img":"https://spoonacular.com/cdn/equipment_250x250/"+equipment["image"]
        } for equipment in step["equipment"]])
        new_instruction = Instruction(
            recipe_id, new_instruction_step_num, new_instruction_step_instruction)
        new_equipment = Equipment(
            recipe_id, new_instruction_step_num, new_instruction_equipment)
        new_ingredients = Ingredient(
            recipe_id, new_instruction_step_num, new_instruction_ingredients)

        db.session.add(new_equipment)
        db.session.add(new_instruction)
        db.session.add(new_ingredients)

    db.session.commit()

# Helper function to construct a string based on the tags on the recipe, for simplified storage and search
def construct_tag_string(recipe):
    new_recipe_tags = ""
    new_recipe_tags += "vegetarian, " if recipe["vegetarian"] else ""
    new_recipe_tags += "vegan, " if recipe["vegan"] else ""
    new_recipe_tags += "glutenFree, " if recipe["glutenFree"] else ""
    new_recipe_tags += "veryHealthy, " if recipe["veryHealthy"] else ""
    new_recipe_tags += "cheap, " if recipe["cheap"] else ""
    new_recipe_tags += "veryPopular, " if recipe["veryPopular"] else ""
    new_recipe_tags += "sustainable, " if recipe["sustainable"] else ""
    new_recipe_tags = new_recipe_tags.strip(", ")

    return new_recipe_tags

# -----------------------------------------------------------------------------
# Background tasks
# -----------------------------------------------------------------------------
# Fetch recipes every hour while the server is active, to continously bring in
# fresh recipes from various sources (for now, only spoonacular).
@scheduler.scheduled_job('interval', seconds=3600)
def download_recipes():
    print("downloading recipes...")
    i = 0
    while os.path.exists("recipes/recipes%s.json" % i):
        i += 1

    response = sp_api.get_random_recipes(number=100)

    if not os.path.exists('recipes'):
        os.makedirs('recipes')

    with open('recipes/recipes%s.json' % i, 'w') as outfile:
        json.dump(response.json(), outfile, ensure_ascii=False, indent=2)

    print("done fetching recipes.")
    # update recipes
    update_recipes()
    print("done updating recipes.")


# Run API service
if __name__ == '__main__':
    db.create_all()
    scheduler.start()
    update_recipes()
    app.run(host='0.0.0.0', debug=False)

    # Terminate background tasks
    scheduler.shutdown()
