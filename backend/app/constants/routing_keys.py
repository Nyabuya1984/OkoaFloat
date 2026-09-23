# Constants for RabbitMQ Routing Keys

# Exchange
PENZI_EXCHANGE = "penzi_events"

ROUTING_KEYS = {
    # User events
    "USER_REGISTERED": "v1.penzi.user.registered",
    "USER_UPDATED": "v1.penzi.user.updated",
    
    # Location events
    "LOCATION_UPDATED": "v1.penzi.location.updated",
    "PASSPORT_ACTIVATED": "v1.penzi.passport.activated",
    "NEARBY_QUERIED": "v1.penzi.nearby.queried",
    
    # Match events
    "MATCH_CREATED": "v1.penzi.match.created",
    "SWIPE_LOGGED": "v1.penzi.swipe.logged",
    
    # Message events
    "MESSAGE_SENT": "v1.penzi.message.sent",
    
    # Photo events
    "PHOTO_UPLOADED": "v1.penzi.photo.uploaded"
}
