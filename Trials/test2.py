# test_agent_invocation.py
from test import agent
from langchain_core.messages import HumanMessage

def test_agent_invocation(flight_code: str):
    # Prepare the message (adjust if needed based on agent input requirements)
    messages = [HumanMessage(content=flight_code)]
    
    try:
        # Invoke the agent (ensure that 'graph' and 'invoke' are accessible as expected)
        result = agent.graph.invoke({"messages": messages})
        
        # Extract and print the response message
        if "messages" in result and len(result["messages"]) > 0:
            response = result["messages"][-1].content
            print("Agent Response:", response)
        else:
            print("No valid response from agent.")
    except Exception as e:
        print(f"Error during agent invocation: {e}")

if __name__ == "__main__":
    # Test with a sample flight code
    flight_code = "MDA921"
    test_agent_invocation(flight_code)
    
    
"""    
Once you get the response, only print out information about only the current flight for the day (today) / the most recent flight.
Your response should include information about the entire flight in natural language. Be detailed in your response about departure airports, destination, and everything else that is important so tha the user can be well informed about their flight.
Do not include information about the airline or aircraft. Include departure, destination, time of arrival.
Do not add the date to your response.
Your output should be in the format:

Your flight from {arrival} to {destination} is scheduled to depart at {time_to_departure}. No visible weather or delays will occur.
or
Your flight from {arrival} to {destination} will land at {time_to_arrival}.  No visible weather or delays will occur.

The arrival and destination should be full names of the cities 
"""    
