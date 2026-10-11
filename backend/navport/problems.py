"""Error responses in the standard HTTP API format: RFC 9457 Problem Details.

Every error this API returns has the same shape and media type, so a client
can handle all of them with one code path:

    HTTP/1.1 400 Bad Request
    Content-Type: application/problem+json

    {
      "type": "about:blank",
      "title": "Bad Request",
      "status": 400,
      "detail": "departure must be a 4-character ICAO code, e.g. KJFK — got 'K'",
      "instance": "/api/v1/briefings"
    }

`title` is always the standard phrase for the status code; `detail` is the
human-readable explanation of this particular occurrence; `instance` is the
path that produced it. `type: about:blank` is the RFC's way of saying the
status code itself is the problem type — there are no NavPort-specific error
categories worth inventing URIs for. Extra members (`retry_after_seconds` on a
429) are allowed by the RFC as extensions.

`detail` only ever carries text written to be shown to a caller. Exceptions
nobody anticipated become a generic 500 in security.py, with the traceback
logged server-side and never sent.
"""

from http import HTTPStatus

from flask import jsonify, request

MEDIA_TYPE = 'application/problem+json'


def problem(status: int, detail: str, **extensions):
    """A Problem Details response for `status`, with `detail` as the message."""
    body = {
        'type': 'about:blank',
        'title': HTTPStatus(status).phrase,
        'status': status,
        'detail': detail,
        'instance': request.path,
        **extensions,
    }

    # The original, unversioned endpoints (routes/legacy.py) returned errors as
    # {"error": "..."}, and clients written against them read that member. They
    # keep getting it until those endpoints are retired.
    if request.blueprint == 'legacy':
        body['error'] = detail

    response = jsonify(body)
    response.status_code = status
    response.content_type = MEDIA_TYPE
    return response
