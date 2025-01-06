from langgraph.graph import StateGraph, END
from langchain_core.messages import AnyMessage, SystemMessage, HumanMessage, ToolMessage

from langchain_core.agents import AgentAction, AgentFinish
from langchain_core.messages import ToolCall, ToolMessage
from langchain_core.messages import BaseMessage
from langchain_core.tools import tool
from langchain_groq import ChatGroq

from typing import Dict, TypedDict, Annotated, List, Union
from IPython.display import Image
import operator
import requests
import json
import os

from dotenv import load_dotenv
load_dotenv()

api_key=os.getenv("GROQ_API_KEY")
api_key = os.getenv("AVIATION-STACK_API_KEY")


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]



class Agent:
  def __init_(self, model, tools, system=""):   # function to initialize the graph with state, nodes, edges
    self.system = system  
    graph = StateGraph(AgentState)  # initialize the agent state. Can be accessed anywhere in the graph (nodes, edges)
    graph.add_node("llm", self.call_groq)  # add llm node
    graph.add_node("action, self.take_action")  # add action node
    graph.add_conditional_edges(
      "llm", # first node in graph
      self.exists_action,  # function to decide which action to take after calling llm. Decides whether to take an action or to END.
      {True: "action", False: END}
    )
    graph.add_edge("action", llm)  # edge to loop back the response to the llm from the action,
    graph.set_entry_point("llm")  # entry point for the graph
    self.graph = graph.compile()  # what we call after doing all the setup. It is turned into a langchain runnable.
    self.tools = {t.name: t for t in tools}
    self.model = model.bind_tools(tools) # bind the tools to our model
    
  def exists_action(self, state: AgentState):
    result = state['messages'][-1]
    return len(result.tool_calls) > 0

  def call_groq(self, state: AgentState):
      messages = state['messages']
      if self.system:
          messages = [SystemMessage(content=self.system)] + messages
      message = self.model.invoke(messages)
      return {'messages': [message]}

  def take_action(self, state: AgentState):
      tool_calls = state['messages'][-1].tool_calls
      results = []
      for t in tool_calls:
          print(f"Calling: {t}")
          if not t['name'] in self.tools:      # check for bad tool name from LLM
              print("\n ....bad tool name....")
              result = "bad tool name, retry"  # instruct LLM to retry if bad
          else:
              result = self.tools[t['name']].invoke(t['args'])
          results.append(ToolMessage(tool_call_id=t['id'], name=t['name'], content=str(result)))
      print("Back to the model!")
      return {'messages': results}




@tool("fetch_data")
def fetch_data(flight_icao: str) -> dict:
    """
        Gets flight data from the aviation stack API data provider.
        Used to deliver real-time flight information to air travellers about their specific flight.
        
        Args:
            flight_icao (str): The ICAO flight identifier
            
        Returns:
            dict: Parsed JSON data as a dictionary
            
        Raises:
            requests.exceptions.RequestException: If API request fails
            ValueError: If API key is not set or flight_icao is invalid
        """
    try:
        response = requests.get(
            f"https://api.aviationstack.com/v1/flights",
            params={
              "access_key": api_key,
              "flight_icao": flight_icao,
              }
        )
        response.raise_for_status()  # Raise an exception for bad status codes
        return response.json()  # Parse JSON response
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data: {e}")
        return {"data": []}  # Return empty data structure on error


tool = [fetch_data]

prompt = """You are a smart tool use assistant. Use the aviation api to get information on a specific flight \
You are allowed to make multiple calls (either together or in sequence). \
Only look up information about the specific user flight given the flight code from the user / human. \
The tool should take in as input the flight number from the user prompt. An example of a flight number is AA3456 or DFT7894. It is a string of alphabets followed by numbers.
  
"""
# If you need to look up some information before asking a follow up question, you are allowed to do that using the search engine tool!

model = ChatGroq(model="llama3-8b-8192")

bot = Agent(model, [tool], system=prompt)


print(Image(bot.graph.get_graph().draw_png()))

# messages = [HumanMessage(content="")]
# result = bot.graph.invoke({"messages": messages})





