from typing import Type
from dotenv import load_dotenv

from langgraph.prebuilt import create_react_agent
from langchain_core.tools import BaseTool, Tool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from tools.fetch_match_overview import fetch_match_overview
from tools.fetch_all_matches import fetch_matches
from tools.send_telegram_message import send_telegram_message

load_dotenv()

# Pydantic models for tool arguments
class FetchMatchDetailsInput(BaseModel):
    url: str = Field(description="should be a url for a match")

class SendTelegramMessageInput(BaseModel):
    message: str = Field(description="should be a string of the telegram message to send")

# Define tools
class FetchMatchDetailsTool(BaseTool):
    name: str = "fetch_match_overview"
    description: str = "Useful for when you need details on a single match."
    args_schema: Type[BaseModel] = FetchMatchDetailsInput

    def _run(self, url: str) -> str:
        return fetch_match_overview(url)

class SendTelegramMessageTool(BaseTool):
    name: str = "send_telegram_message"
    description: str = "Useful for when you need to send a telegram message."
    args_schema: Type[BaseModel] = SendTelegramMessageInput

    def _run(self, message: str) -> str:
        return send_telegram_message(message)

def get_all_matches(*args, **kwargs):
    return fetch_matches()

tools = [
    FetchMatchDetailsTool(),
    SendTelegramMessageTool(),
    Tool(
        name="GetAllMatches",
        func=get_all_matches,
        description="Get all available matches for the day",
    ),
]

llm = ChatOpenAI(model="gpt-4o")

#create agent
agent = create_react_agent(llm, tools)


#query
response = agent.invoke({"messages":[{"role":"user", "content":"You are an expert soccer punter. I need your predictions on all football matches available today for a parlay. For each available match, analyze the match overview including stats, betting analysis, match news, head to head,etc and come up with an educated prediction on the most likely match outcome. Do not depend on the betting analysis given by the match overview, reason about all the information given and come up with a prediction yourself. Outcomes can include any option available in major sports bookies E.g: '{Home/Away} win', 'Draw', '{Home/Away} win or draw', 'Total goals {over/under}{x}', '{Home/Away} goals{over/under}{x}', 'Both Teams to score{Yes/No}', '{Match stats(cards, corners {over/under})}', '{Player stats}(goals, assists)', '{Exact scoreline}', etc. Send a telegram message with a list of the predictions for all available matches if there are any and if there are none, just send the message 'No High priority matches available today😓.'"}]})
print(f"Response: {response['messages'][-1].content}")

