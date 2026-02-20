from fastapi import Request


def get_request_user(request: Request) -> str:
    header_user = (request.headers.get("x-hb-user") or "").strip()
    if header_user:
        return header_user
    return "name@zalaris.com"
