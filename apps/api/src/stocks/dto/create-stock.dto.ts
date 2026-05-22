import { IsString, IsNotEmpty, IsOptional, IsBoolean } from 'class-validator';

export class CreateStockDto {
  @IsString()
  @IsNotEmpty()
  symbol: string;

  @IsString()
  @IsNotEmpty()
  name: string;

  @IsBoolean()
  @IsOptional()
  isActive?: boolean;
}
