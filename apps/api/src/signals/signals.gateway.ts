import {
  WebSocketGateway,
  WebSocketServer,
  OnGatewayInit,
  OnGatewayConnection,
  OnGatewayDisconnect,
} from '@nestjs/websockets';
import { Server, Socket } from 'socket.io';
import { Logger } from '@nestjs/common';

@WebSocketGateway({
  cors: {
    origin: (process.env.CORS_ORIGINS || 'http://localhost:5173,http://localhost:4200')
      .split(',')
      .map((o) => o.trim())
      .filter(Boolean),
    credentials: true,
  },
  transports: ['websocket', 'polling'],
})
export class SignalsGateway implements OnGatewayInit, OnGatewayConnection, OnGatewayDisconnect {
  @WebSocketServer()
  server!: Server;

  private readonly logger = new Logger(SignalsGateway.name);

  afterInit() {
    this.logger.log('WebSocket Gateway initialized');
  }

  handleConnection(client: Socket) {
    // Opt-in socket auth: if API_KEY is set, the client must present it in the
    // handshake auth payload (`auth: { apiKey }`) or a query param.
    const required = process.env.API_KEY;
    if (required) {
      const provided =
        (client.handshake.auth as { apiKey?: string })?.apiKey ||
        (client.handshake.query?.apiKey as string);
      if (provided !== required) {
        this.logger.warn(`Rejected socket ${client.id} — bad API key`);
        client.disconnect(true);
        return;
      }
    }
    this.logger.log(`Client connected: ${client.id}`);
  }

  handleDisconnect(client: Socket) {
    this.logger.log(`Client disconnected: ${client.id}`);
  }

  emitNewAlert(payload: any) {
    this.logger.log(`Emitting NEW_TRADE_ALERT: ${payload.strategyName} on ${payload.symbol}`);
    this.server.emit('NEW_TRADE_ALERT', payload);
  }

  /**
   * Broadcast a trade lifecycle update (close / partial / trailing-SL / reversal)
   * so the dashboard can react in real time instead of polling. The old gateway
   * only emitted NEW_TRADE_ALERT, leaving every other event invisible to the UI.
   */
  emitTradeUpdate(event: 'CLOSED' | 'PARTIAL' | 'SL_UPDATED', payload: Record<string, unknown>) {
    this.logger.log(`Emitting TRADE_UPDATE/${event}: ${payload.symbol ?? ''}`);
    this.server.emit('TRADE_UPDATE', { event, ...payload });
  }
}

