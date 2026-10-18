"""Exact catalog entity resolution only; no merchant classification."""
import re
from urllib.parse import urlsplit
from backend.decisions.common import canonical_domain


def safe_domain(value):
    value = value.strip()
    parsed = urlsplit(value if '://' in value else '//' + value)
    if (parsed.scheme not in ('', 'http', 'https') or parsed.username or parsed.password
            or (parsed.hostname or '').endswith('..')):
        raise ValueError('Invalid merchant domain')
    try:
        port = parsed.port
    except ValueError:
        raise ValueError('Invalid merchant port') from None
    host = canonical_domain(value)
    if port not in (None, 80, 443) or not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?', host):
        raise ValueError('Invalid merchant domain')
    if any(not label or len(label) > 63 or label.startswith('-') or label.endswith('-') for label in host.split('.')):
        raise ValueError('Invalid merchant domain')
    return host


def exact_merchants(query, merchants):
    text = query.strip().casefold()
    # A standalone hostname/URL must go through the same safe normalization as
    # the domain field, including rejecting deceptive userinfo URLs.
    query_host = safe_domain(text) if '.' in text and not re.search(r'\s', text) else None
    matches = []
    for merchant in merchants:
        if query_host is not None:
            hosts = [safe_domain(merchant.domain),
                     *[safe_domain(a) for a in merchant.aliases if '.' in a and ' ' not in a]]
            if query_host in hosts:
                matches.append(merchant)
            continue
        for name in [merchant.name, merchant.domain, *merchant.aliases]:
            # Boundaries prevent Nike from matching Nikeshoes or nike.com.evil.
            if name and re.search(r'(?<![\w.-])' + re.escape(name.casefold()) + r'(?![\w.-])', text):
                matches.append(merchant)
                break
    return matches
