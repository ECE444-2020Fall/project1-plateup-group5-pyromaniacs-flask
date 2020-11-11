from initializer import ma


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
