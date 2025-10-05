"""MQTT client for receiving and processing messages."""

import json
import logging
import threading
import time

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

from src.handlers.base import HandlerBase

logger = logging.getLogger(__name__)


class MQTTClient:
    """MQTT client for handling display commands."""

    def __init__(
        self,
        broker_host: str,
        broker_port: int = 1883,
        client_id: str | None = None,
        username: str | None = None,
        password: str | None = None,
        shutdown_timeout: float = 60.0,
    ):
        """Initialize MQTT client.

        Args:
            broker_host: MQTT broker hostname
            broker_port: MQTT broker port
            client_id: Client ID for MQTT connection
            username: Optional username for authentication
            password: Optional password for authentication
            shutdown_timeout: Seconds to wait for handlers during shutdown
        """
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.shutdown_timeout = shutdown_timeout

        # Initialize MQTT client (paho-mqtt v2.x API)
        if client_id:
            self.client = mqtt.Client(
                CallbackAPIVersion.VERSION2, client_id=client_id, clean_session=False
            )
        else:
            self.client = mqtt.Client(CallbackAPIVersion.VERSION2, clean_session=False)

        # Set authentication if provided
        if username:
            self.client.username_pw_set(username, password)

        # Set callbacks
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect

        # Message handlers registry
        self.handlers: list[HandlerBase] = []
        self.topics: list[str] = []
        self.connected = threading.Event()

        # Handler activity tracking for graceful shutdown
        self._handler_lock = threading.Lock()
        self._active_handlers = 0
        self._shutting_down = False

    def register_handler(self, handler: HandlerBase) -> None:
        """Register a message handler.

        Args:
            handler: Handler instance to register
        """
        self.handlers.append(handler)
        logger.info(f"Registered handler for actions: {handler.supported_actions}")

    def add_topic(self, topic: str) -> None:
        """Add a topic to subscribe to.

        Args:
            topic: MQTT topic to subscribe to
        """
        self.topics.append(topic)
        logger.info(f"Added topic: {topic}")

    def connect(self) -> None:
        """Connect to the MQTT broker."""
        try:
            logger.info(f"Connecting to MQTT broker {self.broker_host}:{self.broker_port}")
            self.client.connect(self.broker_host, self.broker_port, keepalive=60)
            self.client.loop_start()

            # Wait for connection to establish
            if not self.connected.wait(timeout=10):
                raise TimeoutError("Failed to connect to MQTT broker within timeout")

            logger.info("Successfully connected to MQTT broker")

        except Exception as e:
            logger.error(f"Failed to connect to MQTT broker: {e}")
            raise

    def wait_for_handlers(self, timeout: float = 60.0) -> bool:
        """Wait for all active handlers to complete.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            True if all handlers completed, False if timeout occurred
        """
        start_time = time.time()
        while True:
            with self._handler_lock:
                if self._active_handlers == 0:
                    logger.info("All handlers completed")
                    return True

                active_count = self._active_handlers

            elapsed = time.time() - start_time
            if elapsed >= timeout:
                logger.warning(
                    f"Timeout waiting for {active_count} handler(s) to complete after {timeout}s"
                )
                return False

            logger.debug(f"Waiting for {active_count} handler(s) to complete...")
            time.sleep(0.1)

    def disconnect(self) -> None:
        """Disconnect from the MQTT broker."""
        logger.info("Disconnecting from MQTT broker")

        # Mark as shutting down to prevent new messages from being processed
        with self._handler_lock:
            self._shutting_down = True

        # Wait for active handlers to complete
        self.wait_for_handlers(timeout=self.shutdown_timeout)

        # Stop the loop with a timeout to prevent hanging
        stop_thread = threading.Thread(target=self.client.loop_stop)
        stop_thread.start()
        stop_thread.join(timeout=2.0)

        if stop_thread.is_alive():
            logger.warning("loop_stop() timed out, forcing disconnect")

        self.client.disconnect()
        self.connected.clear()
        logger.info("Disconnected from MQTT broker")

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        """Callback for successful connection.

        Args:
            client: MQTT client instance
            userdata: User data
            flags: Connection flags
            reason_code: Connection result code
            properties: MQTT v5 properties
        """
        if reason_code == 0:
            logger.info("Connected to MQTT broker successfully")
            self.connected.set()

            # Subscribe to topics
            for topic in self.topics:
                client.subscribe(topic, qos=2)
                logger.info(f"Subscribed to topic: {topic}")
        else:
            logger.error(f"Failed to connect to MQTT broker. Result code: {reason_code}")

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        """Callback for disconnection.

        Args:
            client: MQTT client instance
            userdata: User data
            disconnect_flags: Disconnection flags
            reason_code: Disconnection result code
            properties: MQTT v5 properties
        """
        self.connected.clear()
        if reason_code == 0:
            logger.info("Disconnected from MQTT broker cleanly")
        else:
            logger.warning(f"Unexpected disconnection from MQTT broker. Result code: {reason_code}")

    def _on_message(self, client, userdata, msg):
        """Callback for received messages.

        Args:
            client: MQTT client instance
            userdata: User data
            msg: Message object
        """
        try:
            # Check if we're shutting down
            with self._handler_lock:
                if self._shutting_down:
                    logger.debug("Ignoring message - shutting down")
                    return

            topic = msg.topic
            payload = msg.payload.decode("utf-8")
            logger.debug(f"Received message on {topic}: {payload}")

            # Parse JSON payload
            try:
                message = json.loads(payload)
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in message: {e}")
                return

            # Extract action and data
            action = message.get("action")
            data = message.get("data", {})

            if not action:
                logger.error("Message missing 'action' field")
                return

            # Find and execute appropriate handler
            handler_found = False
            for handler in self.handlers:
                if handler.can_handle(action):
                    logger.info(f"Processing '{action}' with {handler.__class__.__name__}")
                    try:
                        # Track handler activity
                        with self._handler_lock:
                            if self._shutting_down:
                                logger.info("Shutdown initiated - not processing new message")
                                return
                            self._active_handlers += 1

                        try:
                            handler.handle(data)
                        finally:
                            with self._handler_lock:
                                self._active_handlers -= 1

                        handler_found = True
                        break
                    except Exception as e:
                        logger.error(f"Handler failed to process message: {e}")

            if not handler_found:
                logger.warning(f"No handler found for action: {action}")

        except Exception as e:
            logger.error(f"Error processing message: {e}")

    def run_forever(self) -> None:
        """Run the client in blocking mode."""
        try:
            logger.info("MQTT client running. Press Ctrl+C to stop.")
            while True:
                self.connected.wait()
        except KeyboardInterrupt:
            logger.info("Shutting down MQTT client")
            self.disconnect()
