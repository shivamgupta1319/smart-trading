import { IsString, IsNotEmpty, IsNumber, IsInt, IsOptional, IsIn, IsBoolean } from 'class-validator';

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

  // The market's condition when the signal was found (sent by the scanner; labels only).
  @IsIn(['TRENDING_UP', 'TRENDING_DOWN', 'RANGING', 'VOLATILE'])
  @IsOptional()
  marketRegime?: string | null;

  @IsIn(['UP', 'DOWN', 'FLAT'])
  @IsOptional()
  marketDirection?: string | null;

  @IsNumber()
  @IsOptional()
  marketBreadthPct?: number | null;

  @IsBoolean()
  @IsOptional()
  alignedWithMarket?: boolean | null;
}


