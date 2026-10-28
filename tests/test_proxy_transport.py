"""Exercise proxy routing without contacting a real website or proxy."""

import socket
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from sblinkseo.diagnostics import failure_detail
from sblinkseo.network import Config, Transport


class ProxyTransportTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict("os.environ", {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.client, self.server = socket.socketpair()
        self.addCleanup(self.client.close)
        self.addCleanup(self.server.close)
        self.client.settimeout(3)
        self.server.settimeout(3)
        self.requests = []
        self.errors = []

    def proxy(self, status=200):
        def run():
            try:
                request = b""
                while b"\r\n\r\n" not in request:
                    request += self.server.recv(1024)
                self.requests.append(request)
                self.server.sendall(f"HTTP/1.1 {status} test\r\n\r\n".encode())
                if status == 200:
                    request = b""
                    while b"\r\n\r\n" not in request:
                        request += self.server.recv(1024)
                    self.requests.append(request)
                    self.server.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")
            except Exception as exc:
                self.errors.append(exc)

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 3)
        return thread

    def test_proxy_tunnels_to_checked_ip_and_hides_proxy_credentials(self):
        self.proxy()
        infos = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 80))]
        with (
            patch.dict("os.environ", {"http_proxy": "http://user:secret@proxy.test:8123"}),
            patch("sblinkseo.network.addresses", return_value=infos),
            patch(
                "sblinkseo.network.socket.create_connection", return_value=self.client
            ) as connect,
        ):
            response = Transport(Config("http://example.com", delay=0, retries=0)).fetch(
                "http://example.com/"
            )
        self.assertEqual(response.status, 200)
        self.assertEqual(response.body, b"ok")
        connect.assert_called_once()
        self.assertIn(b"CONNECT 8.8.8.8:80 HTTP/1.1", self.requests[0])
        self.assertIn(b"Proxy-Authorization: Basic dXNlcjpzZWNyZXQ=", self.requests[0])
        self.assertIn(b"Host: example.com", self.requests[1])
        self.assertNotIn(b"Proxy-Authorization", self.requests[1])
        self.assertNotIn("secret", repr(response))
        self.assertFalse(self.errors)

    def test_https_tunnel_uses_original_hostname_for_tls(self):
        self.proxy()
        infos = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]
        context = MagicMock()
        context.wrap_socket.side_effect = lambda sock, **kwargs: sock
        with (
            patch.dict("os.environ", {"https_proxy": "http://proxy.test:8123"}),
            patch("sblinkseo.network.addresses", return_value=infos),
            patch("sblinkseo.network.socket.create_connection", return_value=self.client),
            patch("sblinkseo.network.ssl.create_default_context", return_value=context),
        ):
            result = Transport(Config("https://example.com", delay=0, retries=0)).fetch(
                "https://example.com/"
            )
        self.assertEqual(result.status, 200)
        self.assertIn(b"CONNECT 8.8.8.8:443 HTTP/1.1", self.requests[0])
        context.wrap_socket.assert_called_once_with(self.client, server_hostname="example.com")

    def test_proxy_407_is_recorded_without_credentials(self):
        self.proxy(407)
        infos = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 80))]
        with (
            patch.dict("os.environ", {"http_proxy": "http://user:secret@proxy.test:8123"}),
            patch("sblinkseo.network.addresses", return_value=infos),
            patch("sblinkseo.network.socket.create_connection", return_value=self.client),
        ):
            result = Transport(Config("http://example.com", delay=0, retries=0)).fetch(
                "http://example.com/"
            )
        self.assertEqual(failure_detail(result.error)["code"], "proxy_authentication_required")
        self.assertNotIn("secret", result.error)

    def test_dns_failure_does_not_fall_back_to_unverified_proxy_dns(self):
        with (
            patch.dict("os.environ", {"https_proxy": "http://proxy.test:8123"}),
            patch("sblinkseo.network.addresses", side_effect=socket.gaierror("DNS unavailable")),
            patch("sblinkseo.network.socket.create_connection") as connect,
        ):
            result = Transport(Config("https://example.com", delay=0, retries=0)).fetch(
                "https://example.com/"
            )
        self.assertEqual(failure_detail(result.error)["code"], "dns_failure")
        connect.assert_not_called()

    def test_private_destination_is_rejected_before_proxy(self):
        with (
            patch.dict("os.environ", {"https_proxy": "http://proxy.test:8123"}),
            patch(
                "sblinkseo.network.socket.getaddrinfo",
                return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))],
            ),
            patch("sblinkseo.network.socket.create_connection") as connect,
        ):
            result = Transport(Config("https://example.com", delay=0, retries=0)).fetch(
                "https://example.com/"
            )
        self.assertIn("private_or_nonpublic_address", result.error)
        connect.assert_not_called()

    def test_no_proxy_and_unsupported_proxy(self):
        infos = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]
        with (
            patch.dict("os.environ", {"https_proxy": "socks5://proxy.test:1080"}),
            patch("sblinkseo.network.addresses", return_value=infos),
        ):
            result = Transport(Config("https://example.com", delay=0, retries=0)).fetch(
                "https://example.com/"
            )
        self.assertEqual(failure_detail(result.error)["code"], "unsupported_proxy_configuration")
        with (
            patch.dict(
                "os.environ", {"https_proxy": "http://proxy.test:8123", "no_proxy": "example.com"}
            ),
            patch("sblinkseo.network.socket.socket") as direct,
            patch("sblinkseo.network.socket.create_connection") as proxy,
        ):
            direct.return_value = MagicMock()
            transport = Transport(Config("https://example.com"))
            sock = transport._connect("https://example.com", infos, time.monotonic() + 3)
            sock.close()
            proxy.assert_not_called()
            direct.assert_called()


if __name__ == "__main__":
    unittest.main()
