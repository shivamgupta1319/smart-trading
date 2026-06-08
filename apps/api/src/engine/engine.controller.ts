import { Controller, Post, Get, Body, Param, Query } from '@nestjs/common';
import axios from 'axios';

@Controller('api/engine')
export class EngineController {
  private readonly engineUrl = process.env.ENGINE_URL || 'http://localhost:8000';

  // Pre-configured client that forwards the shared API key to the engine
  // (engine enforces it when API_KEY is set) and sets a sane default timeout.
  private readonly http = axios.create({
    baseURL: this.engineUrl,
    timeout: 60000,
    headers: process.env.API_KEY ? { 'x-api-key': process.env.API_KEY } : {},
  });

  @Post('fetch-history')
  async fetchHistory(@Body() body: { symbol: string; timeframes?: string[] }) {
    const response = await this.http.post(`/api/engine/fetch-history`, body);
    return response.data;
  }

  @Post('run-backtest')
  async runBacktest(@Body() body: { symbol: string; strategy: string; timeframe: string }) {
    const response = await this.http.post(`/api/engine/run-backtest`, body);
    return response.data;
  }

  @Post('run-all-strategies')
  async runAllStrategies(@Body() body: { symbol: string }) {
    const response = await this.http.post(`/api/engine/run-all-strategies`, body);
    return response.data;
  }

  @Post('run-strategy-all-stocks')
  async runStrategyAllStocks(@Body() body: { strategy: string; timeframe?: string }) {
    const response = await this.http.post(`/api/engine/run-strategy-all-stocks`, body);
    return response.data;
  }

  @Post('run-walk-forward')
  async runWalkForward(
    @Body() body: { symbol: string; strategy: string; timeframe: string; folds?: number },
  ) {
    const response = await this.http.post(`/api/engine/run-walk-forward`, body);
    return response.data;
  }

  @Post('run-monte-carlo')
  async runMonteCarlo(
    @Body() body: { symbol: string; strategy: string; timeframe: string; iterations?: number },
  ) {
    const response = await this.http.post(`/api/engine/run-monte-carlo`, body);
    return response.data;
  }

  @Get('leaderboard')
  async leaderboard() {
    const response = await this.http.get(`/api/engine/leaderboard`);
    return response.data;
  }

  @Post('auto-select')
  async autoSelect(
    @Body()
    body: { strategies?: string[]; topN?: number; clearExisting?: boolean; dryRun?: boolean },
  ) {
    // Heavy: backtests every (strategy × stock) plus walk-forward + Monte-Carlo
    // on survivors. Override the 60s default with a long timeout (10 min).
    const response = await this.http.post(`/api/engine/auto-select`, body, {
      timeout: 600000,
    });
    return response.data;
  }

  @Post('custom-backtest')
  async customBacktest(@Body() body: { symbol: string; spec: any; timeframe?: string }) {
    const response = await this.http.post(`/api/engine/custom-backtest`, body);
    return response.data;
  }

  @Get('strategies')
  async getStrategies() {
    const response = await this.http.get(`/api/engine/strategies`);
    return response.data;
  }

  @Get('regime')
  async marketRegime() {
    const response = await this.http.get(`/api/engine/regime`);
    return response.data;
  }

  @Get('regime/:symbol')
  async stockRegime(@Param('symbol') symbol: string) {
    const response = await this.http.get(`/api/engine/regime/${encodeURIComponent(symbol)}`);
    return response.data;
  }

  @Get('broker/status')
  async brokerStatus() {
    const response = await this.http.get(`/api/engine/broker/status`);
    return response.data;
  }

  @Get('broker/probe/:symbol')
  async brokerProbe(@Param('symbol') symbol: string) {
    const response = await this.http.get(`/api/engine/broker/probe/${encodeURIComponent(symbol)}`);
    return response.data;
  }

  @Post('broker/dhan/token')
  async setDhanToken(@Body() body: { token: string }) {
    const response = await this.http.post(`/api/engine/broker/dhan/token`, body);
    return response.data;
  }

  @Post('live-prices')
  async getLivePrices(@Body() body: { symbols: string[] }) {
    const response = await this.http.post(`/api/engine/live-prices`, body);
    return response.data;
  }

  @Get('analysis/dashboard')
  async getDashboardAnalysis() {
    const response = await this.http.get(`/api/engine/analysis/dashboard`);
    return response.data;
  }

  @Get('analysis/news')
  async getMarketNews() {
    const response = await this.http.get(`/api/engine/analysis/news`);
    return response.data;
  }

  @Get('analysis/stock/:symbol')
  async getStockAnalysis(@Param('symbol') symbol: string) {
    const response = await this.http.get(`/api/engine/analysis/stock/${encodeURIComponent(symbol)}`);
    return response.data;
  }

  @Get('analysis/sectors')
  async getSectorsAnalysis() {
    const response = await this.http.get(`/api/engine/analysis/sectors`);
    return response.data;
  }

  @Post('analysis/sectors/analyze-list')
  async analyzeSectorList(@Body() body: any) {
    const response = await this.http.post(`/api/engine/analysis/sectors/analyze-list`, body);
    return response.data;
  }

  @Get('analysis/stock/:symbol/indicators')
  async getStockIndicators(@Param('symbol') symbol: string, @Query('timeframe') timeframe: string) {
    const response = await this.http.get(
      `/api/engine/analysis/stock/${encodeURIComponent(symbol)}/indicators`,
      { params: { timeframe: timeframe || '1d' } },
    );
    return response.data;
  }

  @Get('chart-data/:symbol')
  async getChartData(@Param('symbol') symbol: string, @Query('timeframe') timeframe: string) {
    const response = await this.http.get(`/api/engine/chart-data/${encodeURIComponent(symbol)}`, {
      params: { timeframe: timeframe || '1d' },
      timeout: 30000,
    });
    return response.data;
  }
}
