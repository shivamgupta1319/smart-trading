import os
import httpx
import yfinance as yf
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

class LLMClient:
    def __init__(self):
        self.openrouter_key = os.getenv("OPENROUTER_API_KEY")
        self.gemini_key = os.getenv("GEMINI_API_KEY")

    async def generate(self, prompt: str) -> str:
        if self.openrouter_key:
            return await self._call_openrouter(prompt)
        elif self.gemini_key:
            return await self._call_gemini(prompt)
        else:
            return (
                "> [!WARNING]\n> **Missing API Keys!**\n\n"
                "To enable AI Research & Analysis, please add `OPENROUTER_API_KEY` or `GEMINI_API_KEY` "
                "to your `apps/engine/.env` file and restart the engine container.\n\n"
                "Example:\n```env\nOPENROUTER_API_KEY=\"sk-or-v1-...\"\n```\n"
            )

    async def _call_openrouter(self, prompt: str) -> str:
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.openrouter_key}",
            "HTTP-Referer": "http://localhost:3000",
            "X-Title": "SmartTrader AI",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "openai/gpt-4o-mini", # Fast, cheap, and smart
            "messages": [
                {"role": "system", "content": "You are an expert Indian Stock Market Quantitative Analyst. You provide concise, insightful, and highly technical fundamental, technical, and sentimental analysis."},
                {"role": "user", "content": prompt}
            ]
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            else:
                return f"Error from OpenRouter: {resp.text}"

    async def _call_gemini(self, prompt: str) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.gemini_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{
                "parts": [{"text": "You are an expert Indian Stock Market Quantitative Analyst.\n\n" + prompt}]
            }]
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                try:
                    return data["candidates"][0]["content"]["parts"][0]["text"]
                except KeyError:
                    return "Error parsing Gemini response."
            else:
                return f"Error from Gemini: {resp.text}"

llm = LLMClient()

@router.get("/dashboard")
async def get_dashboard_analysis():
    try:
        # Fetch Nifty 50 data to represent the Indian market
        ticker = yf.Ticker("^NSEI")
        hist = ticker.history(period="1mo")
        news = ticker.news
        
        if hist.empty:
            current_price = "Unknown"
            price_change = "Unknown"
        else:
            current_price = hist["Close"].iloc[-1]
            prev_price = hist["Close"].iloc[0] # 1 month ago
            price_change = ((current_price - prev_price) / prev_price) * 100

        news_titles = [item.get("title", "") for item in news[:5]] if news else ["No recent news available"]

        prompt = f"""
        Analyze the current state of the Indian Stock Market (Nifty 50).
        
        Current Nifty 50 Price: {current_price}
        1-Month Change: {price_change}%
        
        Recent Market Headlines:
        {chr(10).join(news_titles)}
        
        Provide a 3-4 paragraph market overview, focusing on sentiment, technical trends based on the 1-month change, and actionable insights for traders. Format as markdown.
        """
        
        analysis = await llm.generate(prompt)
        return {"status": "success", "analysis": analysis}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.get("/stock/{symbol}")
async def get_stock_analysis(symbol: str):
    # Ensure NSE suffix
    yf_symbol = symbol if symbol.endswith(".NS") else f"{symbol}.NS"
    try:
        ticker = yf.Ticker(yf_symbol)
        info = ticker.info
        hist = ticker.history(period="6mo")
        news = ticker.news
        
        if hist.empty:
            return {"status": "error", "message": "Failed to fetch historical data for this stock."}
            
        current_price = hist["Close"].iloc[-1]
        high_52w = info.get("fiftyTwoWeekHigh", "Unknown")
        low_52w = info.get("fiftyTwoWeekLow", "Unknown")
        market_cap = info.get("marketCap", "Unknown")
        pe_ratio = info.get("trailingPE", "Unknown")
        sector = info.get("sector", "Unknown")
        
        news_titles = [item.get("title", "") for item in news[:3]] if news else ["No recent news available"]
        
        prompt = f"""
        Provide a comprehensive quantitative research report for the Indian stock: {symbol} (Sector: {sector}).
        
        Data Points:
        - Current Price: {current_price}
        - 52-Week High: {high_52w}
        - 52-Week Low: {low_52w}
        - Market Cap: {market_cap}
        - P/E Ratio: {pe_ratio}
        
        Recent News Headlines:
        {chr(10).join(news_titles)}
        
        Please generate a professional Markdown report with the following structure:
        1. **Executive Summary**: 2 sentences on the current state of the stock.
        2. **Fundamental Analysis**: Interpret the P/E, Market Cap, and any obvious fundamental traits of this sector.
        3. **Technical Context**: Interpret the current price relative to its 52-week high/low and suggest potential support/resistance zones.
        4. **Sentiment & News Analysis**: How do the recent headlines reflect on the stock's short-term potential?
        """
        
        analysis = await llm.generate(prompt)
        return {"status": "success", "analysis": analysis}
    except Exception as e:
        return {"status": "error", "message": str(e)}
