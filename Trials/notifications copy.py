from langgraph.graph import StateGraph, END
from langchain_core.messages import AnyMessage, SystemMessage, HumanMessage, ToolMessage, AIMessage
from langchain_groq import ChatGroq
from langchain_core.tools import tool
from typing import Dict, TypedDict, Annotated, List
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
import operator
import json
import os
from api_agent import agent  

import os
from dotenv import load_dotenv

os.environ.pop("TWILIO_ACCOUNT_SID", None)
os.environ.pop("TWILIO_AUTH_TOKEN", None)

load_dotenv()

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")

@tool
def send_message(to_number: str, message_body: str) -> dict:
    """
    Sends an SMS message using Twilio.
    
    Args:
        to_number: The recipient's phone number (format: +[country_code][number])
        message_body: The text message to send
        
    Returns:
        Dictionary containing status of the message send attempt
    """
    try:    
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        
        message = client.messages.create(
            from_= +12316255322,
            body=message_body,
            to=to_number
        )
        
        return {
            "status": "success",
            "message_sid": message.sid,
            "to": to_number,
            "body": message_body
        }
        
    except TwilioRestException as e:
        return {
            "error": f"Twilio error: {str(e)}",
            "code": e.code,
            "status": e.status
        }
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


class MessagingAgentState(TypedDict):
    messages: Annotated[List[AnyMessage], operator.add]
    flight_data: dict
    recipient_number: str  

class MessagingAgent:
    def __init__(self, model, send_message_tool):
        self.model = model.bind_tools([send_message_tool])
        self.send_message = send_message_tool
        
        self.system_prompt = """You are a flight notification assistant that decides when to send SMS notifications based on flight status data.

        When receiving flight data, follow these rules for sending notifications:
        1. If flight_status is "landed" or "arrived": Send a landing notification
        2. If flight_status is "delayed": Send a delay notification
        3. For all other statuses: Send a "flight on track" notification

        For landed/arrived flights: Focus on arrival time and any terminal information
        For delayed flights: Include the delay duration and new estimated arrival time
        For on-track flights: Provide reassurance about the flight's normal status

        All messages should be clear, concise, and informative."""

        graph = StateGraph(MessagingAgentState)
        
        graph.add_node("process_status", self.process_flight_status)
        graph.add_node("send_notification", self.send_notification)
        
        graph.add_edge("process_status", "send_notification")
        graph.add_edge("send_notification", END)
        
        graph.set_entry_point("process_status")
        self.graph = graph.compile()

    def process_flight_status(self, state: MessagingAgentState) -> Dict:
        """Process flight status and prepare appropriate message"""
        flight_data = state['flight_data']
        status = flight_data.get('Flight status', '').lower()
        flight_number = flight_data.get('Flight number')
        delay = flight_data.get('Delay')
        live_data = flight_data.get('Live', {})
        
        def format_datetime(iso_time_str):
            from datetime import datetime
            try:
                dt = datetime.fromisoformat(iso_time_str.replace('Z', '+00:00'))
                date_str = dt.strftime("%B %d")  
                time_str = dt.strftime("%I:%M %p")  
                return f"{date_str} at {time_str}"
            except:
                return iso_time_str
        
        message = None
        if status == 'landed':
            arrival_datetime = format_datetime(flight_data['Arrival time'])
            message = (
                f"Great news! Your flight {flight_number} has safely landed at "
                f"{flight_data['Arrival airport']} on {arrival_datetime}. "
                f"You can collect your bags at Terminal {flight_data.get('Terminal', 'TBD')}"
            )
        elif status == 'active':
            updated_time = live_data.get('Updated time')
            if updated_time:
                updated_datetime = format_datetime(updated_time)
                update_info = f"Last updated on {updated_datetime}"
            else:
                update_info = "Currently in flight"

            altitude_info = ""
            if live_data.get('altitude'):
                altitude_info = f" at {live_data['altitude']} feet"
            
            arrival_datetime = format_datetime(flight_data['Arrival time'])
            message = (
                f"Your flight {flight_number} is currently in the air! {update_info}{altitude_info}. "
                f"Expected to arrive at {flight_data['Arrival airport']} on {arrival_datetime}. "
                f"You'll be arriving at Terminal {flight_data.get('Terminal', 'TBD')}, "
                f"Gate {flight_data.get('Gate', 'TBD')}"
            )
        elif delay and delay > 0:
            arrival_datetime = format_datetime(flight_data['Arrival time'])
            message = (
                f"Important update for flight {flight_number}: "
                f"There's a {delay}-minute delay. "
                f"Your new arrival time is {arrival_datetime}. "
                f"Please proceed to Terminal {flight_data.get('Terminal', 'TBD')}, "
                f"Gate {flight_data.get('Gate', 'TBD')}"
            )
        else:  # scheduled
            departure_datetime = format_datetime(flight_data['Departure time'])
            arrival_datetime = format_datetime(flight_data['Arrival time'])
            message = (
                f"Your flight {flight_number} is on schedule! "
                f"Departure from {flight_data['Departure airport']} on {departure_datetime}. "
                f"You'll arrive at {flight_data['Arrival airport']} on {arrival_datetime}. "
                f"Please head to Terminal {flight_data.get('Terminal', 'TBD')}, "
                f"Gate {flight_data.get('Gate', 'TBD')}"
            )

        tool_call = {
            'id': 'sms_notification',
            'name': 'send_message',
            'args': {
                'to_number': state['recipient_number'],
                'message_body': message
            }
        }
        
        return {
            'messages': state['messages'] + [
                AIMessage(content="Preparing SMS notification.", tool_calls=[tool_call])
            ],
            'flight_data': flight_data,
            'recipient_number': state['recipient_number']
        }
    def send_notification(self, state: MessagingAgentState) -> Dict:
        """Execute the SMS sending tool call"""
        last_message = state['messages'][-1]
        
        if not hasattr(last_message, 'tool_calls'):
            return state
            
        results = []
        for tool_call in last_message.tool_calls:
            try:
                if isinstance(tool_call, dict):
                    args = tool_call['args']
                else:
                    args = tool_call.args
                
                result = self.send_message.invoke(args)
                results.append(
                    ToolMessage(
                        tool_call_id=getattr(tool_call, 'id', 'unknown'),
                        name='send_message',
                        content=str(result)
                    )
                )
            except Exception as e:
                results.append(
                    ToolMessage(
                        tool_call_id=getattr(tool_call, 'id', 'unknown'),
                        name='send_message',
                        content=f"Error sending message: {str(e)}"
                    )
                )
        
        return {
            'messages': state['messages'] + results,
            'flight_data': state['flight_data'],
            'recipient_number': state['recipient_number']
        }

def clean_markdown_json(content: str) -> str:
    """Remove Markdown formatting from JSON string"""
    content = content.replace('```json', '').replace('```', '')
    return content.strip()

def send_notification_for_flight(flight_code: str, recipient_number: str) -> Dict:
    """
    Send flight notifications to a specified recipient number.
    
    Args:
        flight_code: The flight number to track
        recipient_number: The recipient's phone number (format: +[country_code][number])
        
    Returns:
        Dictionary containing the notification results
    """
    flight_messages = [HumanMessage(content=f"What are the details of {flight_code}?")]
    flight_result = agent.graph.invoke({"messages": flight_messages})
    
    cleaned_content = clean_markdown_json(flight_result["messages"][-1].content)
    
    try:
        flight_data = json.loads(cleaned_content)
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON after cleaning: {e}")
        raise ValueError("Unable to parse flight data response")
    
    model = ChatGroq(model="llama-3.3-70b-versatile")
    messaging_agent = MessagingAgent(model=model, send_message_tool=send_message)
    
    initial_state = {
        "messages": [HumanMessage(content="Process flight status for notifications")],
        "flight_data": flight_data,
        "recipient_number": recipient_number  
    }
    
    result = messaging_agent.graph.invoke(initial_state)
    return result

try:
    flight_code = "RJA3813"
    recipient_number = "+233532419012"  
    
    result = send_notification_for_flight(flight_code, recipient_number)
    print("\nNotification result:")
    print(result["messages"][-1].content)
except Exception as e:
    print(f"\nError in send_notification_for_flight: {e}")
    import traceback
    traceback.print_exc()
    