import { Module, Global } from '@nestjs/common';
import { DhanService } from './dhan.service';
import { DhanController } from './dhan.controller';
import { PrismaModule } from '../prisma/prisma.module';

@Global()
@Module({
  imports: [PrismaModule],
  providers: [DhanService],
  controllers: [DhanController],
  exports: [DhanService],
})
export class DhanModule {}
