from sqlalchemy import Column, String
from sqlalchemy.orm import relationship

from app.db.model.base import Base, user_model_association, user_personality_association, user_lora_association


class User(Base):
    __tablename__ = 'users'
    id = Column(String, unique=True, primary_key=True)
    name = Column(String, unique=True, index=True)
    image = Column(String, nullable=True)
    last_lora = Column(String, nullable=True)
    last_model = Column(String, nullable=True)

    chats = relationship("Chat", back_populates="user", cascade="all, delete-orphan", lazy='selectin')
    personalities = relationship("Personality", secondary=user_personality_association, back_populates="users",
                                 lazy='selectin')
    models = relationship("Model", secondary=user_model_association, back_populates="users", lazy='selectin')
    loras = (relationship("LoRA", secondary=user_lora_association, back_populates="users", lazy='selectin'))
    personas = relationship("Persona", back_populates="users", lazy='selectin')
