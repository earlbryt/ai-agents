from langgraph.graph import StateGraph, END
from langchain_core.messages import AnyMessage, SystemMessage, HumanMessage, ToolMessage, AIMessage
from langchain_core.messages import ToolCall, ToolMessage
from langchain_core.tools import tool
from langchain_groq import ChatGroq
from typing import Dict, TypedDict, Annotated, List, Tuple, Optional
from datetime import datetime
import operator
import requests
import json
import os
from dotenv import load_dotenv
from twilio.rest import Client
from enum import Enum

# Load environment variables
load_dotenv()

# Access environment variables
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
AVIATION_STACK_API_KEY = os.getenv("AVIATION_STACK_API_KEY")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")

# Notification Enums
class NotificationPriority(Enum):
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"

class NotificationChannel(Enum):
    SMS = "sms"
    EMAIL = "email"
    VOICE = "voice"


# State classes
class AgentState(TypedDict):
    messages: Annotated[List[AnyMessage], operator.add]

class NotificationState(TypedDict):
    messages: Annotated[List[AnyMessage], operator.add]
    flight_data: dict
    notification_sent: bool
    selected_channels: List[NotificationChannel]
    priority: NotificationPriority

# Flight Notification Node
class FlightNotificationNode:
    def __init__(self, twilio_client: Client, twilio_phone: str, sender_email: str):
        self.twilio_client = twilio_client
        self.twilio_phone = twilio_phone
        self.sender_email = sender_email
        self.graph = self._create_notification_graph()

    def _create_notification_graph(self) -> StateGraph:
        graph = StateGraph(NotificationState)
        
        # Add nodes
        graph.add_node("evaluate_priority", self._evaluate_priority)
        graph.add_node("select_channels", self._select_channels)
        graph.add_node("send_sms", self._send_sms)
        graph.add_node("send_email", self._send_email)
        graph.add_node("send_voice", self._send_voice)
        
        # Add conditional edges
        graph.add_conditional_edges(
            "evaluate_priority",
            self._should_notify,
            {True: "select_channels", False: END}
        )
        
        graph.add_conditional_edges(
            "select_channels",
            self._check_sms_needed,
            {True: "send_sms", False: "select_channels"}
        )
        
        graph.add_conditional_edges(
            "select_channels",
            self._check_email_needed,
            {True: "send_email", False: "select_channels"}
        )
        
        graph.add_conditional_edges(
            "select_channels",
            self._check_voice_needed,
            {True: "send_voice", False: END}
        )
        
        graph.set_entry_point("evaluate_priority")
        
        return graph.compile()

    # Evaluation and channel selection methods
    def _evaluate_priority(self, state: NotificationState) -> Dict:
        flight_data = state['flight_data']
        status = flight_data.get('Flight status', '').lower()
        delay = flight_data.get('Delay')
        
        priority = NotificationPriority.NORMAL
        
        if status in ['diverted', 'canceled']:
            priority = NotificationPriority.HIGH
        elif status == 'delayed' or (delay and delay > 30):
            priority = NotificationPriority.HIGH
        elif status in ['landed', 'arrived']:
            priority = NotificationPriority.NORMAL
            
        return {**state, 'priority': priority}

    def _select_channels(self, state: NotificationState) -> Dict:
        priority = state['priority']
        channels = []
        
        if priority == NotificationPriority.HIGH:
            channels = [NotificationChannel.SMS, NotificationChannel.EMAIL, NotificationChannel.VOICE]
        elif priority == NotificationPriority.NORMAL:
            channels = [NotificationChannel.SMS, NotificationChannel.EMAIL]
        else:
            channels = [NotificationChannel.EMAIL]
            
        return {**state, 'selected_channels': channels}

    # Notification sending methods
    def _send_sms(self, state: NotificationState) -> Dict:
        try:
            flight_data = state['flight_data']
            priority = state['priority']
            message = self._generate_message(flight_data, priority)
            
            if priority == NotificationPriority.HIGH:
                message = "URGENT: " + message
                
            self.twilio_client.messages.create(
                body=message,
                from_=self.twilio_phone,
                to=flight_data.get('user_phone')
            )
            return {**state, 'notification_sent': True}
            
        except Exception as e:
            print(f"SMS sending failed: {str(e)}")
            return {**state, 'notification_sent': False}

    def _send_email(self, state: NotificationState) -> Dict:
        try:
            flight_data = state['flight_data']
            priority = state['priority']
            subject = self._generate_subject(flight_data, priority)
            body = self._generate_message(flight_data, priority)
            
            # Implement email sending logic here
            print(f"Would send email: {subject}\n{body}")
            
            return {**state, 'notification_sent': True}
        except Exception as e:
            print(f"Email sending failed: {str(e)}")
            return {**state, 'notification_sent': False}

    def _send_voice(self, state: NotificationState) -> Dict:
        if state['priority'] != NotificationPriority.HIGH:
            return state
            
        try:
            flight_data = state['flight_data']
            message = self._generate_message(flight_data, state['priority'])
            
            self.twilio_client.calls.create(
                twiml=f'<Response><Say>{message}</Say></Response>',
                from_=self.twilio_phone,
                to=flight_data.get('user_phone')
            )
            
            return {**state, 'notification_sent': True}
        except Exception as e:
            print(f"Voice call failed: {str(e)}")
            return {**state, 'notification_sent': False}

    # Helper methods
    def _generate_message(self, flight_data: Dict, priority: NotificationPriority) -> str:
        status = flight_data.get('Flight status', '').lower()
        flight_num = flight_data.get('Flight number')
        
        messages = {
            'delayed': f"Flight {flight_num} is delayed. New departure time: {flight_data.get('Departure time')}",
            'diverted': f"Flight {flight_num} has been diverted. We will contact you with more information.",
            'canceled': f"Flight {flight_num} has been canceled. Please check your email for rebooking options.",
            'landed': f"Flight {flight_num} has arrived at {flight_data.get('Arrival time')}.",
            'arrived': f"Flight {flight_num} has arrived at {flight_data.get('Arrival time')}. Please proceed to baggage claim."
        }
        
        return messages.get(status, f"Update for flight {flight_num}: {flight_data.get('Description')}")

    def _generate_subject(self, flight_data: Dict, priority: NotificationPriority) -> str:
        status = flight_data.get('Flight status', '').lower()
        flight_num = flight_data.get('Flight number')
        
        if priority == NotificationPriority.HIGH:
            return f"URGENT: Flight {flight_num} {status.capitalize()}"
        return f"Flight {flight_num} Update: {status.capitalize()}"

    # Conditional check methods
    def _should_notify(self, state: NotificationState) -> bool:
        status = state['flight_data'].get('Flight status', '').lower()
        return status in ['delayed', 'diverted', 'canceled', 'landed', 'arrived']

    def _check_sms_needed(self, state: NotificationState) -> bool:
        return NotificationChannel.SMS in state['selected_channels']

    def _check_email_needed(self, state: NotificationState) -> bool:
        return NotificationChannel.EMAIL in state['selected_channels']

    def _check_voice_needed(self, state: NotificationState) -> bool:
        return NotificationChannel.VOICE in state['selected_channels']

# Tools
@tool
def send_sms_notification(message: str, phone_number: str, priority: str = "normal") -> str:
    """
    Send SMS notification to user.
    Args:
        message: The message to send
        phone_number: The recipient's phone number
        priority: Priority level (high, normal, low)
    """
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        
        if priority == "high":
            message = "URGENT: " + message
            
        client.messages.create(
            body=message,
            from_=TWILIO_PHONE_NUMBER,
            to=phone_number
        )
        return f"SMS sent successfully to {phone_number}"
    except Exception as e:
        return f"Failed to send SMS: {str(e)}"

@tool
def send_voice_notification(message: str, phone_number: str) -> str:
    """
    Send voice notification for high-priority alerts.
    Args:
        message: The message to be spoken
        phone_number: The recipient's phone number
    """
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        client.calls.create(
            twiml=f'<Response><Say>{message}</Say></Response>',
            from_=TWILIO_PHONE_NUMBER,
            to=phone_number
        )
        return f"Voice call sent successfully to {phone_number}"
    except Exception as e:
        return f"Failed to send voice call: {str(e)}"

@tool
def send_email_notification(subject: str, body: str, to_email: str) -> str:
    """
    Send email notification.
    Args:
        subject: Email subject
        body: Email body
        to_email: Recipient's email address
    """
    try:
        # Implement your email sending logic here
        # For demonstration, we'll just print
        print(f"Would send email:\nTo: {to_email}\nSubject: {subject}\nBody: {body}")
        return f"Email sent successfully to {to_email}"
    except Exception as e:
        return f"Failed to send email: {str(e)}"
    
@tool
def fetch_data(flight_icao: str) -> dict:
    """Gets flight data for a specific flight."""
    try:
        response = requests.get(
            "https://api.aviationstack.com/v1/flights",
            params={
                "access_key": AVIATION_STACK_API_KEY,
                "flight_icao": flight_icao,
            },
            timeout=10
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        return {"error": f"API request failed: {str(e)}"}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}

# Main Agent Class
class Agent:
    def __init__(self, model, tools, system=""):
        self.system = system
        self.tools = {t.name: t for t in tools}
        self.model = model.bind_tools(tools)
        
        graph = StateGraph(AgentState)
        
        # Add basic nodes
        graph.add_node("llm", self.call_groq)
        graph.add_node("action", self.take_action)
        
        # Add edges
        graph.add_conditional_edges(
            "llm",
            self.exists_action,
            {True: "action", False: END}
        )
        graph.add_edge("action", "llm")
            
        graph.set_entry_point("llm")
        self.graph = graph.compile()


    def exists_action(self, state: AgentState) -> bool:
        last_message = state['messages'][-1]
        return hasattr(last_message, 'tool_calls') and bool(last_message.tool_calls)

    def should_notify(self, state: AgentState) -> bool:
        last_message = state['messages'][-1]
        if isinstance(last_message, ToolMessage):
            try:
                flight_data = json.loads(last_message.content)
                status = flight_data.get('Flight status', '').lower()
                return status in ['delayed', 'diverted', 'canceled', 'landed', 'arrived']
            except:
                return False
        return False

    def call_groq(self, state: AgentState) -> Dict:
        messages = state['messages']
        if self.system:
            messages = [SystemMessage(content=self.system)] + messages
        message = self.model.invoke(messages)
        return {'messages': [message]}

    def take_action(self, state: AgentState) -> Dict:
        last_message = state['messages'][-1]
        if not hasattr(last_message, 'tool_calls'):
            return {'messages': []}
            
        results = []
        for tool_call in last_message.tool_calls:
            try:
                if isinstance(tool_call, dict):
                    tool_name = tool_call.get('name')
                    tool_args = tool_call.get('args', {})
                    tool_id = tool_call.get('id')
                else:
                    tool_name = tool_call.name
                    tool_args = tool_call.args
                    tool_id = tool_call.id

                if tool_name not in self.tools:
                    result = f"Error: Tool '{tool_name}' not found"
                else:
                    tool = self.tools[tool_name]
                    result = tool.invoke(tool_args)
                
                results.append(
                    ToolMessage(
                        tool_call_id=tool_id,
                        name=tool_name,
                        content=str(result)
                    )
                )
            except Exception as e:
                print(f"Error in take_action: {str(e)}")
                results.append(
                    ToolMessage(
                        tool_call_id=getattr(tool_call, 'id', 'unknown'),
                        name=getattr(tool_call, 'name', 'unknown'),
                        content=f"Error executing tool: {str(e)}"
                    )
                )
        
        return {'messages': results}


def main():
    # System prompt remains the same
    prompt = """You are a flight information assistant. Use the fetch_data tool to get flight information and send appropriate notifications based on flight status.

    When a user provides a flight code:
    1. Use fetch_data to get flight information
    2. Always validate flight codes before making API calls
    3. Analyze the flight status and determine notification priority:
       - For delays, cancellations, or diversions: Use high priority (voice + SMS + email)
       - For normal updates (landed, arrived): Use normal priority (SMS + email)
       - For routine updates: Use low priority (email only)
    4. Send appropriate notifications using the notification tools:
       - send_sms_notification for SMS
       - send_voice_notification for urgent messages
       - send_email_notification for email updates
    
    Return your output in a well structured json string that includes:
    * Flight number
    * Airline
    * Departure airport
    * Arrival airport
    * Flight status
    * Departure time
    * Arrival time
    * Duration
    * Delay
    * Live : a json string containing:
          Updated time
          latitude
          longitude
          altitude
          direction
          speed_horizontal
          speed_vertical
    * Description : a short description of all non-empty data fields above
    
    Return null for any value that is not present.
    """

    # Initialize tools and model
    tools = [
        fetch_data,
        send_sms_notification,
        send_voice_notification,
        send_email_notification
    ]
    model = ChatGroq(model="llama3-70b-8192")
    
    # Create agent
    agent = Agent(
        model=model,
        tools=tools,
        system=prompt
    )

    # Example usage with test contact info
    test_contact = {
        "phone": "+233553792221",
        "email": "coralearl04@gmail.com.com"
    }

    messages = [
        HumanMessage(content="What are the details of RJA3813?")
    ]

    # Run the agent
    result = agent.graph.invoke({"messages": messages})
    
    # Improved message printing
    for msg in result["messages"]:
        if isinstance(msg, HumanMessage):
            print("\nHuman:", msg.content)
        elif isinstance(msg, AIMessage):
            print("\nAssistant:", msg.content)
            if hasattr(msg, 'additional_kwargs') and 'tool_calls' in msg.additional_kwargs:
                print("\nTool Calls:")
                for tool_call in msg.additional_kwargs['tool_calls']:
                    # Handle dictionary format
                    tool_name = tool_call.get('function', {}).get('name', tool_call.get('name', 'Unknown'))
                    tool_args = tool_call.get('function', {}).get('arguments', tool_call.get('args', '{}'))
                    print(f"- Tool: {tool_name}")
                    print(f"  Arguments: {tool_args}")
        elif isinstance(msg, ToolMessage):
            print("\nTool Response:")
            try:
                # Try to parse and pretty print JSON response
                response_data = json.loads(msg.content)
                print(json.dumps(response_data, indent=2))
            except json.JSONDecodeError:
                # If not JSON, print as is
                print(msg.content)
            print(f"Tool Name: {msg.name}")

if __name__ == "__main__":
    main()