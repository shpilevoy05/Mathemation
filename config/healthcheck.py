"""Probe the web process without requiring TLS on its loopback listener."""
from urllib.request import Request, urlopen

from django.conf import settings


def main():
    host = settings.ALLOWED_HOSTS[0].lstrip(".")
    request = Request("http://127.0.0.1:8000/healthz", headers={"Host": host})
    with urlopen(request, timeout=4) as response:
        return 0 if response.status == 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())
