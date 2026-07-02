import {
  WebSocketGateway,
  WebSocketServer,
  OnGatewayInit,
  OnGatewayConnection,
  OnGatewayDisconnect,
} from '@nestjs/websockets';
import { Server, Socket } from 'socket.io';
import { Logger } from '@nestjs/common';

const wsCorsOrigins = (
  process.env.CORS_ORIGINS ||
  'http://localhost:5173,http://localhost:4200,https://trading.pseo.cloud'
)
  .split(',')
  .map((o) => o.trim())
  .filter(Boolean);

@WebSocketGateway({
  cors: {
    origin: wsCorsOrigins,
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
    this.logger.log(`Client connected: ${client.id}`);
  }

  handleDisconnect(client: Socket) {
    this.logger.log(`Client disconnected: ${client.id}`);
  }

  emitNewAlert(payload: any) {
    this.logger.log(`Emitting NEW_TRADE_ALERT: ${payload.strategyName} on ${payload.symbol}`);
    this.server.emit('NEW_TRADE_ALERT', payload);
  }
}

