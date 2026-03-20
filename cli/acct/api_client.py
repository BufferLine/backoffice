import os

import httpx
import typer
from acct.config import get_api_url, get_refresh_token, get_token, update_token


def get_client() -> httpx.Client:
    token = get_token()
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx.Client(base_url=get_api_url(), headers=headers, timeout=30.0)


def _try_refresh() -> bool:
    """Attempt to refresh the access token. Returns True if successful."""
    refresh_token = get_refresh_token()
    if not refresh_token:
        return False
    try:
        with httpx.Client(base_url=get_api_url(), timeout=30.0) as client:
            resp = client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
            if resp.status_code == 200:
                data = resp.json()
                update_token(data["access_token"])
                return True
    except Exception:
        pass
    return False


def _request(method: str, path: str, **kwargs) -> httpx.Response:
    """Make a request, auto-refreshing the token on 401."""
    with get_client() as client:
        resp = getattr(client, method)(path, **kwargs)
    if resp.status_code == 401 and _try_refresh():
        with get_client() as client:
            resp = getattr(client, method)(path, **kwargs)
    return resp


def api_get(path: str, params: dict | None = None) -> dict:
    resp = _request("get", path, params=params)
    _handle_error(resp)
    return resp.json()


def api_post(path: str, json_data: dict | None = None, files: dict | None = None, params: dict | None = None) -> dict:
    kwargs = {}
    if params:
        kwargs["params"] = params
    if files:
        kwargs["files"] = files
    else:
        kwargs["json"] = json_data
    resp = _request("post", path, **kwargs)
    _handle_error(resp)
    return resp.json()


def api_patch(path: str, json_data: dict) -> dict:
    resp = _request("patch", path, json=json_data)
    _handle_error(resp)
    return resp.json()


def api_delete(path: str) -> dict:
    resp = _request("delete", path)
    _handle_error(resp)
    try:
        return resp.json()
    except Exception:
        return {}


def api_download(path: str, output_path: str) -> str:
    """Download a file from the API and save to disk. Returns saved filepath."""
    resp = _request("get", path)
    _handle_error(resp)
    cd = resp.headers.get("content-disposition", "")
    filename = "download"
    if "filename=" in cd:
        filename = cd.split("filename=")[1].strip('"')

    if os.path.isdir(output_path):
        filepath = os.path.join(output_path, filename)
    else:
        filepath = output_path
    with open(filepath, "wb") as f:
        f.write(resp.content)
    return filepath


def _handle_error(resp: httpx.Response) -> None:
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text
        typer.echo(f"Error {resp.status_code}: {detail}", err=True)
        raise typer.Exit(1)
