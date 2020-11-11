import os
import json
from initializer import scheduler, sp_api
from util import update_recipes


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
