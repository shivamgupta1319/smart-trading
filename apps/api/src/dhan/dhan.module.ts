import { Module, Global } from '@nestjs/common';
import { DhanService } from './dhan.service';

@Global()
@Module({
  providers: [DhanService],
  exports: [DhanService],
})
export class DhanModule {}
