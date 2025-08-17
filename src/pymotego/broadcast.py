import httpx
from concurrent.futures import ThreadPoolExecutor, Future
from urllib.parse import urljoin
from typing import Dict, Any


BASEURL = "http://localhost:9012/api/broadcast/data/"
DEFAULT_BROADCAST_PATH = "default"


class Broadcast:
    """Asynchronous HTTP broadcast client for sending experimental data to cogmoteGO.

    This class uses a thread pool to execute non-blocking HTTP requests with HTTP/2 support.

    Attributes:
        executor: Thread pool executor for asynchronous task scheduling
        client: HTTPX client instance with persistent connection
    """

    def __init__(self) -> None:
        """Initialize the broadcast client.

        Creates a thread pool with 1 worker and configures HTTPX client with HTTP/2.
        """
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.client = httpx.Client(http2=True)

    def send(self, data: Dict[str, Any]) -> Future[httpx.Response]:
        """Send data to the default broadcast endpoint.

        Args:
            data: Dictionary payload to be sent (will be auto-serialized to JSON)

        Returns:
            Future[httpx.Response]: Future object containing HTTP response.
            Use future.result() to get actual response (blocks until completion).

        Example:
            >>> broadcaster = Broadcast()
            >>> future = broadcaster.send({"key": "value"})
            >>> response = future.result()  # Blocks for result
        """
        return self.executor.submit(self.broadcast, DEFAULT_BROADCAST_PATH, data)

    def send_to(self, endpoint_name: str, data: Dict[str, Any]) -> Future[httpx.Response]:
        """Send data to a specific broadcast endpoint.

        Args:
            endpoint_name: Target endpoint name/path
            data: Dictionary payload to be sent

        Returns:
            Future[httpx.Response]: Future object containing HTTP response

        Raises:
            ValueError: If endpoint_name contains invalid characters
        """
        return self.executor.submit(self.broadcast, endpoint_name, data)

    def broadcast(self, endpoint_name: str, data: Dict[str, Any]) -> httpx.Response:
        """Execute the actual HTTP broadcast request.

        Args:
            endpoint_name: Target endpoint name/path
            data: Dictionary payload to be sent

        Returns:
            httpx.Response: HTTP response object

        Raises:
            httpx.NetworkError: On network connectivity issues
            httpx.HTTPStatusError: For non-2XX status codes
        """
        return self.client.post(urljoin(BASEURL, endpoint_name), json=data)

    def create_broadcast(self, endpoint_name: str) -> httpx.Response:
        """Create a new broadcast endpoint.

        Args:
            endpoint_name: Name of the endpoint to create

        Returns:
            httpx.Response: HTTP response containing creation result
        """
        return self.client.post(urljoin(BASEURL, endpoint_name))

    def __del__(self):
        """Clean up resources.

        Note:
            - Doesn't wait for pending requests (wait=False)
            - Destruction timing depends on Python GC
        """
        self.client.close()
        self.executor.shutdown(wait=False)