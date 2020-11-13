import random
import json
import operator

from flask import jsonify, request, Response
from flask_login import current_user, login_user, login_required, logout_user
from flask_restx import fields, Resource
from werkzeug.security import check_password_hash

from initializer import api, app, db, scheduler
from models import User, Recipe, Instruction, ShoppingList, Inventory
from util import flat_list, send_welcome_email
from background import download_recipes
from schemas import UserSchema, RecipeSchema, InstructionSchema, \
    EquipmentSchema, IngredientSchema

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
recipeR = api.namespace('recipe', description='Preview of recipes')
recipeDetailR = api.namespace(
    'recipeDetail', description='Instruction level details for recipes')
inventoryR = api.namespace(
    'inventory', description='User inventory operations')
shoppingR = api.namespace(
    'shopping', description='User shopping list operations')

# -----------------------------------------------------------------------------
# Marshmallow schemas
#
# Initialize schemas (many = True auto formats several objects into an array)
# -----------------------------------------------------------------------------
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

    @userR.doc(description="Register a new user to the system with \
        complete information.")
    @userR.expect(resource_fields, validate=True)
    def post(self):
        name = request.json['name']
        email = request.json['email'].lower()
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

        # Sends welcome email to user, if it doesn't work, then the email
        # address is likely invalid
        if not send_welcome_email(email, new_user, password):
            return Response(
                "Mail not sent! Invalid email or server issues, \
                user not saved.",
                status=400
            )

        db.session.add(new_user)
        db.session.commit()

        return user_schema.jsonify(new_user)

    '''
        HTTP DELETE /user
        Deletes all the users in the database.
        (same as resetting database for users)
        Used only in testing, not production friendly.
    '''

    @userR.doc(description="WARNING: Delete all user information stored in \
        the database.")
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
        A hash of the password is stored for security purposes.
    '''

    @loginR.doc(description="Logging a user into the system and authenticating for \
        access to deeper APIs.")
    @loginR.expect(resource_fields, validate=True)
    def post(self):
        email = request.json['email'].lower()
        password = request.json['password']
        user = User.query.filter_by(email=email).first()

        if user is not None and check_password_hash(user.password, password):
            login_user(user)
            return user_schema.jsonify(user)

        return Response(
            "Login failed! Please confirm that the email and password \
                are correct.",
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


# Retrieve the recipe instruction step by step with corresponding
# equipment and ingredients
@recipeR.route('/<id>', methods=['GET', 'POST'])
class RecipeDetailAPI(Resource):
    resourceFields = recipeR.model('Information to get recipe instruction', {
        'recipe_id': fields.String,
        'step_num': fields.Integer,
        'step_instruction': fields.String,
        'ingredients': fields.String,
        'equipment': fields.String
    })

    '''
        Database handlers
    '''

    def __get_recipe_instructions_by_id(self, recipe_id):
        recipe_found = db.session.query(Instruction).filter(
            Instruction.recipe_id.like(recipe_id)).all()
        return recipe_found

    def __get_recipe_preview_by_id(self, recipe_id):
        recipe_found = db.session.query(Recipe).filter(
            Recipe.id.like(recipe_id)).all()
        return recipe_found

    '''
        Sort recipe instruction list by step
    '''

    def __sort_by_step(self, unsorted_list):
        sorted_list = sorted(
            unsorted_list, key=operator.attrgetter("step_num"), reverse=False)
        return sorted_list

    '''
        Check if a conflict instruction existed
        Two instructions are conflicted if they have
        same recipe id and step number
    '''

    def __not_exist_instruction(self, recipe_instruction_object):
        instruction_list = self.__get_recipe_instructions_by_id(
            recipe_instruction_object.recipe_id)
        for i in range(len(instruction_list)):
            if instruction_list[i].step_num == \
                    recipe_instruction_object.step_num:
                return False
        return True

    '''
        Organize the return object.
        For each step it should have instruction, ingredient and equipment.
    '''

    def __organize_return_object(self, recipe_instruction_list):
        dict_list = []
        for instructions in recipe_instruction_list:
            equipment_list = json.loads(instructions.equipment)
            ingredient_list = json.loads(instructions.ingredient)
            return_ingredient = ingredients_schema.dump(equipment_list)
            return_equipment = equipments_schema.dump(ingredient_list)
            return_dict = {
                "step_instruction": instructions.step_instruction,
                "ingredients": return_ingredient,
                "equipment": return_equipment
            }

            dict_list.append(return_dict)
        return dict_list

    '''
        HTTP GET /recipe/<recipe_id>
        Get the corresponding recipe instruction and preview from database.
        Organization of return format:
        {
            "recipe_preview":{
            ...
            }
            "recipe_instruction":[
                {
                    "ingredient":[
                        {
                            "name": ...
                            "img": ...
                        }
                        ...
                    ]
                    "equipment":[
                        {
                            "name": ...
                            "img": ...
                        }
                        ...
                    ]
                    "insturction": ...
                }
                ...(next step)
            ]
        }
    '''

    @login_required
    def get(self, id):
        recipe_id = id

        recipe_instruction_list_unsorted = \
            self.__get_recipe_instructions_by_id(recipe_id)

        recipe_instruction_list_sorted = \
            self.__sort_by_step(recipe_instruction_list_unsorted)

        recipe_preview = self.__get_recipe_preview_by_id(id)

        if len(recipe_instruction_list_sorted) == 0:
            return Response("recipe instruction not found!", status=500)

        if len(recipe_preview) == 0:
            return Response("recipe preview not found!", status=500)

        return_step_list = \
            self.__organize_return_object(recipe_instruction_list_sorted)
        return_preview = recipe_schema.dump(recipe_preview[0])
        return_object = {
            "recipe_preview": return_preview,
            "recipe_instruction": return_step_list
        }

        return jsonify(return_object)

    '''
        HTTP POST /recipe/<recipe_id>
        Add one step of recipe instruction including equipement and ingredients
        to the database. It will check if there is a conflict instruction that has
        same description exist. If yes, it will not insert the new instruction.
    '''

    @recipeR.doc(description="Insert recipe instruction to database")
    @recipeR.expect(resourceFields, validate=True)
    @login_required
    def post(self, id):
        new_instruction_recipe_id = request.json["recipe_id"]
        new_instruction_step_num = request.json["step_num"]
        new_instruction_step_instruction = request.json["step_instruction"]

        new_instruction_ingredients = request.json["ingredients"]
        new_instruction_equipment = request.json["equipment"]

        new_instruction_description = Instruction(
            new_instruction_recipe_id,
            new_instruction_step_num,
            new_instruction_step_instruction,
            new_instruction_ingredients,
            new_instruction_equipment
        )

        if self.__not_exist_instruction(new_instruction_description):
            db.session.add(new_instruction_description)

        db.session.commit()

        return Response("recipe instruction inserted!", status=200)


# Retrieve recipe based on the search keyword and filters
# Add recipe to the database
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
    random_pick = False

    '''
        Merge two list together without duplication
    '''

    def __merge_list(self, old_list, new_list):
        in_old = set(old_list)
        in_new = set(new_list)
        in_new_not_old = in_new - in_old
        merged_list = old_list + list(in_new_not_old)
        return merged_list

    '''
        Database handler functions
    '''

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

    '''
        Create searching priority by keyword list
        Ex: If user search "Beef"
        Then "Beef" has higher priority than "rosted Beef"
    '''

    def __search_keyword_list_for_search_by_name(self, keyword):
        keyword_list = []
        keyword_list.append("% " + keyword + " %")
        keyword_list.append("%" + keyword + " %")
        keyword_list.append("% " + keyword + "%")
        keyword_list.append("%" + keyword + "%")
        return keyword_list

    def __search_keyword_list_for_search_by_ingredient(self, keyword):
        keyword_list = []
        keyword_list.append("%\"" + keyword + "\"%")
        keyword_list.append("%\"" + keyword + " %")
        keyword_list.append("%" + keyword + "\"%")
        keyword_list.append("% " + keyword + " %")
        keyword_list.append("%" + keyword + " %")
        keyword_list.append("% " + keyword + "%")
        keyword_list.append("%" + keyword + "%")
        return keyword_list

    '''
        Try to search recipe by name, tag and ingredient
    '''

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
        # search by both origin case and lower case, origin case has
        # higher priority.
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
    Filter Recipe by cost and time
    '''

    def __filter_by_cost(self, recipe_list, filter_cost):
        recipe_list = [
            recipe for recipe in recipe_list
            if recipe.cost <= float(filter_cost)
        ]
        return recipe_list

    def __filter_by_time(self, recipe_list, filter_time_h, filter_time_min):
        filter_time_h = int(filter_time_h)
        filter_time_min = int(filter_time_min)
        recipe_list_same_h = [
            recipe for recipe in recipe_list
            if recipe.time_h == int(filter_time_h)
        ]
        recipe_list_same_h = [
            recipe for recipe in recipe_list_same_h
            if recipe.time_min <= int(filter_time_min)
        ]
        recipe_list = [
            recipe for recipe in recipe_list
            if recipe.time_h < int(filter_time_h)
        ]
        recipe_list = recipe_list_same_h + recipe_list
        return recipe_list

    '''
        Get ingredient name from recipe preview
    '''

    def __get_ingredient_from_recipe(self, recipe):
        ingredient_json = recipe.ingredients
        ingredient_list = json.loads(ingredient_json)
        name_list = ingredient_list.keys()
        return name_list

    '''
        Check if all ingredient in a recipe is found in user's inventory
    '''

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

    '''
        Filter recipe by ingredient in user's inventory
    '''

    def __filter_by_ingredients(self, recipe_list, user_id):
        new_recipe_list = []
        for recipe in recipe_list:
            ingredients_name_list = self.__get_ingredient_from_recipe(recipe)

            if self.__check_ingredient_in_inventory(
                    ingredients_name_list, user_id
            ):
                new_recipe_list.append(recipe)
        return new_recipe_list

    '''
        Main filter function, filter recipe by cost, time,
        and ingredient in user's inventory
    '''

    def __filter_recipe(self, recipe_list, filter_cost, filter_time_h,
                        filter_time_min, filter_has_ingredient, user_id):
        if len(recipe_list) == 0:
            self.random_pick = True
            recipe_list = db.session.query(Recipe).all()

        if filter_cost is not None:
            recipe_list = self.__filter_by_cost(recipe_list, filter_cost)
        if filter_time_h is not None and filter_time_min is not None:
            recipe_list = self.__filter_by_time(
                recipe_list, filter_time_h, filter_time_min)
        if filter_has_ingredient:
            recipe_list = self.__filter_by_ingredients(recipe_list, user_id)

        return recipe_list

    '''
        HTTP POST /recipe
        
        Add a recipe to the database.
        Automatically correct the input time for min>60
    '''

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
            new_recipe_time_h = new_recipe_time_h + int(new_recipe_time_min / 60)
            new_recipe_time_min = new_recipe_time_min % 60

        new_recipe = Recipe(
            new_recipe_name,
            new_recipe_ingredients,
            new_recipe_time_h,
            new_recipe_time_min,
            new_recipe_cost,
            new_recipe_preview_text,
            new_recipe_preview_media_url,
            new_recipe_tags
        )

        db.session.add(new_recipe)
        db.session.commit()
        return Response("recipe inserted!", status=200)

    '''
        HTTP GET /recipe/recipe?<Search><Filter_time_h><Filter_time_min><Filter_cost>
        <Filter_has_ingredients><Page><Limit><user_id>
        Example:
        http://127.0.0.1:5000/recipe?Search=meal&Filter_time_h=10&ilter_time_min=0&\
        Filter_cost=10000&Page=0&Limit=2&user_id=test_user
        
        Search the recipe by Name. Filter the recipe by the time and
        cost limit. Also, it will filter out the recipes that requires
        ingredient that is not in user's inventory. Then return information
        for the recipes
         
        If no recipe pass the filter and search, it will randomly pick
        some recipe that match the filter from database and tell
        the front end that the result is randomly picked up.
        
        return format:
        {
            recipe: (recipe information)
            is_random: True/False
        }
    '''

    @recipeR.doc(description="Get recipe preview json by name and filter",
                 params={
                     'Search':
                         {
                             'description': 'search by an ingredient, \
                                recipe name, or tag',
                             'type': 'string'
                         },
                     'Filter_time_h':
                         {
                             'description': 'filter by max hours',
                             'type': 'int'
                         },
                     'Filter_time_min':
                         {
                             'description': 'filter by max minutes (<60)',
                             'type': 'int'
                         },
                     'Filter_cost':
                         {
                             'description': 'filter by max cost',
                             'type': 'float'
                         },
                     'Filter_has_ingredients':
                         {
                             'description': 'filter by if user has all the \
                                appropriate ingredients',
                             'type': 'boolean'
                         },
                     'Limit':
                         {
                             'description': 'number of recipes to return',
                             'type': 'int'
                         },
                     'Page':
                         {
                             'description': 'page number determines range of data \
                                returned: \
                                [page x limit -> page x limit + limit]',
                             'type': 'int'
                         },
                     'user_id':
                         {
                             'description': 'user id for checking the user inventory \
                                    returned: \
                                    [page x limit -> page x limit + limit]',
                             'type': 'int'
                         }
                 })
    @login_required
    def get(self):
        # get params
        recipe_list = []
        search_query = request.args.get('Search')
        filter_time_h = request.args.get('Filter_time_h')
        filter_time_min = request.args.get('Filter_time_min')
        filter_cost = request.args.get('Filter_cost')
        filter_has_ingredients = \
            bool(request.args.get('Filter_has_ingredients')) \
                if request.args.get('Filter_has_ingredients') else False
        limit = int(request.args.get('Limit')
                    ) if request.args.get('Limit') else 20
        page = int(request.args.get('Page')) if request.args.get('Page') else 0
        user_id = request.args.get(
            'user_id') if request.args.get('user_id') else ""

        self.random_pick = False
        # get list
        recipe_list_name = []
        recipe_list_ingredient = []
        recipe_list_tags = []

        if search_query is not None:
            recipe_list_name = self.__search_for_recipes_by_name(search_query)
            recipe_list_ingredient = self.__search_for_recipes_by_ingredient(
                search_query)
            recipe_list_tags = self.__search_for_recipes_by_tags(search_query)

        recipe_list = self.__merge_list(
            recipe_list_name, recipe_list_ingredient)
        recipe_list = self.__merge_list(recipe_list, recipe_list_tags)

        recipe_list = self.__filter_recipe(
            recipe_list,
            filter_cost,
            filter_time_h,
            filter_time_min,
            filter_has_ingredients,
            user_id
        )

        if self.random_pick:
            recipe_list = random.sample(
                recipe_list, k=min(len(recipe_list), int(limit)))
            page = 0

        recipe_list = recipe_list[limit * page:limit * page + limit]

        return_result = recipes_schema.dump(recipe_list)

        return_dict = {"recipes": return_result, "is_random": self.random_pick}
        return jsonify(return_dict)


# The recipe checker route performs the function of validating whether
# or not a user has enough ingredients in their inventory to cook the
# specified recipe.
@recipeR.route('/<recipe_id>/check/<user_id>', methods=['GET'])
class RecipeInventoryCheckerAPI(Resource):
    '''
    HTTP GET /recipe/<recipe_id>/check/<user_id>

    This API call does one of two things:
    1. If the user has all the required ingredients for the recipe,
    it will deduct the ingredients from their inventory.
    2. If the user doesn't have all the required ingredients, it will
    check for the missing ingredients and add them to the user's shopping list.

    In both cases, it is up to the client app to decide how to handle it.
    In case 1, the app should allow users to proceed to cooking.
    In case 2, the app should remind users to buy the required ingredients,
    or allow a manual override to continue cooking anyways.
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
                "unit": required_res[ingredient_name].split()[1]
                if len(required_res[ingredient_name].split()) > 1 else ""
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
                    return Response(
                        "Bad unit match while checking ingredient \
                        requirements for recipe.",
                        status=400
                    )
                if inventory[entry]['quantity'] - \
                        required[entry]['quantity'] >= 0:
                    inventory[entry]['quantity'] -= required[entry]['quantity']
                else:
                    has_missing = True
                    new_entry = ShoppingList(
                        user_id, entry,
                        required[entry]['quantity'] -
                        inventory[entry]['quantity'],
                        inventory[entry]['quantity']
                    )
                    db.session.add(new_entry)
            else:
                has_missing = True
                new_entry = ShoppingList(
                    user_id, entry,
                    required[entry]['quantity'],
                    required[entry]['unit']
                )
                db.session.add(new_entry)

        if has_missing:
            db.session.commit()
            return Response(
                "Not enough ingredients, added to shopping list",
                status=200
            )

        for entry in inventory:
            inventory_entry = Inventory.query.get((user_id, entry))
            if inventory[entry]['quantity'] != 0:
                inventory_entry.quantity = inventory[entry]['quantity']
            else:
                db.session.delete(inventory_entry)

        db.session.commit()

        return Response(
            "Inventory updated, enough ingredients to proceed!",
            status=200
        )


# The inventory route is used for getting and setting the user's existing
# stock of groceries, which is referred to as the user's inventory.
@inventoryR.route('/<user_id>', methods=['GET', 'POST'])
class InventoryAPI(Resource):
    '''
        Resource model definitions for the inventory details required to
        update a user's inventory. It is defined in three components to
        clarify the nested structure.

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

    Updates the user's current inventory, given an input formatted as depicted
    in the resource field "inventory_fields" documentation.

    Returns the updated inventory, which should be the same as the posted
    document less any errors.
    '''

    @inventoryR.doc(description="Posting a new or updated version of the \
        user's inventory.")
    @inventoryR.expect(inventory_fields, validate=True)
    @login_required
    def post(self, user_id):
        inventory = request.json['inventory']
        inventory_res = Inventory.query.filter_by(user_id=user_id).delete()

        for entry_name in inventory:
            new_entry = Inventory(
                user_id, entry_name,
                inventory[entry_name]["qty"],
                inventory[entry_name]["unit"]
            )
            db.session.add(new_entry)

        db.session.commit()

        inventory_res = Inventory.query.filter_by(user_id=user_id).all()
        inventory = {}

        for entry in inventory_res:
            inventory[entry.ingredient_name] = {
                "qty": entry.quantity, "unit": entry.unit}

        response = {"inventory": inventory}

        return jsonify(response)


# The shopping route is used in a similar manner as the inventory route,
# for getting and setting the user's shopping list.
@shoppingR.route('/<user_id>', methods=['GET', 'POST'])
class ShoppingListAPI(Resource):
    '''
        Resource model definitions for the inventory details required
        to update a user's shopping list. It is defined in three components
        to clarify the nested structure. Deliberately formatted similarly to
        inventory as these two are made to be easily transferrable
        (shopping list > inventory and vice versa).

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

    Returns the user's current shopping list formatted as depicted in the
    resource field "shopping_fields" documentation.
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

    Updates the user's current shopping list, given an input formatted
    as depicted in the resource field "shopping_fields" documentation.

    Returns the updated shopping list, which should be the same as the
    posted document less any errors.
    '''

    @shoppingR.doc(description="Posting a new or updated version of the \
        user's shopping list.")
    @shoppingR.expect(shopping_fields, validate=True)
    @login_required
    def post(self, user_id):
        shopping = request.json['shopping']
        shopping_res = ShoppingList.query.filter_by(user_id=user_id).delete()

        for entry_name in shopping:
            new_entry = ShoppingList(
                user_id, entry_name,
                shopping[entry_name]["qty"],
                shopping[entry_name]["unit"]
            )
            db.session.add(new_entry)

        db.session.commit()

        shopping_res = ShoppingList.query.filter_by(user_id=user_id).all()
        shopping = {}

        for entry in shopping_res:
            shopping[entry.ingredient_name] = {
                "qty": entry.quantity, "unit": entry.unit}

        response = {"shopping": shopping}

        return jsonify(response)


# The shopping flash root that pushes all the user's shopping list items
# into their inventory, assuming that the user has purchased all the
# required ingredients.
# TODO: expand flash functionality to allow partial flashes
@shoppingR.route('/flash', methods=['POST'])
class ShoppingFlashToInventoryAPI(Resource):
    '''
    The only field required is the user id, but used as a post to follow REST
    protocols as this endpoint updates the data, not suitable for get. More
    param can be more easily added in the future with a defined resource model.
    '''
    resource_fields = shoppingR.model('User', {
        'user_id': fields.String,
    })

    '''
    HTTP {POST} /shopping/flash

    Updates the user's current inventory based on the items in the
    shopping list.

    For items that don't exist, new items are created in the user's inventory.
    For items that already exist, their quantities are modified.

    Returns the updated user inventory.
    '''

    @inventoryR.doc(description="Push the user's shopping list to the \
        user's inventory.")
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
                    return Response(
                        "Bad unit match while flashing to inventory.",
                        status=400
                    )
                inventory_entry.quantity = \
                    inventory_entry.quantity + entry.quantity

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


# Run API service
if __name__ == '__main__':
    db.create_all()
    # download_recipes() # Only necessary if not enough recipes
    scheduler.start()

    app.run(host='0.0.0.0')

    # Terminate background tasks
    scheduler.shutdown()
