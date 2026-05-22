import { Injectable, NotFoundException } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';
import { CreateConfigDto } from './dto/create-config.dto';

@Injectable()
export class ConfigsService {
  constructor(private prisma: PrismaService) {}

  async findAll() {
    return this.prisma.activeConfiguration.findMany({
      include: { stock: true },
      orderBy: { updatedAt: 'desc' },
    });
  }

  async upsert(dto: CreateConfigDto) {
    const stock = await this.prisma.stock.findUnique({ where: { symbol: dto.symbol } });
    if (!stock) throw new NotFoundException(`Stock ${dto.symbol} not found`);

    return this.prisma.activeConfiguration.upsert({
      where: { stockId: stock.id },
      update: { strategyName: dto.strategyName, timeframe: dto.timeframe },
      create: {
        stockId: stock.id,
        strategyName: dto.strategyName,
        timeframe: dto.timeframe
      },
      include: { stock: true },
    });
  }

  async remove(id: number) {
    const config = await this.prisma.activeConfiguration.findUnique({ where: { id } });
    if (!config) throw new NotFoundException(`Configuration #${id} not found`);
    return this.prisma.activeConfiguration.delete({ where: { id } });
  }
}
