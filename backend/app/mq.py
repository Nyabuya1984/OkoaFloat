import pika
import json
import logging
import os
from .constants import ROUTING_KEYS, PENZI_EXCHANGE

logger = logging.getLogger(__name__)

class MessageQueue:
    """Wrapper for RabbitMQ using pika"""
    def __init__(self):
        self.connection = None
        self.channel = None
        self.url = os.environ.get("MQ_URL", "amqp://guest:guest@localhost:5672/%2f")

    def connect(self):
        # Reuse a healthy channel instead of opening a fresh heavyweight
        # connection on every publish request.
        if self.connection and not getattr(self.connection, "is_closed", True) and self.channel:
            return

        try:
            if self.connection and getattr(self.connection, "is_closed", True):
                self.connection = None
                self.channel = None

            parameters = pika.URLParameters(self.url)
            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()
            self.channel.exchange_declare(exchange=PENZI_EXCHANGE, exchange_type='topic', durable=True)
            logger.info("Connected to RabbitMQ")
        except Exception as e:
            self.connection = None
            self.channel = None
            logger.warning(f"RabbitMQ connection unavailable; continuing without queue publish: {e}")

    def publish(self, routing_key, body):
        try:
            self.connect()
            if not self.channel:
                logger.warning("RabbitMQ channel is unavailable; skipping publish")
                return

            self.channel.basic_publish(
                exchange=PENZI_EXCHANGE,
                routing_key=routing_key,
                body=json.dumps(body),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # make message persistent
                )
            )
            logger.info(f"Published message to {routing_key}")
        except Exception as e:
            logger.warning(f"RabbitMQ publish skipped because the backend connection is unavailable: {e}")

    def publish_status_indicator(self, user_phone, status):
        """
        Publishes a status indicator to RabbitMQ (Online, Offline, Processing, Done, Live).
        WebSockets (via STOMP plugin) can subscribe to topic/status.{user_phone}
        """
        valid_statuses = ["Online", "Offline", "Processing", "Done", "Live"]
        if status not in valid_statuses:
            logger.warning(f"Invalid status {status} published for {user_phone}")
        
        # For STOMP, topics are typically prefixed depending on the rabbitmq stomp configuration
        # Assuming exchange=penzi_events and routing key is status.<phone>
        routing_key = f"status.{user_phone}"
        body = {"phone": user_phone, "status": status}
        self.publish(routing_key, body)

    def publish_location_update(self, phone, latitude, longitude):
        """
        Publishes location update to v1.penzi.location.updated
        """
        routing_key = ROUTING_KEYS.get("LOCATION_UPDATED", "v1.penzi.location.updated")
        body = {"phone": phone, "latitude": latitude, "longitude": longitude}
        self.publish(routing_key, body)

mq = MessageQueue()
