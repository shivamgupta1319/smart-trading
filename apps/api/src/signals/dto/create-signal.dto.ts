import { IsString, IsNotEmpty, IsNumber, IsInt, IsOptional } from 'class-validator';

export class CreateSignalDto {
  @IsInt()
  stockId!: number;

  @IsString()
  @IsNotEmpty()
  strategyName!: string;

  @IsString()
  @IsNotEmpty()
  signalType!: string; // "BUY" | "SELL"

  @IsNumber()
  entryPrice!: number;

  @IsNumber()
  stopLoss!: number;

  @IsNumber()
  target!: number;

  @IsString()
  @IsOptional()
  holdDuration?: string; // "INTRADAY" | "SHORT_SWING" | "MID_SWING" | "LONG_POSITIONAL"
}


