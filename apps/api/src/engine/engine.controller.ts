import { Controller, Post, Get, Body, Param } from '@nestjs/common';
import axios from 'axios';

@Controller('api/engine')
export class EngineController {
  private readonly engineUrl = process.env.ENGINE_URL || 'http://localhost:8000';

  @Post('fetch-history')
  async fetchHistory(@Body() body: { symbol: string; timeframes?: string[] }) {
    const response = await axios.post(`${this.engineUrl}/api/engine/fetch-history`, body);
    return response.data;
  }

  @Post('run-backtest')
  async runBacktest(@Body() body: { symbol: string; strategy: string; timeframe: string }) {
    const response = await axios.post(`${this.engineUrl}/api/engine/run-backtest`, body);
    return response.data;
  }

  @Post('run-all-strategies')
  async runAllStrategies(@Body() body: { symbol: string }) {
    const response = await axios.post(`${this.engineUrl}/api/engine/run-all-strategies`, body);
    return response.data;
  }

  @Post('live-prices')
  async getLivePrices(@Body() body: { symbols: string[] }) {
    const response = await axios.post(`${this.engineUrl}/api/engine/live-prices`, body);
    return response.data;
  }

  @Get('analysis/dashboard')
  async getDashboardAnalysis() {
    const response = await axios.get(`${this.engineUrl}/api/engine/analysis/dashboard`);
    return response.data;
  }

  @Get('analysis/stock/:symbol')
  async getStockAnalysis(@Param('symbol') symbol: string) {
    const response = await axios.get(`${this.engineUrl}/api/engine/analysis/stock/${symbol}`);
    return response.data;
  }
}
