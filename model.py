import os
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

load_dotenv()

GROQ_API_KEY = os.getenv('GROQ_API_KEY')

from langchain_groq import ChatGroq

chat_model = ChatGroq(model_name="llama3-8b-8192")

# result = chat_model.invoke(
#   [HumanMessage(
#     content="Tell me a joke about the weather"
#     )])

joke_prompt = ChatPromptTemplate.from_messages([
  ("system", "You are a helpful assistant that tells jokes."),
  ("human", "Tell me a joke about the weather"),
  ("assistant", "Why did the meteorologist quit his job? Because he couldn't predict his future."),
  ("human", "That was terrible, tell me a joke about {topic}")
])

chain = joke_prompt | chat_model


str_chain = chain | StrOutputParser()
# result = str_chain.invoke({"topic": "weather"})

# for chunk in str_chain.stream({"topic": "AI"}):
  # print(chunk, end="/")
  
from datetime import date

prompt = ChatPromptTemplate.from_messages([
  ("system", "You know that the current date is {current_date}"),
  ("human", "{question}")
])

chain = prompt | chat_model | StrOutputParser()

result = chain.invoke({
  "question": "What is the date today?",
  "current_date": date.today()
})

print(result)