from typing import List, Dict, Any  # Type Safety
from langchain_groq import ChatGroq  
from langgraph.graph import StateGraph, END  
from pydantic import BaseModel  # Pydantic data validation
from dotenv import load_dotenv
import os

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# THE SCROLL should look like this!!!
class ChatState(BaseModel):
  messages: List[Dict[str, str]] = []
  current_input: str = ""
  tools_output : Dict[str, str] = {}
  final_response : str = ""  ## I'm not using any tools at the moment
  
# The first badass node. He adds the user input to the scroll messages  
# Why is he an async? I do not see him performing an async operation
async def process_user_input(state: ChatState) -> ChatState:
    # He adds the new user message to the existing messages in THE SCROLL!!
    messages = state.messages + [{"role": "user", "content": state.current_input}]
    # This is the updated SCROLL!!
    return ChatState(
        messages=messages,
        current_input=state.current_input,
        tools_output=state.tools_output
    )

# Badass node 2
# He sends the scroll to LLama, who gives us a response    
async def generate_ai_response(state: ChatState) -> ChatState:
    """Generate AI response"""
    # Hello Llama
    llm = ChatGroq(
        temperature=0.7,
        model="llama-3.3-70b-versatile",
        api_key=GROQ_API_KEY
    )
    response = await llm.ainvoke(state.messages)
    # We take the message from Llama's response. Llama adds a few more things in his response other than the message. But we want only the message, so we get that.
    response_content = response.content
    # We add Llama's response  to the SCROLL!! Now we have the user message and Llama's message in the messages of the SCROLL!!
    messages = state.messages + [{"role": "assistant", "content": response_content}]
    # Our updated SCROLL!! It's shared throughout our kingdom (every junction and every river)
    return ChatState(
        messages=messages,
        current_input=state.current_input,
        should_continue=True
    )   

# He was meant to be a conditional router. But he's sick, so we'll have to give him some medication later - maybe not   
# He decides whether Llama should continue talking to the user or, sadly, end the conversation.
def should_continue(state: ChatState) -> str:
    """Decide whether to continue talking to the user"""
    if "goodbye" in state.current_input.lower():
        return "end"
    return "continue"     

# These are the golden rivers 
# And now, I give life to you, Kingdom of LangGraphia!!
workflow = StateGraph(ChatState) 

# I bestow unto you:
workflow.add_node("process_user_input", process_user_input) # Your first junction
workflow.add_node("generate_ai_response", generate_ai_response) # Your second junction

workflow.add_edge("process_user_input", "generate_ai_response")  # Your first river, he flows from a to b
workflow.add_edge("generate_ai_response", END)  # Your second river, he flows from b to END. Sad!

workflow.set_entry_point("process_user_input")  # The mountains from which the golden river flows

# workflow.add_conditional_edges("generate_ai_response", should_continue, {"continue": "process_user_input", "end": END})

app = workflow.compile()

# He's meant to 
# - get the user message from the terminal
# - add it to the SCROLL 
# - send the SCROLL to Llama 
# - add Llama's response to the SCROLL
# - print out Llama's response to the terminal

# - or throw an Exception
async def chat():
    state = ChatState()
    while True:
        try:
          user_input = input("You: ")
          state.current_input = user_input
          state = await app.ainvoke(state)
          print("Bot:", state.messages[-1]["content"])
        except Exception as e:
            print(f"An error occurred: {e}")
            break

# Run the Kingdom
import asyncio
asyncio.run(chat())
