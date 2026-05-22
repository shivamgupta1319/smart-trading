import { Injectable, NotFoundException, ConflictException } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';
import { CreateStockDto } from './dto/create-stock.dto';

@Injectable()
export class StocksService {
  constructor(private prisma: PrismaService) {}

  async findAll() {
    return this.prisma.stock.findMany({ orderBy: { symbol: 'asc' } });
  }

  async findOne(id: number) {
    const stock = await this.prisma.stock.findUnique({ where: { id } });
    if (!stock) throw new NotFoundException(`Stock #${id} not found`);
    return stock;
  }

  async create(dto: CreateStockDto) {
    const existing = await this.prisma.stock.findUnique({ where: { symbol: dto.symbol.toUpperCase() } });
    if (existing) throw new ConflictException(`Stock ${dto.symbol} already exists`);
    return this.prisma.stock.create({
      data: { ...dto, symbol: dto.symbol.toUpperCase() },
    });
  }

  async remove(id: number) {
    await this.findOne(id);
    return this.prisma.stock.delete({ where: { id } });
  }

  async toggleActive(id: number) {
    const stock = await this.findOne(id);
    return this.prisma.stock.update({
      where: { id },
      data: { isActive: !stock.isActive },
    });
  }
}
