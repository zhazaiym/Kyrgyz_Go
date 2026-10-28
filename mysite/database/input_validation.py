"""Write DTO validation delegates to the same rules as ORM persistence."""

from pydantic import BaseModel, model_validator

from mysite.database import models
from mysite.database.storage_validation import validate_storage_values


class StorageInput(BaseModel):
    @model_validator(mode='after')
    def validate_storage_and_domain(self):
        name = type(self).__name__.removesuffix('InputSchema').removesuffix('UpdateSchema')
        entity = getattr(models, name, None)
        if entity is not None:
            values = validate_storage_values(entity, self.model_dump(), self.model_fields_set)
            for key, value in values.items():
                if value != getattr(self, key):
                    setattr(self, key, value)
        return self
