"""Recognize HTTPS terminated by a reverse proxy on this machine."""

from ipaddress import ip_address


class LocalProxySchemeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Never accept this internal header directly from the client.
        request.META.pop('HTTP_X_LOCAL_PROXY_SCHEME', None)
        try:
            peer = ip_address(request.META.get('REMOTE_ADDR', ''))
            if getattr(peer, 'ipv4_mapped', None):
                peer = peer.ipv4_mapped
            loopback = peer.is_loopback
        except ValueError:
            loopback = False

        # ngrok appends its own value; the last value is the trusted one.
        scheme = request.META.get('HTTP_X_FORWARDED_PROTO', '').rsplit(',', 1)[-1].strip().lower()
        if loopback and scheme == 'https':
            request.META['HTTP_X_LOCAL_PROXY_SCHEME'] = 'https'
        return self.get_response(request)
