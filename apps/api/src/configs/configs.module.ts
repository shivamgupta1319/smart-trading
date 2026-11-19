import { Module } from '@nestjs/common';
import { ConfigsService } from './configs.service';
import { ConfigsController } from './configs.controller';
import { LifecycleService } from './lifecycle.service';
import { PrismaModule } from '../prisma/prisma.module';

@Module({
  imports: [PrismaModule],
  providers: [ConfigsService, LifecycleService],
  controllers: [ConfigsController],
  exports: [LifecycleService],
})
export class ConfigsModule {}
