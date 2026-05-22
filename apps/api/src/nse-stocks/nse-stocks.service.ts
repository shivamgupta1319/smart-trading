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
}
