"""
Passenger entrypoint for thealphanova.com/aegis.

cPanel's "Setup Python App" (LiteSpeed LSAPI) speaks WSGI, but this is a FastAPI
(ASGI) app. We bridge with a tiny, fully-buffered WSGI->ASGI adapter instead of
a2wsgi: a2wsgi's thread/event-loop streaming model hangs under LiteSpeed's LSAPI
(the app imports in 0.4s but requests never return). This adapter runs the ASGI
app to completion in a fresh event loop per request and returns the whole
response as one bytes object — no threads, no streaming — which LSAPI handles
reliably. SCRIPT_NAME is mapped to ASGI root_path so routing works under /aegis.
"""
import os
import sys
import asyncio

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import app as _asgi_app


def _build_scope(environ):
    headers = []
    for key, val in environ.items():
        if key.startswith("HTTP_"):
            name = key[5:].replace("_", "-").lower().encode("latin1")
            headers.append((name, val.encode("latin1")))
    if environ.get("CONTENT_TYPE"):
        headers.append((b"content-type", environ["CONTENT_TYPE"].encode("latin1")))
    if environ.get("CONTENT_LENGTH"):
        headers.append((b"content-length", environ["CONTENT_LENGTH"].encode("latin1")))

    root_path = environ.get("SCRIPT_NAME", "")
    path_info = environ.get("PATH_INFO", "")
    full_path = (root_path + path_info) or "/"

    try:
        port = int(environ.get("SERVER_PORT") or 0)
    except ValueError:
        port = 0

    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.1"},
        "http_version": environ.get("SERVER_PROTOCOL", "HTTP/1.1").split("/")[-1],
        "method": environ.get("REQUEST_METHOD", "GET"),
        "scheme": environ.get("wsgi.url_scheme", "http"),
        "path": full_path,
        "raw_path": full_path.encode("latin1"),
        "query_string": environ.get("QUERY_STRING", "").encode("latin1"),
        "root_path": root_path,
        "headers": headers,
        "server": (environ.get("SERVER_NAME", ""), port),
        "client": (environ.get("REMOTE_ADDR", ""), 0),
    }


def _read_body(environ):
    try:
        length = int(environ.get("CONTENT_LENGTH") or 0)
    except ValueError:
        length = 0
    if length <= 0:
        return b""
    return environ["wsgi.input"].read(length)


_REASON = {
    200: "OK", 201: "Created", 204: "No Content", 301: "Moved Permanently",
    302: "Found", 304: "Not Modified", 400: "Bad Request", 401: "Unauthorized",
    403: "Forbidden", 404: "Not Found", 405: "Method Not Allowed",
    422: "Unprocessable Entity", 500: "Internal Server Error",
    503: "Service Unavailable",
}


def application(environ, start_response):
    scope = _build_scope(environ)
    body = _read_body(environ)
    state = {"status": 500, "headers": [], "body": bytearray()}

    async def run():
        request_sent = False

        async def receive():
            nonlocal request_sent
            if not request_sent:
                request_sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.disconnect"}

        async def send(message):
            mtype = message["type"]
            if mtype == "http.response.start":
                state["status"] = message["status"]
                state["headers"] = message.get("headers", [])
            elif mtype == "http.response.body":
                state["body"].extend(message.get("body", b""))

        await _asgi_app(scope, receive, send)

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(run())
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass
        loop.close()

    status_line = "{} {}".format(state["status"], _REASON.get(state["status"], "Status"))
    out_headers = [
        (k.decode("latin1"), v.decode("latin1")) for k, v in state["headers"]
    ]
    start_response(status_line, out_headers)
    return [bytes(state["body"])]
