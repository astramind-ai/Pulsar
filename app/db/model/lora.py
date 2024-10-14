from sqlalchemy import String, Column, event, text
from sqlalchemy.orm import relationship

from app.db.model.base import Base, user_lora_association


class LoRA(Base):
    __tablename__ = "loras"
    id = Column(String, unique=True, index=True)

    name = Column(String, primary_key=True, index=True, unique=True)
    path = Column(String)
    owner = Column(String)
    image = Column(String, nullable=True)
    url = Column(String, unique=True)
    description = Column(String, nullable=True)
    base_architecture = Column(String)

    users = relationship("User", secondary=user_lora_association, back_populates="loras", lazy='selectin')
    chats = relationship("Chat", back_populates="lora", cascade="all, delete-orphan", lazy='selectin')
    completions = relationship("Completions", back_populates="lora", lazy='selectin')
    messages = relationship("Message", back_populates="lora", cascade="all, delete-orphan", lazy='selectin')


# noinspection PyProtectedMember
@event.listens_for(LoRA, 'before_update')
def receive_before_update(mapper, connection, target):
    if hasattr(target, '_original_id') and target.id != target._original_id:
        # L'ID è stato modificato, aggiorna tutte le tabelle correlate
        for table in ['chats', 'completions', 'messages']:
            stmt = text(f"UPDATE {table} SET lora_id = :new_id WHERE lora_id = :old_id")
            connection.execute(stmt, {'new_id': target.id, 'old_id': target._original_id})

        # Aggiorna anche la tabella di associazione user_lora
        stmt = text("UPDATE user_lora_association SET lora_id = :new_id WHERE lora_id = :old_id")
        connection.execute(stmt, {'new_id': target.id, 'old_id': target._original_id})


@event.listens_for(LoRA, 'load')
def receive_load(target, context):
    target._original_id = target.id
