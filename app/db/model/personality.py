from sqlalchemy import ForeignKey, Column, String, JSON
from sqlalchemy.orm import relationship

from app.db.model.base import Base, user_personality_association


class Personality(Base):
    __tablename__ = "personalities"
    id = Column(String, primary_key=True, unique=True, index=True)

    name = Column(String, unique=True, index=True)
    description = Column(String)
    image = Column(String)
    # describe_scene = Column(Boolean)
    owner = Column(String)
    pre_prompt = Column(JSON)

    users = relationship("User", secondary=user_personality_association, back_populates="personalities",
                         lazy='selectin')
