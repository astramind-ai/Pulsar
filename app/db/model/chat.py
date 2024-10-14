
from sqlalchemy import Column, Integer, String
from sqlalchemy import ForeignKey, JSON, DateTime, func
from sqlalchemy.orm import relationship

from app.db.model.base import Base


class Message(Base):
    __tablename__ = 'messages'
    id = Column(String, unique=True, primary_key=True)
    content = Column(JSON)
    user_id = Column(String, ForeignKey('users.id'))
    model_id = Column(String, ForeignKey('models.name'))
    lora_id = Column(String, ForeignKey('loras.name'), nullable=True)
    chat_id = Column(String, ForeignKey('chats.id'), nullable=True)
    completion_id = Column(String, ForeignKey('completions.id'), nullable=True)
    timestamp = Column(DateTime, default=func.now())
    version = Column(Integer, default=1)
    parent_message_id = Column(String, ForeignKey('messages.id'), nullable=True)

    # Relationships
    chat = relationship("Chat", back_populates="messages")
    previous_message = relationship("Message", remote_side=[id])
    completion = relationship("Completions", back_populates="messages", lazy='selectin')
    model = relationship("Model", back_populates="messages", lazy='selectin')
    lora = relationship("LoRA", back_populates="messages", lazy='selectin')


class Chat(Base):
    __tablename__ = "chats"
    id = Column(String, primary_key=True, unique=True, index=True)
    summary = Column(String, nullable=True)
    timestamp = Column(DateTime, onupdate=func.now(), nullable=True)

    user_id = Column(String, ForeignKey('users.id'))
    model_id = Column(String, ForeignKey('models.name'))
    lora_id = Column(String, ForeignKey('loras.name'), nullable=True)
    personality = Column(String, ForeignKey('personalities.name'), nullable=True)

    user = relationship("User", back_populates="chats")
    model = relationship("Model", back_populates="chats")
    lora = relationship("LoRA", back_populates="chats")
    messages = relationship("Message",
                            back_populates="chat",
                            cascade="all, delete-orphan",
                            lazy='selectin',
                            order_by="Message.timestamp")


class Completions(Base):
    __tablename__ = "completions"
    id = Column(String, primary_key=True, index=True)

    chat_id = Column(String, ForeignKey('chats.id'))
    user_id = Column(String, ForeignKey('users.id'))
    lora_id = Column(String, ForeignKey('loras.name'), nullable=True)
    model_id = Column(String, ForeignKey('models.name'))

    chat = relationship("Chat")
    user = relationship("User")
    lora = relationship("LoRA")
    model = relationship("Model")
    messages = relationship("Message", back_populates="completion", cascade="all, delete-orphan", lazy='selectin')
