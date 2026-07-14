import { Module, Global } from '@nestjs/common';
import { DhanService } from './dhan.service';
import { PrismaModule } from '../prisma/prisma.module';

@Global()
@Module({
  imports: [PrismaModule],
  providers: [DhanService],
  exports: [DhanService],
})
export class DhanModule {}
