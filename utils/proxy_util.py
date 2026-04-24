"""
Proxy Utility
=============
Builds a Chrome extension for authenticated proxy support.
"""

import os
import tempfile
import zipfile
import shutil
from typing import Optional


def create_proxy_extension(host: str, port: str, user: str, password: str) -> Optional[str]:
    """
    Creates a Chrome extension (.zip) for authenticated proxy support.
    Returns the path to the extension zip file, or None on failure.
    """
    if not all([host, port, user, password]):
        return None

    manifest_json = """{
    "version": "1.0.0",
    "manifest_version": 2,
    "name": "Proxy Auth Extension",
    "permissions": [
        "proxy",
        "tabs",
        "unlimitedStorage",
        "storage",
        "<all_urls>",
        "webRequest",
        "webRequestBlocking"
    ],
    "background": {
        "scripts": ["background.js"]
    }
}"""

    background_js = """var config = {
    mode: "fixed_servers",
    rules: {
        singleProxy: {
            scheme: "http",
            host: "%s",
            port: parseInt(%s)
        },
        bypassList: ["localhost"]
    }
};

chrome.proxy.settings.set({value: config, scope: "regular"}, function() {});

function callbackFn(details) {
    return {
        authCredentials: {
            username: "%s",
            password: "%s"
        }
    };
}

chrome.webRequest.onAuthRequired.addListener(
    callbackFn,
    {urls: ["<all_urls>"]},
    ['blocking']
);""" % (host, port, user, password)

    # Create temp directory for the extension
    ext_dir = tempfile.mkdtemp(prefix="li_proxy_")
    ext_zip = os.path.join(ext_dir, "proxy_extension.zip")

    try:
        with zipfile.ZipFile(ext_zip, "w") as zf:
            zf.writestr("manifest.json", manifest_json)
            zf.writestr("background.js", background_js)
        return ext_zip
    except Exception:
        shutil.rmtree(ext_dir, ignore_errors=True)
        return None


def cleanup_proxy_extension(ext_path: str):
    """Remove the temporary proxy extension directory."""
    if ext_path:
        ext_dir = os.path.dirname(ext_path)
        shutil.rmtree(ext_dir, ignore_errors=True)
