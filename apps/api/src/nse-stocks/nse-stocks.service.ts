import { Injectable } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';

@Injectable()
export class NseStocksService {
  constructor(private prisma: PrismaService) {}

  async search(query: string) {
    if (!query || query.length < 2) {
      return this.prisma.nseStock.findMany({ take: 20, orderBy: { symbol: 'asc' } });
    }
    return this.prisma.nseStock.findMany({
      where: {
        OR: [
          { symbol: { contains: query, mode: 'insensitive' } },
          { companyName: { contains: query, mode: 'insensitive' } },
        ],
      },
      take: 20,
      orderBy: { symbol: 'asc' }
    });
  }

  async getAll() {
    return this.prisma.nseStock.findMany({
      select: { id: true, symbol: true, sector: true },
      orderBy: { symbol: 'asc' }
    });
  }

  async updateSector(symbol: string, sector: string) {
    return this.prisma.nseStock.update({
      where: { symbol },
      data: { sector },
    });
  }

  async getSectors() {
    const records = await this.prisma.nseStock.findMany({
      select: { sector: true },
      distinct: ['sector'],
      where: {
        sector: { not: null, notIn: ['Unknown', ''] }
      },
      orderBy: { sector: 'asc' }
    });
    return records.map(r => r.sector);
  }

  async getBySector(sector: string) {
    return this.prisma.nseStock.findMany({
      where: { sector },
      orderBy: { symbol: 'asc' }
    });
  }
}
