import { BadRequestException, Injectable, NotFoundException } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';
import { CreateConfigDto } from './dto/create-config.dto';

@Injectable()
export class ConfigsService {
  constructor(private prisma: PrismaService) {}

  async findAll() {
    const configs = await this.prisma.activeConfiguration.findMany({
      include: { stock: true },
      orderBy: { updatedAt: 'desc' },
    });
    if (configs.length === 0) return configs;

    // Attach each config's most recent backtest snapshot. One query for all relevant
    // (stockId) rows, newest first, then pick the first seen per (stockId, strategyName).
    const stockIds = [...new Set(configs.map((c) => c.stockId))];
    const reports = await this.prisma.backtestReport.findMany({
      where: { stockId: { in: stockIds } },
      orderBy: { createdAt: 'desc' },
    });
    const latestByKey = new Map<string, (typeof reports)[number]>();
    for (const r of reports) {
      const key = `${r.stockId}|${r.strategyName}`;
      if (!latestByKey.has(key)) latestByKey.set(key, r); // desc order → first = newest
    }
    return configs.map((c) => ({
      ...c,
      latestBacktest: latestByKey.get(`${c.stockId}|${c.strategyName}`) ?? null,
    }));
  }

  async findBySymbol(symbol: string) {
    const stock = await this.prisma.stock.findUnique({ where: { symbol } });
    if (!stock) throw new NotFoundException(`Stock ${symbol} not found`);

    return this.prisma.activeConfiguration.findMany({
      where: { stockId: stock.id },
      orderBy: { updatedAt: 'desc' },
    });
  }

  async toggle(dto: CreateConfigDto) {
    const stock = await this.prisma.stock.findUnique({ where: { symbol: dto.symbol } });
    if (!stock) throw new NotFoundException(`Stock ${dto.symbol} not found`);

    const existing = await this.prisma.activeConfiguration.findUnique({
      where: { stockId_strategyName: { stockId: stock.id, strategyName: dto.strategyName } },
    });

    if (existing) {
      await this.prisma.activeConfiguration.delete({
        where: { stockId_strategyName: { stockId: stock.id, strategyName: dto.strategyName } },
      });
      return { status: 'removed', strategyName: dto.strategyName };
    } else {
      const added = await this.prisma.activeConfiguration.create({
        data: {
          stockId: stock.id,
          strategyName: dto.strategyName,
          timeframe: dto.timeframe
        },
        include: { stock: true }
      });
      return { status: 'added', config: added };
    }
  }

  /**
   * The owner's switch for real money on one cell (the second lock). Switching ON is
   * refused unless the cell is PROVEN and its stock has a broker id; switching OFF always
   * works. A broker id can be saved in the same call.
   */
  async setLive(id: number, enabled: boolean, securityId?: string) {
    const config = await this.prisma.activeConfiguration.findUnique({ where: { id }, include: { stock: true } });
    if (!config) throw new NotFoundException(`Configuration #${id} not found`);

    const cleanId = securityId?.trim();
    if (cleanId !== undefined && cleanId !== '') {
      if (!/^[0-9]{1,10}$/.test(cleanId)) throw new BadRequestException('The broker id must be a number (Dhan security id).');
      await this.prisma.stock.update({ where: { id: config.stockId }, data: { dhanSecurityId: cleanId } });
    }
    const brokerId = cleanId || config.stock.dhanSecurityId;

    if (enabled) {
      if (config.status !== 'PROVEN') {
        throw new BadRequestException(
          `Real money can only be switched on for a PROVEN cell. ${config.stock.symbol} ${config.strategyName} is ${config.status}.`,
        );
      }
      if (!brokerId) {
        throw new BadRequestException(`${config.stock.symbol} has no Dhan security id yet. Send it as securityId.`);
      }
    }
    const updated = await this.prisma.activeConfiguration.update({
      where: { id },
      data: { liveEnabled: enabled },
      include: { stock: true },
    });
    return {
      id: updated.id,
      symbol: updated.stock.symbol,
      strategyName: updated.strategyName,
      status: updated.status,
      liveEnabled: updated.liveEnabled,
      dhanSecurityId: updated.stock.dhanSecurityId,
    };
  }

  async remove(id: number) {
    const config = await this.prisma.activeConfiguration.findUnique({ where: { id } });
    if (!config) throw new NotFoundException(`Configuration #${id} not found`);
    return this.prisma.activeConfiguration.delete({ where: { id } });
  }
}
