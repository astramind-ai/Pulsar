import json

from starlette.responses import StreamingResponse
from starlette.types import Send

from app.db.model.chat import Message
from app.utils.log import setup_custom_logger

logger = setup_custom_logger(__name__)

class WrappedStreamingResponse(StreamingResponse):
    def __init__(self, content, db_session, chat, response_id, parent_message_id, model_id, *args,
                 **kwargs):
        self.db_session = db_session
        self.chat = chat
        self.response_id = response_id
        self.parent_id = parent_message_id
        self.model_id = model_id
        self.accumulated_content = ""
        super().__init__(content, *args, **kwargs)

    def substitute_id(self, chunk):
        if not isinstance(chunk, str):
            return chunk
        parts = chunk.split("data: ")
        if len(parts) < 2:
            return chunk
        json_part = parts[1]
        if json_part.strip() == "[DONE]":
            return chunk
        try:
            data = json.loads(json_part)
            data['chat_id'] = self.chat.id
            data['id'] = self.response_id
            updated_json_string = json.dumps(data)
            return f"data: {updated_json_string}\n\n"
        except json.JSONDecodeError:
            return chunk

    async def stream_response(self, send: Send) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": self.status_code,
                "headers": self.raw_headers,
            }
        )
        try:
            async for chunk in self.body_iterator:
                chunk = self.substitute_id(chunk)
                if not isinstance(chunk, bytes):
                    chunk = chunk.encode(self.charset)

                decoded_chunk = chunk.decode(self.charset)
                self.accumulate_content(decoded_chunk)

                await send({"type": "http.response.body", "body": chunk, "more_body": True})
        except Exception as e:
            logger.error(f"Stream interrupted: {str(e)}")
        finally:
            # Save the last message
            await self.save_message_to_db()
            await send({"type": "http.response.body", "body": b"", "more_body": False})

    def accumulate_content(self, chunk):
        if 'INTERNAL-' in chunk:
            return  # This is done in order to not log the internal process sta
        if chunk.startswith("data: "):
            content = chunk[6:].strip()  # Remove "data: " prefix
            if content != "[DONE]":
                try:
                    data = json.loads(content)
                    if 'choices' in data and len(data['choices']) > 0:
                        delta = data['choices'][0].get('delta', {})
                        if 'content' in delta:
                            self.accumulated_content += delta['content']
                except json.JSONDecodeError:
                    logger.error(f"Error parsing JSON content: {content}")
                    pass  # Ignore malformed JSON

    async def save_message_to_db(self):
        async with self.db_session.begin():
            try:
                if self.accumulated_content:
                        new_message = Message(
                            chat=self.chat,
                            id=self.response_id,
                            parent_message_id=self.parent_id,
                            model_id=self.model_id,
                            content={"role": "assistant", "content": self.accumulated_content}
                        )
                        self.db_session.add(new_message)
            except Exception as e:
                print(f"Error saving message to database: {str(e)}")
                await self.db_session.rollback()
                raise
