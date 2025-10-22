from typing import List, Optional

class CallContext:
    """Store context for the current call."""
    def __init__(self):
        self.stream_sid: Optional[str] = None
        self.call_sid: Optional[str] = None
        self.call_ended: bool = False
        self.user_context: List = []
        self.system_message: str = ""
        self.initial_message: str = ""
        self.session = None
        self.start_time: Optional[str] = None
        self.end_time: Optional[str] = None
        self.final_status: Optional[str] = None
        self.first_name: Optional[str] = None  # Explicitly typed as Optional[str]

    def to_dict(self) -> dict:
        """Convert CallContext to a dictionary for logging."""
        return {
            "stream_sid": self.stream_sid,
            "call_sid": self.call_sid,
            "call_ended": self.call_ended,
            "user_context": self.user_context,
            "system_message": self.system_message,
            "initial_message": self.initial_message,
            "session": self.session,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "final_status": self.final_status,
            "first_name": self.first_name
        }