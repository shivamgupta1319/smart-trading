import { IsString, IsNotEmpty } from "class-validator";

export class CreateConfigDto {
  @IsString()
  @IsNotEmpty()
  symbol: string;

  @IsString()
  @IsNotEmpty()
  strategyName: string;

  @IsString()
  @IsNotEmpty()
  timeframe: string;
}
