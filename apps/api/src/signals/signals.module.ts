import { Module } from '@nestjs/common';
import { SignalsService } from './signals.service';
import { SignalsController } from './signals.controller';
import { SignalsGateway } from './signals.gateway';
import { PrismaModule } from '../prisma/prisma.module';

@Module({
  imports: [PrismaModule],
  providers: [SignalsService, SignalsGateway],
  controllers: [SignalsController],
})
export class SignalsModule {}
