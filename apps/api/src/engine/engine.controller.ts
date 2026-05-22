import { Controller, Post, Body } from '@nestjs/common';
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
}
