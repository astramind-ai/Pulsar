import json
import uuid
from collections import defaultdict
from typing import List, Optional, Union

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..model.chat import Chat, Message
from ..model.personality import Personality
from ...utils.definitions import ALLOWED_MESSAGE_FIELDS


async def _get_chat_history(db: AsyncSession, chat_id: str, up_to_message_id: str = None):
    # Base query
    query = select(Message).where(Message.chat_id == chat_id)

    if up_to_message_id:
        # Subquery to get the timestamp of the up_to_message_id
        subquery = select(Message.timestamp).where(and_(
            Message.chat_id == chat_id,
            Message.id == up_to_message_id
        )).scalar_subquery()

        # Main query: get all messages up to and including the up_to_message_id
        query = query.where(Message.timestamp <= subquery)

    # Order by timestamp
    query = query.order_by(Message.timestamp)

    result = await db.execute(query)
    return result.scalars().all()


async def async_unpack_chat_history(
        db: AsyncSession,
        chat: Union[Chat, str],
        up_to_message_id: Optional[str] = None,
        message_ids: Optional[List[str]] = None,
        personality: Optional[Personality] = None,
        full_history: bool = False
) -> List[dict]:
    # Get the chat history
    chat_id = chat.id if isinstance(chat, Chat) else chat
    messages = await _get_chat_history(db, chat_id, up_to_message_id)

    # Unpack the messages
    return unpack_messages(messages, personality, message_ids, full_history)


async def validate_uuid(uuid_id: str):
    if len(uuid_id) != 32:
        return False
    return True


def unpack_multimodal_content(content: str) -> Union[List[dict], dict]:
    if isinstance(content, str) and content.startswith("<_MultiModalContent_>"):
        try:
            return json.loads(content[len("<_MultiModalContent_>"):])
        except json.JSONDecodeError:
            return [{"type": "text", "text": content}]
    return content  # Returns just the content if it is not multimodal


def unpack_messages(messages: List[Message], personality: Optional[Personality], message_ids: Optional[List[str]],
                    full_history: Optional[bool] = True) -> List[dict]:
    message_dict = {msg.id: msg for msg in messages}
    message_id_set = set(message_ids) if message_ids else set()

    # Group messages by their parent_message_id
    message_groups = defaultdict(list)
    for msg in messages:
        parent_id = msg.parent_message_id or uuid.uuid4().hex
        message_groups[parent_id].append(msg)

    def get_message_chain(start_msg_id: str) -> List[dict]:
        chain = []
        current_msg_id = start_msg_id

        while current_msg_id:
            msg = message_dict.get(current_msg_id)
            if not msg:
                break

            group = message_groups.get(msg.parent_message_id or uuid.uuid4().hex, [])

            if len(group) > 1 and message_ids:
                selected_msg = next((m for m in group if m.id in message_id_set), group[0])
            else:
                selected_msg = msg

            if not (personality and selected_msg != messages[-2] and selected_msg.content.get(
                    'role') == "system") and isinstance(selected_msg.content, dict):
                unpacked_msg = selected_msg.content.copy()
                unpacked_msg['id'] = selected_msg.id
                unpacked_msg['version'] = selected_msg.version
                unpacked_msg['parent_message_id'] = selected_msg.parent_message_id

                # Gestione del contenuto multimodale
                if 'content' in unpacked_msg:
                    unpacked_msg['content'] = unpack_multimodal_content(unpacked_msg['content'])

                chain.append(unpacked_msg)

            current_msg_id = selected_msg.parent_message_id

        return list(reversed(chain))  # Reverse to get chronological order

    if messages:
        if full_history:
            full_messages_list = []
            for message in messages:
                message_dict = {}
                for var in vars(message):
                    if var in ALLOWED_MESSAGE_FIELDS:
                        if var != 'content':
                            message_dict[var] = vars(message)[var]
                        else:
                            message_attr = vars(message)[var]
                            message_attr['content'] = unpack_multimodal_content(message_attr['content'])
                            message_dict.update(unpack_multimodal_content(message_attr))  # it already returns a dict
                full_messages_list.append(message_dict)
            return full_messages_list

        # Start from the last message and build the chain backwards
        last_message = messages[-1]
        return get_message_chain(last_message.id)
    else:
        return []
