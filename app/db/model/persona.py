from sqlalchemy import ForeignKey, Column, String
from sqlalchemy.orm import relationship

from app.db.model.base import Base, user_personas_association


class Persona(Base):
    __tablename__ = "personas"
    id = Column(String, unique=True, index=True)
    user_username = Column(String, ForeignKey('users.name'))
    name = Column(String, primary_key=True, unique=True, index=True)
    owner = Column(String)
    description = Column(String)
    personality_id = Column(String, ForeignKey('personalities.id'))
    lora_id = Column(String, ForeignKey('loras.id'), nullable=True)
    model_id = Column(String, ForeignKey('models.id'))

    image = Column(String)

    model = relationship("Model")
    lora = relationship("LoRA")
    personality = relationship("Personality")
    users = relationship("User", secondary=user_personas_association, back_populates="personas", lazy='selectin')
