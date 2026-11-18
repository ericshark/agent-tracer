from urllib.parse import urlsplit

from app.config import get_settings

OFFICIAL_URLS = {
    "anthropic": "https://api.anthropic.com",
    "openai": "https://api.openai.com",
}


def provider_url(provider: str, configured_url: str | None) -> str:
    """Custom destinations are explicitly trusted by the service operator."""
    official_url = OFFICIAL_URLS[provider]
    if configured_url is None:
        return official_url
    settings = get_settings()
    custom_hosts = (
        settings.anthropic_provider_hosts
        if provider == "anthropic"
        else settings.openai_provider_hosts
    )
    allowed = {urlsplit(official_url).hostname}
    allowed.update(host.strip().lower() for host in custom_hosts.split(",") if host.strip())

    try:
        parsed = urlsplit(configured_url)
        if (
            any(c.isspace() or ord(c) < 32 for c in configured_url)
            or any(c in configured_url for c in "\\?#")
            or parsed.scheme != "https"
            or parsed.hostname not in allowed
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in (None, 443)
            or parsed.netloc.lower() not in (parsed.hostname, f"{parsed.hostname}:443")
        ):
            raise ValueError
    except ValueError:
        raise ValueError("Provider URL must be HTTPS and use an approved provider host") from None
    return configured_url.rstrip("/")
