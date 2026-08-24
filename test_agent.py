"""
Test the ThermoPulse LangGraph agent end-to-end: give it a natural-language
request, let it decide which tool(s) to call, and print its final answer.
"""

import asyncio
from agent import build_agent


async def main():
    agent = build_agent()

    question = (
        "Assess heat risk for the area between latitude 40.705 and 40.718, "
        "longitude -74.017 and -74.003, on 2024-07-15 at 14:00. "
        "Only look at the top 3 hottest points to keep it quick. "
        "Tell me which spot is riskiest and why."
    )

    result = await agent.ainvoke({
        "messages": [{"role": "user", "content": question}]
    })

    print("\n=== Agent's final answer ===\n")
    print(result["messages"][-1].content)


if __name__ == "__main__":
    asyncio.run(main())