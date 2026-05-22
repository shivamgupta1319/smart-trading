import { IsString, IsNotEmpty, IsInt } from 'class-validator';

export class CreateConfigDto {
  @IsInt()
  stockId: number;

  @IsString()
  @IsNotEmpty()
  strategyName: string;

  @IsString()
  @IsNotEmpty()
  timeframe: string;
}
