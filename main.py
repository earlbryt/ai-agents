# main.py
from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import uvicorn
from api_agent import agent  # Import your existing agent code
from langchain_core.messages import HumanMessage

app = FastAPI()

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def get():
    # Serve the HTML file
    with open("static/index.html") as f:
        return HTMLResponse(f.read())


from api_agent import agent  # Import your existing agent code
from langchain_core.messages import HumanMessage

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    while True:
        flight_code = await websocket.receive_text()
        messages = [HumanMessage(content=flight_code)]
        result = agent.graph.invoke({"messages": messages})
        response = result["messages"][-1].content
        await websocket.send_text(response)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
    
    
from fastapi import FastAPI
from api_agent import agent
from langchain_core.messages import HumanMessage

app = FastAPI()

@app.post("/example_endpoint")
async def process_message(message: str):
    messages = [HumanMessage(content=flight_code)]
    result = agent.graph.invoke({"messages": messages})
    response = result["messages"][-1].content  