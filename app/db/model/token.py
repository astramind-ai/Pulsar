from sqlalchemy import Column, Integer, String

from app.db.model.base import Base


class Token(Base):
    __tablename__ = "token"

    id = Column(Integer, unique=True, primary_key=True)
    access_token = Column(String, nullable=True)
    refresh_token = Column(String, nullable=True)
    url_token = Column(String, nullable=True)
