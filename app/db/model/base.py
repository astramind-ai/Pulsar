from sqlalchemy import Table, Column, String, ForeignKey
from sqlalchemy.orm import declarative_base

Base = declarative_base()

# Many-to-Many between User and X
user_lora_association = Table('user_lora_association', Base.metadata,
                              Column('user_id', String, ForeignKey('users.id'), primary_key=True),
                              Column('lora_id', String, ForeignKey('loras.id'), primary_key=True)
                              )

user_model_association = Table('user_model_association', Base.metadata,
                               Column('user_id', String, ForeignKey('users.id'), primary_key=True),
                               Column('model_id', String, ForeignKey('models.id'), primary_key=True)
                               )

user_personality_association = Table('user_personality_association', Base.metadata,
                                     Column('user_id', String, ForeignKey('users.id'), primary_key=True),
                                     Column('personality_id', String, ForeignKey('personalities.id'), primary_key=True)
                                     )

user_personas_association = Table('user_personas_association', Base.metadata,
                                  Column('user_id', String, ForeignKey('users.id'), primary_key=True),
                                  Column('personas_id', String, ForeignKey('personas.id'), primary_key=True)
                                  )