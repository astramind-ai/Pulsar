from sqlalchemy import Column, String, Boolean, Float, event, text
from sqlalchemy.orm import relationship

from app.db.model.base import Base, user_model_association


class Model(Base):
    __tablename__ = "models"
    id = Column(String, index=True, unique=True)

    name = Column(String, primary_key=True, unique=True, index=True)
    path = Column(String)
    owner = Column(String)
    description = Column(String, nullable=True)
    tags = Column(String, nullable=True)
    image = Column(String, nullable=True)
    working = Column(Boolean, default=True)
    url = Column(String, unique=True, index=True)
    base_architecture = Column(String)
    variants = Column(String, nullable=True)

    speed_value = Column(Float, nullable=True)

    users = relationship("User", secondary=user_model_association, back_populates="models", lazy='selectin')
    chats = relationship("Chat", back_populates="model", cascade="all, delete-orphan", lazy='selectin')
    completions = relationship("Completions", back_populates="model", lazy='selectin')
    messages = relationship("Message", back_populates="model", lazy='selectin')


# noinspection PyProtectedMember
@event.listens_for(Model, 'before_update')
def receive_before_update(mapper, connection, target):
    if hasattr(target, '_original_id') and target.id != target._original_id:
        # L'ID è stato modificato, aggiorna tutte le tabelle correlate
        for table in ['chats', 'completions', 'messages']:
            stmt = text(f"UPDATE {table} SET model_id = :new_id WHERE model_id = :old_id")
            connection.execute(stmt, {'new_id': target.id, 'old_id': target._original_id})

        # Aggiorna anche la tabella di associazione user_model
        stmt = text("UPDATE user_model_association SET model_id = :new_id WHERE model_id = :old_id")
        connection.execute(stmt, {'new_id': target.id, 'old_id': target._original_id})


@event.listens_for(Model, 'load')
def receive_load(target, context):
    target._original_id = target.id
