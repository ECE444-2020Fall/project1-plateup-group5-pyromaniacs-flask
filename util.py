import json
import os

from emailservice import send_email_as_plateup
from initializer import db, login_manager
from models import User, Recipe, Instruction


# -----------------------------------------------------------------------------
# Utility functions
# -----------------------------------------------------------------------------
# Flattens list into a string list
def flat_list(ls):
    return ["%s" % v.lower() for v in ls]


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

    with open('welcome_email.html', 'r') as file:
        template = file.read()
        body = template % (email, str(user.id), password)

    return send_email_as_plateup(receipient, subject, body)


# Function to update the recipes read in from the json files stored in
# relative path /recipes to the database in the format expected by the
# various recipe routes.
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
                        recipe["readyInMinutes"]) \
                        if "readyInMinutes" in recipe else 60
                    new_recipe_cost = recipe["pricePerServing"]
                    new_recipe_preview_text = recipe["summary"]
                    new_recipe_preview_media_url = recipe["image"]
                    new_recipe_tags = construct_tag_string(recipe)

                    if new_recipe_time_min > 60:
                        new_recipe_time_h = new_recipe_time_h + \
                            int(new_recipe_time_min/60)
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

                    update_instructions(
                        new_recipe.id,
                        recipe["analyzedInstructions"][0]["steps"]
                    )
                    db.session.add(new_recipe)
                    db.session.commit()

            except Exception as ex:
                print("One recipe not updated due to missing \
                    fields or other error: %s \n" % ex)
                print("skipping...")

    print("done updating recipes.")


# Helper function to update the instructions for each recipe into
# the database. Pulled out of the update_recipes function for better
# modularity and readability.
def update_instructions(recipe_id, instructions):
    for step in instructions:
        new_instruction_step_num = step["number"]
        new_instruction_step_instruction = step["step"]
        new_instruction_ingredients = json.dumps([{
            "name": ingredient["name"],
            "img":"https://spoonacular.com/cdn/ingredients_250x250/"
            + ingredient["image"]
        } for ingredient in step["ingredients"]])
        new_instruction_equipment = json.dumps([{
            "name": equipment["name"],
            "img":"https://spoonacular.com/cdn/equipment_250x250/"
            + equipment["image"]
            } for equipment in step["equipment"]])

        new_instruction = Instruction(
            recipe_id,
            new_instruction_step_num,
            new_instruction_step_instruction,
            new_instruction_equipment,
            new_instruction_ingredients
        )

        db.session.add(new_instruction)

    db.session.commit()


# Helper function to construct a string based on the tags on the recipe,
# for simplified storage and search
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
