from langgraph.graph import StateGraph, END
from langchain_core.messages import AnyMessage, SystemMessage, HumanMessage, ToolMessage, AIMessage
from langchain_core.messages import ToolCall, ToolMessage
from langchain_core.tools import tool
from langchain_groq import ChatGroq
from typing import Dict, TypedDict, Annotated, List
import operator
import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

groq_api_key = os.getenv("GROQ_API_KEY")
aviation_stack_api_key = os.getenv("AVIATION_STACK_API_KEY")


class AgentState(TypedDict):
    messages: Annotated[List[AnyMessage], operator.add]

class Agent:
    def __init__(self, model, tools, system=""):
        self.system = system
        self.tools = {t.name: t for t in tools}
        self.model = model.bind_tools(tools)
        
        graph = StateGraph(AgentState)
        graph.add_node("llm", self.call_groq)
        graph.add_node("action", self.take_action)
        
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

    def call_groq(self, state: AgentState) -> Dict:
        messages = state['messages']
        if self.system:
            messages = [SystemMessage(content=self.system)] + messages
        message = self.model.invoke(messages)
        return {'messages': [message]}

    def take_action(self, state: AgentState) -> Dict:
        """Execute tool calls with proper error handling"""
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
                print(f"Detailed error in take_action: {str(e)}")  
                print(f"Tool call structure: {tool_call}")  
                results.append(
                    ToolMessage(
                        tool_call_id=getattr(tool_call, 'id', 'unknown'),
                        name=getattr(tool_call, 'name', 'unknown'),
                        content=f"Error executing tool: {str(e)}"
                    )
                )
        
        return {'messages': results}

@tool
def fetch_data(flight_icao: str) -> dict:
    """Gets flight data for a specific flight."""
    try:
        response = requests.get(
            "https://api.aviationstack.com/v1/flights",
            params={
                "access_key": aviation_stack_api_key,
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


prompt = """You are a flight information assistant. Use the fetch_data tool to get flight information on only the current flight.
When a user provides a flight code:
Use fetch_data to get flight information
Always validate flight codes before making API calls.
Return your output in a well structured json string!!! that includes the following:

* Flight number
* Airline
* Departure airport
* Arrival airport
* Flight status
* Departure time
* Arrival time
* Duration
* Delay
* Gate
* Terminal
* Live : a json string containing the following:
      Updated time
      latitude
      longitude
      altitude
      direction
      speed_horizontal
      speed_vertical
    Make sure you always add these fields into the live field and use null when they are empty      
* Description : a short description of the all non-empty data fields above
Return null for a value that is not present.

"""

tools = [fetch_data]
model = ChatGroq(model="llama-3.3-70b-versatile")
agent = Agent(model=model, tools=tools, system=prompt)

