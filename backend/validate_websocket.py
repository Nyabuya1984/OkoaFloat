import pika
import json
import time

def test_publish():
    # Connect to RabbitMQ
    connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
    channel = connection.channel()
    
    # Ensure exchange exists
    exchange_name = 'penzi_events'
    channel.exchange_declare(exchange=exchange_name, exchange_type='topic', durable=True)
    
    # The phone number you are currently logged into on the frontend
    test_phone = "0721143189"  # CHANGE THIS to your frontend user's phone
    
    message_payload = {
        "to": test_phone,
        "from": "0722114477",
        "text": "Automated WebSocket Validation Test!",
        "type": "text"
    }
    
    routing_key = 'v1.penzi.message.sent'
    
    print(f"Publishing to {exchange_name} with routing key {routing_key}...")
    channel.basic_publish(
        exchange=exchange_name,
        routing_key=routing_key,
        body=json.dumps(message_payload)
    )
    print("Message published successfully. Check your React UI/Console!")
    connection.close()

if __name__ == "__main__":
    test_publish()
