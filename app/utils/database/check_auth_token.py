import json

from httpx import Response

from app.db.tokens.db_token import set_access_token, set_refresh_token, set_url_token


async def check_if_token_in_response(db, response):
    response.headers.pop("content-length", None)
    try:
        # Attempt to parse the response as JSON
        json_content = response.json()

        # Update and remove tokens if present in the JSON part of the response
        if 'access_token' in json_content:
            await set_access_token(json_content['access_token'], db)
        if 'refresh_token' in json_content:
            await set_refresh_token(json_content['refresh_token'], db)
        if 'url_token' in json_content:
            await set_url_token(json_content['url_token'], db)

        json_content.pop('access_token', None)
        json_content.pop('refresh_token', None)
        json_content.pop('url_token', None)

        return Response(content=json.dumps(json_content),
                        status_code=response.status_code, headers=dict(response.headers))
    except json.JSONDecodeError:
        # If response is not JSON, return it as-is
        return Response(content=response.text,
                        status_code=response.status_code, headers=dict(response.headers))
