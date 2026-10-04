"""Tiny JSON-over-HTTP client (stdlib only, so the setup job needs no pip install)."""
import http.cookiejar
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


class ApiError(RuntimeError):
    def __init__(self, method, url, status, body):
        super().__init__(f"{method} {url} -> HTTP {status}: {body[:800]}")
        self.status = status
        self.body = body


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # noqa: D401
        return None


class Client:
    def __init__(self, base_url, headers=None, timeout=120):
        self.base = base_url.rstrip("/")
        self.headers = dict(headers or {})
        self.timeout = timeout

    def url(self, path, params=None):
        u = path if path.startswith("http") else f"{self.base}/{path.lstrip('/')}"
        if params:
            u += ("&" if "?" in u else "?") + urllib.parse.urlencode(params, doseq=True)
        return u

    def request(self, method, path, body=None, params=None, headers=None, raw=False, ok404=False):
        url = self.url(path, params)
        data = None
        hdrs = dict(self.headers)
        hdrs.update(headers or {})
        if body is not None and not isinstance(body, (bytes, bytearray)):
            data = json.dumps(body).encode()
            hdrs.setdefault("Content-Type", "application/json")
        elif body is not None:
            data = bytes(body)
        hdrs.setdefault("Accept", "application/json")
        req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = resp.read()
        except urllib.error.HTTPError as e:
            text = e.read().decode(errors="replace")
            if ok404 and e.code == 404:
                return None
            raise ApiError(method, url, e.code, text) from None
        if raw:
            return payload
        if not payload:
            return None
        try:
            return json.loads(payload)
        except ValueError:
            return payload.decode(errors="replace")

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, body=None, **kw):
        return self.request("POST", path, body=body if body is not None else {}, **kw)

    def put(self, path, body=None, **kw):
        return self.request("PUT", path, body=body if body is not None else {}, **kw)

    def delete(self, path, **kw):
        return self.request("DELETE", path, **kw)

    def upload(self, path, filename, content, params=None, field=None):
        """multipart/form-data upload of a single file."""
        boundary = uuid.uuid4().hex
        field = field or filename
        parts = [
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'.encode(),
            b"Content-Type: application/octet-stream\r\n\r\n",
            content,
            f"\r\n--{boundary}--\r\n".encode(),
        ]
        return self.request(
            "POST", path, body=b"".join(parts), params=params,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )


def wait_for(desc, fn, timeout=900, interval=5):
    start = time.time()
    last = None
    while time.time() - start < timeout:
        try:
            if fn():
                return
        except Exception as e:  # noqa: BLE001
            last = e
        time.sleep(interval)
    raise TimeoutError(f"Timed out waiting for {desc}: {last}")


def browser_login_token(base_url, client_id, username, password, public_url=None):
    """Obtain a short-lived OAuth access token from YouTrack's embedded Hub by
    performing the same implicit-grant login the YouTrack web UI performs.
    Only used once, to mint a permanent token (the documented REST auth method)."""
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), NoRedirect)
    public_url = (public_url or base_url).rstrip("/")
    redirect = f"{public_url}/oauth"
    q = urllib.parse.urlencode({
        "response_type": "token", "client_id": client_id, "redirect_uri": redirect,
        "scope": f"0-0-0-0-0 {client_id}", "state": "setup",
    })
    data = urllib.parse.urlencode({"username": username, "password": password}).encode()
    url = f"{base_url}/hub/api/rest/oauth2/interactive/login?{q}"
    for _ in range(6):
        try:
            resp = opener.open(urllib.request.Request(url, data=data, method="POST") if data else url)
            loc = resp.headers.get("Location")
        except urllib.error.HTTPError as e:
            loc = e.headers.get("Location")
        data = None
        if not loc:
            return None
        if "access_token=" in loc:
            frag = urllib.parse.urlparse(loc).fragment
            return urllib.parse.parse_qs(frag)["access_token"][0]
        if "hub-auth-credentials-bad" in loc or "error=" in loc:
            return None
        if loc.startswith("/"):
            loc = base_url + loc
        elif loc.startswith(public_url):
            loc = base_url + loc[len(public_url):]
        url = loc
    return None
