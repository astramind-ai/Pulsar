import json
import re
from enum import Enum
from typing import List, Optional, Union

from jsonschema.validators import validate
from pydantic import BaseModel, constr, Field, field_validator


class Sexuality(str, Enum):
    heterosexual = "heterosexual"
    homosexual = "homosexual"
    bisexual = "bisexual"
    asexual = "asexual"
    pansexual = "pansexual"
    other = "other"


class Gender(str, Enum):
    male = "male"
    female = "female"
    non_binary = "non-binary"
    other = "other"



class PersonalitySchema(BaseModel):
    name: constr(max_length=50)
    sexuality: Sexuality
    gender: Gender
    species: constr(max_length=50)
    history: constr(max_length=500)
    description: constr(max_length=500)
    appearance: constr(max_length=500)
    personality: constr(max_length=500)
    abilities: List[constr(max_length=100)] = Field(max_length=5)
    allies: Optional[List[constr(max_length=150)]] = Field(default=None, max_length=5)
    enemies: Optional[List[constr(max_length=150)]] = Field(default=None, max_length=5)

    @field_validator('*', mode='before')
    def clean_string_values(cls, v):
        if isinstance(v, str):
            return v.strip("'\"")
        elif isinstance(v, list):
            return [item.strip("'\"") if isinstance(item, str) else item for item in v]
        return v

    def to_dict(self):
        return {
            key: (value.value if isinstance(value, Enum) else value)
            for key, value in self.model_dump(exclude_unset=True).items()
        }

    @classmethod
    def from_form(cls, form_data: dict):
        form_data = clean_and_validate_data(form_data, cls.model_json_schema())
        # Convert string lists to actual lists
        list_fields = ['allies', 'enemies']
        for field in list_fields:
            if field in form_data and isinstance(form_data[field], str):
                form_data[field] = [item.strip() for item in form_data[field].split(',') if item.strip()]

        # Convert string to enum for sexuality
        if 'sexuality' in form_data:
            form_data['sexuality'] = Sexuality(form_data['sexuality'])
        elif 'gender' in form_data:
            form_data['gender'] = Gender(form_data['gender'])

        return cls(**form_data)

def clean_and_validate_data(input_data: Union[str, dict], schema: dict):
    if isinstance(input_data, str):
        try:
            # Prova a parsare il JSON
            data = json.loads(input_data)
        except json.JSONDecodeError:
            try:
                # Prova a correggere manualmente
                cleaned = input_data.replace("'", '"')
                cleaned = re.sub(r'(\w+):', r'"\1":', cleaned)
                cleaned += "}"
                data = json.loads(cleaned)
            except json.JSONDecodeError:
                # Se il parsing fallisce, prova a correggere manualmente
                cleaned = input_data.replace("'", '"')
                cleaned = re.sub(r'(\w+):', r'"\1":', cleaned)
                data = json.loads(cleaned)
    else:
        data = input_data

    # Assicurati che tutti i campi richiesti siano presenti
    for field in schema['required']:
        if field not in data:
            data[field] = "" if field not in ['allies', 'enemies', 'abilities'] else []

    # Rimuovi campi non necessari
    allowed_fields = list(schema['properties'].keys())
    data = {k: v for k, v in data.items() if k in allowed_fields}

    validate(instance=data, schema=schema)

    return data
