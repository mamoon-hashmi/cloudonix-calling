tools = [
{
    "type": "function",
    "function": {
        "name": "transfer_call",
        "description": "Transfer the call to a human when necessary either when the user insists, or when the assistant detects that the situation requires human support (e.g. complex, emotional, or repeated queries).",
        "parameters": {
            "type": "object",
            "properties": {}
        },
        "say": "Transferring your call, please wait."
    }
},
   
    
    {
    "type": "function",
    "function": {
        "name": "end_call",
        "description": "Ends the current call when the user is busy, uninterested, or wants to stop the conversation. The bot should handle it politely and end the call naturally without requiring the user to explicitly say 'bye'.",
        "parameters": {
            "type": "object",
            "properties": {}
        },
        "say": "Goodbye."
    }
}

]
