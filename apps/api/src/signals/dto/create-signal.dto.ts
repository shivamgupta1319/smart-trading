import { IsString, IsNotEmpty, IsNumber, IsInt, IsOptional, IsIn } from 'class-validator';

export class CreateSignalDto {
  @IsInt()
  stockId!: number;

  @IsString()
  @IsNotEmpty()
  strategyName!: string;

  @IsIn(['BUY', 'SELL'])
  signalType!: string;

  @IsNumber()
  entryPrice!: number;

  @IsNumber()
  stopLoss!: number;

  @IsNumber()
  target!: number;

  @IsIn(['INTRADAY', 'SHORT_SWING', 'MID_SWING', 'LONG_POSITIONAL'])
  @IsOptional()
  holdDuration?: string;
}


