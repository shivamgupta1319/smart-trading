import os
import httpx
import yfinance as yf
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime

router = APIRouter()

def parse_news_item(item):
    if not isinstance(item, dict):
        return {"title": "", "publisher": "", "link": "", "providerPublishTime": 0}
        
    if "content" in item and isinstance(item["content"], dict):
        c = item["content"]
        pub_date = c.get("pubDate") or ""
        # convert '2026-02-09T09:20:18Z' to timestamp
        try:
            timestamp = int(datetime.strptime(pub_date, "%Y-%m-%dT%H:%M:%SZ").timestamp())
        except:
            timestamp = 0
            
        provider = c.get("provider") or {}
        click_through = c.get("clickThroughUrl") or {}
            
        return {
            "title": c.get("title") or "",
            "publisher": provider.get("displayName") or "",
            "link": click_through.get("url") or "",
            "providerPublishTime": timestamp
        }
    else:
        return {
            "title": item.get("title") or "",
            "publisher": item.get("publisher") or "",
            "link": item.get("link") or "",
            "providerPublishTime": item.get("providerPublishTime") or 0
        }

class LLMClient:
    def __init__(self):
        self.openrouter_key = os.getenv("OPENROUTER_API_KEY")
        self.gemini_key = os.getenv("GEMINI_API_KEY")

    async def generate(self, prompt: str) -> str:
        # Try providers in order, falling back on any failure so a single dead
        # key (e.g. a revoked OpenRouter key) doesn't take AI analysis down when
        # another working provider is configured.
        errors = []
        if self.openrouter_key:
            try:
                return await self._call_openrouter(prompt)
            except Exception as e:
                errors.append(f"OpenRouter: {e}")
        if self.gemini_key:
            try:
                return await self._call_gemini(prompt)
            except Exception as e:
                errors.append(f"Gemini: {e}")
        if errors:
            return (
                "> [!WARNING]\n> **AI analysis unavailable.**\n\n"
                "All configured LLM providers failed:\n\n- "
                + "\n- ".join(errors)
                + "\n\nCheck your `OPENROUTER_API_KEY` / `GEMINI_API_KEY` in the engine `.env`."
            )
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
                raise RuntimeError(f"HTTP {resp.status_code} {resp.text}")

    async def _call_gemini(self, prompt: str) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={self.gemini_key}"
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

        parsed_news = [parse_news_item(n) for n in news] if news else []
        news_titles = [n["title"] for n in parsed_news[:5] if n["title"]] or ["No recent news available"]

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

@router.get("/news")
async def get_market_news():
    try:
        nifty = yf.Ticker("^NSEI")
        sensex = yf.Ticker("^BSESN")
        
        nifty_news = nifty.news or []
        sensex_news = sensex.news or []
        
        # Also fetch news for top constituents to ensure we have enough data
        reliance = yf.Ticker("RELIANCE.NS").news or []
        hdfc = yf.Ticker("HDFCBANK.NS").news or []
        tcs = yf.Ticker("TCS.NS").news or []
        
        # Combine and deduplicate based on title, limit to top 10 recent
        seen_titles = set()
        all_news = []
        raw_news_combined = nifty_news + sensex_news + reliance + hdfc + tcs
        
        for item in raw_news_combined:
            parsed = parse_news_item(item)
            title = parsed["title"]
            if title and title not in seen_titles:
                seen_titles.add(title)
                all_news.append(parsed)
                if len(all_news) >= 10:
                    break

        all_news.sort(key=lambda x: x["providerPublishTime"], reverse=True)
        news_titles = [item["title"] for item in all_news]
        
        if not news_titles:
            return {"status": "success", "analysis": "No recent news found for the Indian Stock Market.", "articles": []}

        prompt = f"""
        You are an expert Indian Stock Market Quantitative Analyst.
        
        Here are the latest breaking news headlines affecting the Indian Stock Market:
        {chr(10).join(news_titles)}
        
        Provide a concise, 3-paragraph summary of how these news events might impact the overall market sentiment today. Format as markdown. Use bullet points if discussing specific sectors.
        """
        
        analysis = await llm.generate(prompt)
        
        return {
            "status": "success",
            "analysis": analysis,
            "articles": all_news
        }
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
        
        parsed_news = [parse_news_item(n) for n in news] if news else []
        news_titles = [n["title"] for n in parsed_news[:3] if n["title"]] or ["No recent news available"]
        
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
import pandas_ta as ta

@router.get("/sectors")
async def get_sectors_analysis():
    try:
        # Major Sector Indices in India
        sector_indices = {
            "Nifty Bank": "^NSEBANK",
            "Nifty IT": "^CNXIT",
            "Nifty Auto": "^CNXAUTO",
            "Nifty Pharma": "^CNXPHARMA",
            "Nifty FMCG": "^CNXFMCG",
            "Nifty Metal": "^CNXMETAL",
            "Nifty Energy": "^CNXENERGY",
            "Nifty Realty": "^CNXREALTY"
        }
        
        sector_data = []
        for name, ticker_str in sector_indices.items():
            ticker = yf.Ticker(ticker_str)
            hist = ticker.history(period="5d")
            if not hist.empty and len(hist) >= 2:
                current = hist["Close"].iloc[-1]
                prev = hist["Close"].iloc[-2]
                change_pct = ((current - prev) / prev) * 100
                
                status = "Neutral"
                if change_pct > 0.5:
                    status = "Up"
                elif change_pct < -0.5:
                    status = "Down"
                
                sector_data.append(f"- {name}: {change_pct:.2f}% ({status})")

        prompt = f"""
        You are an expert Indian Stock Market Quantitative Analyst.
        
        Here is the daily performance of major Indian sector indices:
        {chr(10).join(sector_data)}
        
        Provide a concise 2-paragraph overall Sector Analysis. 
        Identify which sectors are leading (Up), lagging (Down), or In Focus, and give brief reasons why based on typical market dynamics. Format as markdown.
        """
        
        analysis = await llm.generate(prompt)
        return {"status": "success", "analysis": analysis, "data": sector_data}
    except Exception as e:
        return {"status": "error", "message": str(e)}

class SectorStockList(BaseModel):
    sector_name: str
    stocks: list

@router.post("/sectors/analyze-list")
async def analyze_sector_list(payload: SectorStockList):
    try:
        # Just use the top 5 stocks from the list to avoid massive prompts
        top_stocks = payload.stocks[:5]
        stock_data = []
        for s in top_stocks:
            yf_sym = s if s.endswith(".NS") else f"{s}.NS"
            hist = yf.Ticker(yf_sym).history(period="5d")
            if not hist.empty and len(hist) >= 2:
                current = hist["Close"].iloc[-1]
                prev = hist["Close"].iloc[-2]
                change_pct = ((current - prev) / prev) * 100
                stock_data.append(f"- {s}: {change_pct:.2f}%")

        prompt = f"""
        You are an expert Indian Stock Market Quantitative Analyst.
        
        Sector: {payload.sector_name}
        Recent daily performance of key stocks in this sector:
        {chr(10).join(stock_data) if stock_data else "No data available."}
        
        Provide a concise 2-paragraph analysis of this specific sector's current performance based on these top constituents.
        Format as markdown.
        """
        analysis = await llm.generate(prompt)
        return {"status": "success", "analysis": analysis}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.get("/stock/{symbol}/indicators")
async def get_technical_indicators(symbol: str, timeframe: str = "1d"):
    yf_symbol = symbol if symbol.endswith(".NS") else f"{symbol}.NS"
    try:
        # Map timeframe to yfinance interval and period
        period_map = {"15m": "5d", "1h": "1mo", "1d": "1y", "1wk": "5y"}
        interval_map = {"15m": "15m", "1h": "60m", "1d": "1d", "1wk": "1wk"}
        
        period = period_map.get(timeframe, "1y")
        interval = interval_map.get(timeframe, "1d")
        
        hist = yf.Ticker(yf_symbol).history(period=period, interval=interval)
        if hist.empty or len(hist) < 200:
            return {"status": "error", "message": "Not enough historical data for indicators."}
            
        # Calculate indicators
        hist.ta.ema(length=50, append=True)
        hist.ta.ema(length=200, append=True)
        hist.ta.rsi(length=14, append=True)
        hist.ta.macd(fast=12, slow=26, signal=9, append=True)
        hist.ta.bbands(length=20, std=2, append=True)
        
        last_row = hist.iloc[-1]
        close_price = float(last_row["Close"])
        
        ema50 = float(last_row.get("EMA_50", 0))
        ema200 = float(last_row.get("EMA_200", 0))
        rsi = float(last_row.get("RSI_14", 0))
        
        macd_line = float(last_row.get("MACD_12_26_9", 0))
        macd_signal = float(last_row.get("MACDs_12_26_9", 0))
        
        bb_upper = float(last_row.get("BBU_20_2.0", 0))
        bb_lower = float(last_row.get("BBL_20_2.0", 0))
        bb_mid = float(last_row.get("BBM_20_2.0", 0))
        
        # Signals
        ema50_sig = "Bullish" if close_price > ema50 else "Bearish"
        ema200_sig = "Bullish" if close_price > ema200 else "Bearish"
        
        if rsi > 70:
            rsi_sig = "Bearish (Overbought)"
        elif rsi < 30:
            rsi_sig = "Bullish (Oversold)"
        else:
            rsi_sig = "Neutral"
            
        macd_sig = "Bullish" if macd_line > macd_signal else "Bearish"
        
        if close_price > bb_upper:
            bb_sig = "Bearish (Overbought)"
        elif close_price < bb_lower:
            bb_sig = "Bullish (Oversold)"
        else:
            bb_sig = "Neutral"

        indicators = [
            {"name": "EMA (50)", "value": round(ema50, 2), "signal": ema50_sig},
            {"name": "EMA (200)", "value": round(ema200, 2), "signal": ema200_sig},
            {"name": "RSI (14)", "value": round(rsi, 2), "signal": rsi_sig},
            {"name": "MACD", "value": f"{round(macd_line, 2)} / {round(macd_signal, 2)}", "signal": macd_sig},
            {"name": "Bollinger Bands", "value": f"U: {round(bb_upper,2)} | L: {round(bb_lower,2)}", "signal": bb_sig},
        ]
        
        return {"status": "success", "indicators": indicators, "current_price": round(close_price, 2)}
    except Exception as e:
        return {"status": "error", "message": str(e)}
