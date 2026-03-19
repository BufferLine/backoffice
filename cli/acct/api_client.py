import os

import httpx
import typer
from acct.config import get_api_url, get_token


def get_client() -> httpx.Client:
    token = get_token()
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx.Client(base_url=get_api_url(), headers=headers, timeout=30.0)


def api_get(path: str, params: dict | None = None) -> dict:
    with get_client() as client:
        resp = client.get(path, params=params)
        _handle_error(resp)
        return resp.json()


def api_post(path: str, json_data: dict | None = None, files: dict | None = None) -> dict:
    with get_client() as client:
        if files:
            resp = client.post(path, files=files)
        else:
            resp = client.post(path, json=json_data)
        _handle_error(resp)
        return resp.json()


def api_patch(path: str, json_data: dict) -> dict:
    with get_client() as client:
        resp = client.patch(path, json=json_data)
        _handle_error(resp)
        return resp.json()


def api_delete(path: str) -> dict:
    with get_client() as client:
        resp = client.delete(path)
        _handle_error(resp)
        try:
            return resp.json()
        except Exception:
            return {}


def api_download(path: str, output_path: str) -> str:
    """Download a file from the API and save to disk. Returns saved filepath."""
    with get_client() as client:
        resp = client.get(path)
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
